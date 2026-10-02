import ast
import tempfile
import unittest
from pathlib import Path

from syncerate.config import (
    CONFIG_OPTION_LOCATIONS,
    load_app_config,
    option_is_enabled,
    validate_syncoid_command_template,
)


BASE = '''\
[backup]
BackupTitle = ""
BackupComment = ""

[syncoid]
SourceListPath = "/tmp/source"
DestListPath = "/tmp/dest"
SyncoidCommand = "syncoid SourceDataSet DestDataSet"

[ssh]
PassWord = "No"
UseSSHAgent = false
SSHAgentKeyLifetimeSeconds = 3600

[mail]
Mail = "No"
SendMailOnSuccess = true

[mqtt]
Use_MQTT = false
SendMQTTOnSuccess = true
broker_address = ""
broker_port = 1883
mqtt_username = ""
mqtt_password = ""
mqtt_topic = ""
mqtt_message = ""
MQTT_JSON_Status = false
mqtt_json_topic = ""

[home_assistant]
Use_HomeAssistant = false
HomeAssistant_Available = ""

[logging]
DateTime = "%Y-%m-%d_%H_%M_%S"
LogDestination = "No"

[runtime]
DryRun = false
SystemAction = "No"
ContinueOnMissingDataset = false
ContinueWithoutResume = true
RetryBrokenPipe = false
BrokenPipeRetryCount = 1
BrokenPipeRetryWaitSeconds = 10
'''


class ConfigTests(unittest.TestCase):
    def load_text(self, text: str):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.toml"
            path.write_text(text, encoding="utf-8")
            return load_app_config(str(path))

    def test_shipped_example_config_loads(self):
        project_root = Path(__file__).resolve().parents[1]
        config = load_app_config(
            str(project_root / "config" / "example-Syncerate.toml")
        )
        self.assertFalse(config.dry_run)
        self.assertFalse(config.continue_on_missing_dataset)
        self.assertFalse(config.continue_without_resume)
        self.assertTrue(config.retry_broken_pipe)
        self.assertEqual(config.broken_pipe_retry_count, 1)
        self.assertEqual(config.broken_pipe_retry_wait_seconds, 10)
        self.assertEqual(config.mqtt_json_topic, "homeassistant/syncerate/status")

    def test_shipped_example_contains_every_supported_config_option(self):
        project_root = Path(__file__).resolve().parents[1]
        cfg = load_app_config(str(project_root / "config" / "example-Syncerate.toml"))
        raw = cfg.raw_config
        expected = {
            (section, option)
            for section, options in CONFIG_OPTION_LOCATIONS.items()
            for option in options
        }
        actual = {
            (section, option)
            for section in CONFIG_OPTION_LOCATIONS
            for option in raw.get(section, {})
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len(expected), 31)

    def test_loader_option_accesses_match_documented_schema(self):
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "syncerate" / "config.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        loader = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "load_app_config"
        )
        section_variables = {
            "backup": "backup",
            "syncoid": "syncoid",
            "ssh": "ssh",
            "mail": "mail",
            "mqtt": "mqtt",
            "home_assistant": "home_assistant",
            "logging_section": "logging",
            "runtime": "runtime",
        }
        helper_names = {"_required_text", "_optional_text", "_boolean", "_integer"}
        accessed = set()
        for node in ast.walk(loader):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in helper_names or len(node.args) < 3:
                continue
            section_arg, option_arg = node.args[0], node.args[2]
            if not isinstance(section_arg, ast.Name) or not isinstance(option_arg, ast.Constant):
                continue
            section = section_variables.get(section_arg.id)
            if section is not None and isinstance(option_arg.value, str):
                accessed.add((section, option_arg.value))

        documented = {
            (section, option)
            for section, options in CONFIG_OPTION_LOCATIONS.items()
            for option in options
        }
        self.assertEqual(accessed, documented)
        self.assertEqual(len(accessed), 31)

    def test_valid_minimal_config_loads(self):
        cfg = self.load_text(BASE)
        self.assertFalse(cfg.dry_run)
        self.assertFalse(cfg.use_mqtt)
        self.assertFalse(cfg.continue_on_missing_dataset)
        self.assertFalse(cfg.mqtt_json_status)
        self.assertIsNone(cfg.log_destination)

    def test_continue_on_missing_dataset_defaults_false_and_requires_toml_boolean(self):
        without_option = BASE.replace("ContinueOnMissingDataset = false\n", "")
        self.assertFalse(self.load_text(without_option).continue_on_missing_dataset)
        self.assertTrue(
            self.load_text(
                BASE.replace(
                    "ContinueOnMissingDataset = false",
                    "ContinueOnMissingDataset = true",
                )
            ).continue_on_missing_dataset
        )
        with self.assertRaisesRegex(ValueError, "ContinueOnMissingDataset"):
            self.load_text(
                BASE.replace(
                    "ContinueOnMissingDataset = false",
                    'ContinueOnMissingDataset = "true"',
                )
            )

    def test_runtime_policy_options_reject_old_syncoid_table_location(self):
        moved = (
            "ContinueWithoutResume = true",
            "RetryBrokenPipe = false",
            "BrokenPipeRetryCount = 1",
            "BrokenPipeRetryWaitSeconds = 10",
        )
        for option_line in moved:
            with self.subTest(option=option_line.split(" =", 1)[0]):
                text = BASE.replace(option_line + "\n", "")
                text = text.replace(
                    'SyncoidCommand = "syncoid SourceDataSet DestDataSet"\n',
                    'SyncoidCommand = "syncoid SourceDataSet DestDataSet"\n' + option_line + "\n",
                )
                with self.assertRaisesRegex(ValueError, r"moved to the \[runtime\] table"):
                    self.load_text(text)

    def test_continue_without_resume_defaults_true_and_requires_toml_boolean(self):
        without_option = BASE.replace("ContinueWithoutResume = true\n", "")
        self.assertTrue(self.load_text(without_option).continue_without_resume)
        self.assertFalse(
            self.load_text(
                BASE.replace("ContinueWithoutResume = true", "ContinueWithoutResume = false")
            ).continue_without_resume
        )
        with self.assertRaisesRegex(ValueError, "ContinueWithoutResume"):
            self.load_text(
                BASE.replace(
                    "ContinueWithoutResume = true",
                    'ContinueWithoutResume = "false"',
                )
            )

    def test_dry_run_defaults_false_and_requires_toml_boolean(self):
        without_dry_run = BASE.replace("DryRun = false\n", "")
        self.assertFalse(self.load_text(without_dry_run).dry_run)
        self.assertTrue(
            self.load_text(BASE.replace("DryRun = false", "DryRun = true")).dry_run
        )
        with self.assertRaisesRegex(ValueError, "DryRun"):
            self.load_text(BASE.replace("DryRun = false", 'DryRun = "true"'))

    def test_success_notification_switches_default_to_enabled_when_omitted(self):
        text = BASE.replace("SendMailOnSuccess = true\n", "").replace(
            "SendMQTTOnSuccess = true\n", ""
        )
        cfg = self.load_text(text)
        self.assertTrue(cfg.send_mail_on_success)
        self.assertTrue(cfg.send_mqtt_on_success)

    def test_success_notification_switches_can_be_disabled(self):
        cfg = self.load_text(
            BASE.replace("SendMailOnSuccess = true", "SendMailOnSuccess = false")
            .replace("SendMQTTOnSuccess = true", "SendMQTTOnSuccess = false")
        )
        self.assertFalse(cfg.send_mail_on_success)
        self.assertFalse(cfg.send_mqtt_on_success)

    def test_success_notification_switch_rejects_non_boolean(self):
        for option in ("SendMailOnSuccess", "SendMQTTOnSuccess"):
            with self.subTest(option=option):
                with self.assertRaisesRegex(ValueError, option):
                    self.load_text(
                        BASE.replace(f"{option} = true", f'{option} = "sometimes"')
                    )

    def test_multiline_backup_comment_uses_toml_multiline_string(self):
        cfg = self.load_text(
            BASE.replace(
                'BackupTitle = ""\nBackupComment = ""',
                'BackupTitle = "Nightly backup"\nBackupComment = """First line\nSecond line\nThird line"""',
            )
        )
        self.assertEqual(
            cfg.backup_comment,
            "First line\nSecond line\nThird line",
        )

    def test_option_is_enabled_remains_legacy_compatibility_helper(self):
        self.assertTrue(option_is_enabled(" on "))
        self.assertFalse(option_is_enabled("typo"))

    def test_boolean_string_is_rejected_by_loader(self):
        with self.assertRaisesRegex(ValueError, "RetryBrokenPipe"):
            self.load_text(
                BASE.replace("RetryBrokenPipe = false", 'RetryBrokenPipe = "false"')
            )

    def test_native_toml_booleans_are_accepted_across_categories(self):
        cfg = self.load_text(
            BASE.replace("RetryBrokenPipe = false", "RetryBrokenPipe = true")
            .replace("DryRun = false", "DryRun = true")
            .replace(
                "ContinueOnMissingDataset = false",
                "ContinueOnMissingDataset = true",
            )
            .replace("SendMailOnSuccess = true", "SendMailOnSuccess = false")
            .replace("SendMQTTOnSuccess = true", "SendMQTTOnSuccess = false")
        )
        self.assertTrue(cfg.retry_broken_pipe)
        self.assertTrue(cfg.dry_run)
        self.assertTrue(cfg.continue_on_missing_dataset)
        self.assertFalse(cfg.send_mail_on_success)
        self.assertFalse(cfg.send_mqtt_on_success)

    def test_empty_password_option_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ssh.PassWord must not be empty"):
            self.load_text(BASE.replace('PassWord = "No"', 'PassWord = ""'))

    def test_empty_required_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "logging.LogDestination"):
            self.load_text(BASE.replace('LogDestination = "No"', 'LogDestination = ""'))

    def test_syncoid_command_requires_both_placeholders(self):
        with self.assertRaisesRegex(ValueError, "exactly one SourceDataSet"):
            self.load_text(
                BASE.replace(
                    'SyncoidCommand = "syncoid SourceDataSet DestDataSet"',
                    'SyncoidCommand = "syncoid pool/a pool/b"',
                )
            )

    def test_syncoid_command_rejects_duplicate_placeholder(self):
        with self.assertRaisesRegex(ValueError, "exactly one SourceDataSet"):
            validate_syncoid_command_template(
                "syncoid SourceDataSet SourceDataSet DestDataSet"
            )

    def test_syncoid_command_reports_shlex_error(self):
        with self.assertRaisesRegex(ValueError, "Could not parse SyncoidCommand"):
            validate_syncoid_command_template('syncoid "SourceDataSet DestDataSet')

    def test_enabled_mqtt_requires_broker_address(self):
        text = BASE.replace("Use_MQTT = false", "Use_MQTT = true")
        with self.assertRaisesRegex(ValueError, "broker_address"):
            self.load_text(text)

    def test_enabled_mqtt_requires_valid_port_range(self):
        text = (
            BASE.replace("Use_MQTT = false", "Use_MQTT = true")
            .replace('broker_address = ""', 'broker_address = "localhost"')
            .replace("broker_port = 1883", "broker_port = 70000")
            .replace('mqtt_topic = ""', 'mqtt_topic = "test/topic"')
        )
        with self.assertRaisesRegex(ValueError, "between 1 and 65535"):
            self.load_text(text)

    def test_enabled_legacy_mqtt_requires_topic(self):
        text = BASE.replace("Use_MQTT = false", "Use_MQTT = true").replace(
            'broker_address = ""', 'broker_address = "localhost"'
        )
        with self.assertRaisesRegex(ValueError, "mqtt_topic"):
            self.load_text(text)

    def test_enabled_legacy_mqtt_requires_message_key(self):
        text = (
            BASE.replace("Use_MQTT = false", "Use_MQTT = true")
            .replace('broker_address = ""', 'broker_address = "localhost"')
            .replace('mqtt_topic = ""', 'mqtt_topic = "test/topic"')
            .replace('mqtt_message = ""\n', "")
        )
        with self.assertRaisesRegex(ValueError, "mqtt_message"):
            self.load_text(text)

    def test_enabled_home_assistant_requires_availability_topic(self):
        text = (
            BASE.replace("Use_MQTT = false", "Use_MQTT = true")
            .replace('broker_address = ""', 'broker_address = "localhost"')
            .replace('mqtt_topic = ""', 'mqtt_topic = "test/topic"')
            .replace("Use_HomeAssistant = false", "Use_HomeAssistant = true")
        )
        with self.assertRaisesRegex(ValueError, "HomeAssistant_Available"):
            self.load_text(text)

    def test_enabled_json_mqtt_requires_dedicated_topic(self):
        text = BASE.replace("MQTT_JSON_Status = false", "MQTT_JSON_Status = true").replace(
            'broker_address = ""', 'broker_address = "localhost"'
        )
        with self.assertRaisesRegex(ValueError, "mqtt_json_topic"):
            self.load_text(text)

    def test_json_topic_conflict_with_legacy_topic_is_rejected(self):
        text = (
            BASE.replace("Use_MQTT = false", "Use_MQTT = true")
            .replace("MQTT_JSON_Status = false", "MQTT_JSON_Status = true")
            .replace('broker_address = ""', 'broker_address = "localhost"')
            .replace('mqtt_topic = ""', 'mqtt_topic = "same/topic"')
            .replace('mqtt_json_topic = ""', 'mqtt_json_topic = "same/topic"')
        )
        with self.assertRaisesRegex(ValueError, "different from the legacy"):
            self.load_text(text)

    def test_invalid_toml_reports_configuration_error(self):
        with self.assertRaisesRegex(ValueError, "Invalid TOML configuration"):
            self.load_text("[runtime\nDryRun = false\n")


if __name__ == "__main__":
    unittest.main()
