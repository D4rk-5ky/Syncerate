import io
import logging
import shlex
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from syncerate.app import main, successfull_run
from syncerate.logging_setup import (
    format_runtime_duration,
    log_final_run_summary,
    log_startup_configuration,
)
from tests.helpers import make_config, make_logger, no_logging_context, write_executable


class AppAndLoggingTests(unittest.TestCase):
    def test_runtime_duration_formats_hours_minutes_seconds_and_milliseconds(self):
        self.assertEqual(format_runtime_duration(3661.2344), "01:01:01.234")
        self.assertEqual(format_runtime_duration(-5), "00:00:00.000")

    def test_final_summary_logs_title_multiline_comment_then_runtime(self):
        cfg = make_config(
            backup_title="Nightly backup",
            backup_comment="First line\nSecond line\nThird line",
        )
        stream = io.StringIO()
        logger = logging.getLogger(f"final-summary-{id(self)}")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        log_final_run_summary(cfg, 62.345, logger)
        lines = stream.getvalue().splitlines()

        summary_index = next(i for i, line in enumerate(lines) if "Final run summary" in line)
        title_index = next(i for i, line in enumerate(lines) if "Backup title" in line)
        comment_index = next(i for i, line in enumerate(lines) if "Backup comment" in line)
        second_line_index = next(i for i, line in enumerate(lines) if "Second line" in line)
        runtime_index = next(i for i, line in enumerate(lines) if "Total runtime" in line)

        self.assertEqual(lines[summary_index + 1], "")
        self.assertEqual(title_index, summary_index + 2)
        self.assertLess(title_index, comment_index)
        self.assertEqual(lines[title_index + 1], "")
        self.assertEqual(comment_index, title_index + 2)
        self.assertLess(comment_index, second_line_index)
        self.assertLess(second_line_index, runtime_index)
        self.assertEqual(lines[runtime_index - 1], "")
        self.assertIn("00:01:02.345", lines[runtime_index])

    def test_startup_multiline_comment_prefixes_every_physical_log_line(self):
        import configparser

        raw = configparser.RawConfigParser()
        raw.read_string(
            textwrap.dedent(
                """
                [Syncerate Config]
                Mail = No
                SystemAction = No
                DateTime = %Y
                LogDestination = No
                BackupTitle = Nightly backup
                BackupComment = First line
                    Second line
                    Third line
                SourceListPath = source
                DestListPath = dest
                PassWord = No
                SyncoidCommand = syncoid SourceDataSet DestDataSet
                UseSSHAgent = No
                RetryBrokenPipe = No
                Use_MQTT = No
                Use_HomeAssistant = No
                MQTT_JSON_Status = No
                """
            )
        )
        cfg = make_config(
            raw_config=raw,
            backup_title="Nightly backup",
            backup_comment="First line\nSecond line\nThird line",
        )
        stream = io.StringIO()
        logger = logging.getLogger(f"multiline-log-{id(self)}")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        log_startup_configuration(cfg, no_logging_context(), logger)
        output_lines = stream.getvalue().splitlines()

        # The continuation lines must be separate logging records, not embedded
        # raw newlines inside one logging record. StreamHandler adds one newline
        # per record, and the logger helper preserves indentation for readability.
        self.assertGreaterEqual(sum("Second line" in line for line in output_lines), 2)
        self.assertGreaterEqual(sum("Third line" in line for line in output_lines), 2)
        self.assertFalse(any(line == "Second line" for line in output_lines))
        self.assertFalse(any(line == "Third line" for line in output_lines))

        heading_index = next(i for i, line in enumerate(output_lines) if "Backup information" in line)
        title_index = next(i for i, line in enumerate(output_lines) if "Backup title" in line)
        comment_index = next(i for i, line in enumerate(output_lines) if "Backup comment" in line)
        self.assertEqual(output_lines[heading_index + 1], "")
        self.assertEqual(title_index, heading_index + 2)
        self.assertEqual(output_lines[title_index + 1], "")
        self.assertEqual(comment_index, title_index + 2)

    @mock.patch("syncerate.app.SystemAction")
    @mock.patch("syncerate.app.MailTo", side_effect=FileNotFoundError("mail not installed"))
    def test_success_mail_exception_is_best_effort_and_system_action_still_runs(
        self, mail_to, system_action
    ):
        cfg = make_config(
            mail_option="user@example.test",
            system_option="echo done",
        )
        successfull_run(
            cfg,
            no_logging_context(),
            make_logger("mail-best-effort"),
            runtime_seconds=12.5,
        )
        mail_to.assert_called_once()
        system_action.assert_called_once()

    def test_logging_omits_unrelated_sections_and_secret_like_options(self):
        import configparser

        raw = configparser.RawConfigParser()
        raw.read_string(
            textwrap.dedent(
                """
                [Syncerate Config]
                Mail = No
                SystemAction = No
                DateTime = %Y
                LogDestination = No
                SourceListPath = source
                DestListPath = dest
                PassWord = top-secret
                SyncoidCommand = syncoid SourceDataSet DestDataSet
                custom_api_token = should-not-leak

                [Other Application]
                username = other-user
                password = other-secret
                """
            )
        )
        cfg = make_config(
            raw_config=raw,
            password_option="top-secret",
            syncoid_command="syncoid SourceDataSet DestDataSet",
        )
        stream = io.StringIO()
        logger = logging.getLogger(f"logging-test-{id(self)}")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        log_startup_configuration(cfg, no_logging_context(), logger)
        output = stream.getvalue()
        self.assertNotIn("top-secret", output)
        self.assertNotIn("should-not-leak", output)
        self.assertNotIn("other-secret", output)
        self.assertNotIn("Other Application", output)

    def write_config(
        self,
        directory: Path,
        script: str,
        source_text: str,
        dest_text: str,
        extra: str = "",
    ) -> Path:
        source = directory / "source-list"
        dest = directory / "dest-list"
        source.write_text(source_text, encoding="utf-8")
        dest.write_text(dest_text, encoding="utf-8")
        config = directory / "syncerate.cfg"
        config.write_text(
            textwrap.dedent(
                f"""
                [Syncerate Config]
                Mail = No
                SystemAction = No
                DateTime = %Y-%m-%d_%H_%M_%S
                LogDestination = No
                SourceListPath = {source}
                DestListPath = {dest}
                PassWord = No
                SyncoidCommand = {shlex.quote(script)} SourceDataSet DestDataSet
                UseSSHAgent = No
                RetryBrokenPipe = No
                Use_MQTT = No
                Use_HomeAssistant = No
                MQTT_JSON_Status = No
                {extra}
                """
            ),
            encoding="utf-8",
        )
        return config

    def test_main_success_path_with_fake_syncoid(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            script = write_executable(
                directory / "fake_syncoid.py",
                "print('replication complete', flush=True)\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/data\n",
                "backup/data\n",
            )
            self.assertEqual(main(["--conf", str(config)]), 0)

    def test_main_emits_final_runtime_summary(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            script = write_executable(
                directory / "fake_syncoid.py",
                "print('replication complete', flush=True)\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/data\n",
                "backup/data\n",
                "BackupTitle = Timer test\nBackupComment = First line\n    Second line",
            )
            stream = io.StringIO()
            with mock.patch("sys.stdout", stream):
                self.assertEqual(main(["--conf", str(config)]), 0)

            output = stream.getvalue()
            self.assertIn("Final run summary", output)
            self.assertIn("Backup title    :   Timer test", output)
            self.assertIn("Backup comment  :   First line", output)
            self.assertIn("Second line", output)
            self.assertIn("Total runtime   :", output)

    @mock.patch("syncerate.notifications.send_mail", return_value=(0, ""))
    def test_success_mail_and_attached_log_include_runtime_before_mail_is_sent(
        self, send_mail_mock
    ):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            log_directory = directory / "logs"
            script = write_executable(
                directory / "fake_syncoid.py",
                "print('replication complete', flush=True)\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/data\n",
                "backup/data\n",
                "\n".join(
                    [
                        "Mail = user@example.test",
                        f"LogDestination = {log_directory}",
                        "BackupTitle = Mail timer test",
                        "BackupComment = First line",
                        "    Second line",
                    ]
                ),
            )

            # write_config supplies Mail/LogDestination defaults, so replace them
            # rather than creating duplicate INI options.
            config_text = config.read_text(encoding="utf-8")
            config_text = config_text.replace("Mail = No", "Mail = user@example.test")
            config_text = config_text.replace(
                "LogDestination = No", f"LogDestination = {log_directory}"
            )
            config_text = config_text.replace(
                "Mail = user@example.test\nLogDestination = " + str(log_directory) + "\n",
                "",
            )
            config.write_text(config_text, encoding="utf-8")

            self.assertEqual(main(["--conf", str(config)]), 0)
            send_mail_mock.assert_called_once()
            subject, body, recipient, attachment_files = send_mail_mock.call_args.args

            self.assertIn("Final run summary\n\nBackup title    :   Mail timer test\n\nBackup comment  :   First line", body)
            self.assertIn("Backup comment  :   First line", body)
            self.assertIn("Second line\n\nTotal runtime   :", body)
            copied_log = body.split(".log file", 1)[1]
            self.assertIn("Total runtime   :", copied_log)
            self.assertEqual(recipient, "user@example.test")
            self.assertIn("Successful Syncerate.py run", subject)

            log_attachment = next(
                Path(path) for path in attachment_files if path.endswith(".log")
            )
            log_contents_at_send = log_attachment.read_text(encoding="utf-8")
            self.assertIn("Backup comment  :   First line", log_contents_at_send)
            self.assertIn("Total runtime   :", log_contents_at_send)

    def test_main_rejects_empty_active_lists_with_code_1(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            script = write_executable(directory / "fake_syncoid.py", "pass\n")
            config = self.write_config(directory, script, "# none\n", "# none\n")
            self.assertEqual(main(["--conf", str(config)]), 1)

    def test_main_rejects_invalid_boolean_before_replication_with_code_2(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            marker = directory / "ran"
            script = write_executable(
                directory / "fake_syncoid.py",
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/data\n",
                "backup/data\n",
                "RetryBrokenPipe = YESS",
            )
            self.assertEqual(main(["--conf", str(config)]), 2)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
