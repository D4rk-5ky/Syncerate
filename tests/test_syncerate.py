import configparser
import logging
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import Syncerate


class FakeChild:
    def __init__(self, indexes, exitstatus=0, before="", after="", buffer=""):
        self.indexes = list(indexes)
        self.exitstatus = exitstatus
        self.signalstatus = None
        self.before = before
        self.after = after
        self.buffer = buffer
        self.logfile = None
        self.sent_lines = []

    def expect(self, patterns):
        return self.indexes.pop(0)

    def sendline(self, value):
        self.sent_lines.append(value)

    def close(self):
        return None

    def terminate(self, force=False):
        return None


class ScriptedPexpect:
    EOF = object()

    def __init__(self, children):
        self.children = list(children)
        self.calls = []

    def spawn(self, command, args, timeout=None, encoding="utf-8"):
        self.calls.append([command, *args])
        return self.children.pop(0)


class SubprocessPexpect:
    EOF = object()

    class spawn:
        def __init__(self, command, args, timeout=None, encoding="utf-8"):
            completed = subprocess.run(
                [command, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            self._output = completed.stdout
            self.exitstatus = completed.returncode
            self.signalstatus = None
            self.before = completed.stdout
            self.after = ""
            self.buffer = ""
            self.logfile = None

        def expect(self, patterns):
            if self.logfile is not None and self._output:
                self.logfile.write(self._output)
                self.logfile.flush()
                self._output = ""
            return patterns.index(SubprocessPexpect.EOF)

        def sendline(self, value):
            return None

        def close(self):
            return None

        def terminate(self, force=False):
            return None


class SyncerateTests(unittest.TestCase):
    def make_logger(self):
        logger = logging.getLogger(f"syncerate-test-{id(self)}")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.INFO)
        return logger

    def make_settings(self, **overrides):
        values = {
            "config_path": "test.cfg",
            "backup_title": "",
            "backup_comment": "",
            "source_list_path": "source",
            "dest_list_path": "dest",
            "syncoid_command": "syncoid SourceDataSet DestDataSet",
            "password_option": "No",
            "mail_recipient": None,
            "datetime_format": "%Y",
            "log_destination": None,
            "system_action": None,
            "mqtt": Syncerate.MQTTSettings(enabled=False),
        }
        values.update(overrides)
        return Syncerate.SyncerateSettings(**values)

    def make_context(self, pexpect_module, settings=None):
        return Syncerate.RuntimeContext(
            settings=settings or self.make_settings(),
            config=configparser.RawConfigParser(),
            logger=self.make_logger(),
            run_files=Syncerate.RunFiles("test", None, None, None),
            pexpect_module=pexpect_module,
        )

    def test_import_creates_no_runtime_configuration_globals(self):
        forbidden = {
            "config",
            "SourceLines",
            "DestLines",
            "DestExtraArgs",
            "PassWord",
            "MailOption",
            "LogDestination",
            "SystemOption",
            "Use_MQTT",
        }
        self.assertFalse(forbidden.intersection(vars(Syncerate)))

    def test_build_command_preserves_spaces_and_extra_arguments(self):
        result = Syncerate.build_syncoid_command(
            "syncoid SourceDataSet DestDataSet",
            "Pool/Data Set",
            "Backup/Data Set",
            ["--recvoptions=o compression=zstd"],
        )
        self.assertEqual(
            result,
            [
                "syncoid",
                "Pool/Data Set",
                "Backup/Data Set",
                "--recvoptions=o compression=zstd",
            ],
        )

    def test_disabled_mqtt_does_not_read_broker_or_ha_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.cfg"
            config_path.write_text(
                """[Syncerate Config]
SourceListPath = source
DestListPath = dest
SyncoidCommand = syncoid SourceDataSet DestDataSet
PassWord = No
Mail = No
DateTime = %Y
LogDestination = No
SystemAction = No
Use_MQTT = 0
broker_port = not-an-integer
""",
                encoding="utf-8",
            )
            settings, _ = Syncerate.load_settings(str(config_path))
            self.assertFalse(settings.mqtt.enabled)
            self.assertFalse(settings.mqtt.home_assistant.enabled)

    def test_disabled_ha_does_not_require_availability_topic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.cfg"
            config_path.write_text(
                """[Syncerate Config]
SourceListPath = source
DestListPath = dest
SyncoidCommand = syncoid SourceDataSet DestDataSet
PassWord = No
Mail = No
DateTime = %Y
LogDestination = No
SystemAction = No
Use_MQTT = Yes
broker_address = localhost
broker_port = 1883
mqtt_topic = test/topic
mqtt_message = ON
Use_HomeAssistant = No
""",
                encoding="utf-8",
            )
            settings, _ = Syncerate.load_settings(str(config_path))
            self.assertTrue(settings.mqtt.enabled)
            self.assertFalse(settings.mqtt.home_assistant.enabled)
            self.assertIsNone(settings.mqtt.home_assistant.available_topic)

    def test_no_resume_state_is_returned_and_retried(self):
        fake_pexpect = ScriptedPexpect(
            [
                FakeChild([8], exitstatus=1),
                FakeChild([6], exitstatus=0),
            ]
        )
        context = self.make_context(fake_pexpect)
        pairs = [Syncerate.DatasetPair("Pool/Data", "Backup/Data", ())]

        Syncerate.run_dataset_pairs(context, pairs)

        self.assertEqual(len(fake_pexpect.calls), 2)
        self.assertIn("--no-resume", fake_pexpect.calls[1])

    def test_known_destroy_warning_remains_non_fatal(self):
        child = FakeChild(
            [1, 9, 6],
            exitstatus=1,
            after="WARN zfs destroy failed: 256",
        )
        context = self.make_context(ScriptedPexpect([child]))
        pairs = [Syncerate.DatasetPair("Pool/Data", "Backup/Data", ())]

        Syncerate.run_dataset_pairs(context, pairs)

    def test_main_runs_complete_fake_local_transfer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_list = root / "source-list"
            destination_list = root / "destination-list"
            fake_syncoid = root / "fake-syncoid"
            config_path = root / "config.cfg"
            log_directory = root / "logs"

            source_list.write_text("Pool/Data Set\n", encoding="utf-8")
            destination_list.write_text(
                'Backup/Data Set: --recvoptions="o compression=zstd"\n',
                encoding="utf-8",
            )
            fake_syncoid.write_text(
                "#!/usr/bin/python3\n"
                "import sys\n"
                "print('FAKE SYNCOID ARGV:', repr(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            fake_syncoid.chmod(0o755)

            config_path.write_text(
                f"""[Syncerate Config]
BackupTitle = Test
BackupComment = Context test
SourceListPath = {source_list}
DestListPath = {destination_list}
SyncoidCommand = {fake_syncoid} SourceDataSet DestDataSet
PassWord = No
Mail = No
DateTime = %Y-%m-%d_%H_%M_%S
LogDestination = {log_directory}
SystemAction = No
Use_MQTT = No
""",
                encoding="utf-8",
            )

            with mock.patch.object(
                Syncerate.importlib,
                "import_module",
                return_value=SubprocessPexpect,
            ):
                exit_code = Syncerate.main(["--conf", str(config_path)])

            self.assertEqual(exit_code, Syncerate.EXIT_OK)
            output_files = list(log_directory.glob("*.out"))
            self.assertEqual(len(output_files), 1)
            output = output_files[0].read_text(encoding="utf-8")
            self.assertIn("'Pool/Data Set'", output)
            self.assertIn("'Backup/Data Set'", output)
            self.assertIn("'--recvoptions=o compression=zstd'", output)


if __name__ == "__main__":
    unittest.main()
