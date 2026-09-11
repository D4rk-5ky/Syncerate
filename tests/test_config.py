import tempfile
import textwrap
import unittest
from pathlib import Path

from syncerate.config import (
    load_app_config,
    option_is_enabled,
    validate_syncoid_command_template,
)


BASE = """\
[Syncerate Config]
Mail = No
SystemAction = No
DateTime = %Y-%m-%d_%H_%M_%S
LogDestination = No
SourceListPath = /tmp/source
DestListPath = /tmp/dest
PassWord = No
SyncoidCommand = syncoid SourceDataSet DestDataSet
UseSSHAgent = No
RetryBrokenPipe = No
Use_MQTT = No
Use_HomeAssistant = No
MQTT_JSON_Status = No
"""


class ConfigTests(unittest.TestCase):
    def load_text(self, text: str):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.cfg"
            path.write_text(text, encoding="utf-8")
            return load_app_config(str(path))

    def test_shipped_example_config_loads(self):
        project_root = Path(__file__).resolve().parents[1]
        config = load_app_config(
            str(project_root / "config" / "example-Syncerate.cfg")
        )
        self.assertEqual(
            config.raw_config.get("Syncerate Config", "mqtt_json_topic"),
            "homeassistant/syncerate/status",
        )

    def test_valid_minimal_config_loads(self):
        cfg = self.load_text(BASE)
        self.assertFalse(cfg.use_mqtt)
        self.assertFalse(cfg.mqtt_json_status)
        self.assertIsNone(cfg.log_destination)

    def test_multiline_backup_comment_uses_ini_continuation_lines(self):
        cfg = self.load_text(
            BASE
            + "BackupTitle = Nightly backup\n"
            + "BackupComment = First line\n"
            + "    Second line\n"
            + "    Third line\n"
        )
        self.assertEqual(
            cfg.backup_comment,
            "First line\nSecond line\nThird line",
        )

    def test_option_is_enabled_remains_compatibility_helper(self):
        self.assertTrue(option_is_enabled(" on "))
        self.assertFalse(option_is_enabled("typo"))

    def test_boolean_typo_is_rejected_by_loader(self):
        with self.assertRaisesRegex(ValueError, "RetryBrokenPipe"):
            self.load_text(BASE.replace("RetryBrokenPipe = No", "RetryBrokenPipe = YESS"))

    def test_all_documented_boolean_spellings_are_accepted(self):
        for value in ("Yes", "True", "1", "On"):
            cfg = self.load_text(
                BASE.replace("RetryBrokenPipe = No", f"RetryBrokenPipe = {value}")
            )
            self.assertTrue(cfg.retry_broken_pipe)
        for value in ("No", "False", "0", "Off"):
            cfg = self.load_text(
                BASE.replace("RetryBrokenPipe = No", f"RetryBrokenPipe = {value}")
            )
            self.assertFalse(cfg.retry_broken_pipe)

    def test_empty_password_option_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "PassWord must not be empty"):
            self.load_text(BASE.replace("PassWord = No", "PassWord ="))

    def test_empty_required_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "LogDestination"):
            self.load_text(BASE.replace("LogDestination = No", "LogDestination ="))

    def test_syncoid_command_requires_both_placeholders(self):
        with self.assertRaisesRegex(ValueError, "exactly one SourceDataSet"):
            self.load_text(BASE.replace("syncoid SourceDataSet DestDataSet", "syncoid pool/a pool/b"))

    def test_syncoid_command_rejects_duplicate_placeholder(self):
        with self.assertRaisesRegex(ValueError, "exactly one SourceDataSet"):
            validate_syncoid_command_template(
                "syncoid SourceDataSet SourceDataSet DestDataSet"
            )

    def test_syncoid_command_reports_shlex_error(self):
        with self.assertRaisesRegex(ValueError, "Could not parse SyncoidCommand"):
            validate_syncoid_command_template('syncoid "SourceDataSet DestDataSet')

    def test_enabled_mqtt_requires_broker_address(self):
        text = BASE.replace("Use_MQTT = No", "Use_MQTT = Yes")
        with self.assertRaisesRegex(ValueError, "broker_address"):
            self.load_text(text)

    def test_enabled_mqtt_requires_valid_port_range(self):
        text = BASE.replace("Use_MQTT = No", "Use_MQTT = Yes") + textwrap.dedent(
            """
            broker_address = localhost
            broker_port = 70000
            mqtt_topic = test/topic
            mqtt_message = ON
            """
        )
        with self.assertRaisesRegex(ValueError, "between 1 and 65535"):
            self.load_text(text)

    def test_enabled_legacy_mqtt_requires_topic(self):
        text = BASE.replace("Use_MQTT = No", "Use_MQTT = Yes") + textwrap.dedent(
            """
            broker_address = localhost
            broker_port = 1883
            mqtt_message = ON
            """
        )
        with self.assertRaisesRegex(ValueError, "mqtt_topic"):
            self.load_text(text)

    def test_enabled_home_assistant_requires_availability_topic(self):
        text = (
            BASE.replace("Use_MQTT = No", "Use_MQTT = Yes")
            .replace("Use_HomeAssistant = No", "Use_HomeAssistant = Yes")
            + textwrap.dedent(
                """
                broker_address = localhost
                broker_port = 1883
                mqtt_topic = test/topic
                mqtt_message = ON
                """
            )
        )
        with self.assertRaisesRegex(ValueError, "HomeAssistant_Available"):
            self.load_text(text)

    def test_enabled_json_mqtt_requires_dedicated_topic(self):
        text = BASE.replace(
            "MQTT_JSON_Status = No", "MQTT_JSON_Status = Yes"
        ) + textwrap.dedent(
            """
            broker_address = localhost
            broker_port = 1883
            mqtt_json_topic =
            """
        )
        with self.assertRaisesRegex(ValueError, "mqtt_json_topic"):
            self.load_text(text)

    def test_json_topic_conflict_with_legacy_topic_is_rejected(self):
        text = (
            BASE.replace("Use_MQTT = No", "Use_MQTT = Yes")
            .replace("MQTT_JSON_Status = No", "MQTT_JSON_Status = Yes")
            + textwrap.dedent(
                """
                broker_address = localhost
                broker_port = 1883
                mqtt_topic = same/topic
                mqtt_message = ON
                mqtt_json_topic = same/topic
                """
            )
        )
        with self.assertRaisesRegex(ValueError, "different from the legacy"):
            self.load_text(text)


if __name__ == "__main__":
    unittest.main()
