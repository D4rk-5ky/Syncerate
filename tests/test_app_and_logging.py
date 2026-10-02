import contextlib
import io
import logging
import shlex
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from syncerate.app import main, successfull_run
from syncerate.cli import parse_arguments
from syncerate.logging_setup import (
    format_runtime_duration,
    format_transfer_size,
    log_final_run_summary,
    log_startup_configuration,
)
from syncerate.models import DatasetPair, ReplicationSummary
from tests.helpers import make_config, make_logger, no_logging_context, write_executable


class AppAndLoggingTests(unittest.TestCase):
    def test_cli_help_describes_every_application_flag(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            with self.assertRaises(SystemExit) as caught:
                parse_arguments(["--help"])

        self.assertEqual(caught.exception.code, 0)
        help_text = stream.getvalue()
        self.assertIn("--conf FILE", help_text)
        self.assertIn("-c FILE", help_text)
        self.assertIn("required Syncerate TOML configuration file", help_text)
        self.assertIn("--dry-run", help_text)
        self.assertIn("planned Syncoid commands without starting", help_text)
        self.assertIn("runtime.DryRun = false", help_text)
        self.assertIn("--version", help_text)
        self.assertIn("Show the installed Syncerate version and exit.", help_text)
        self.assertIn("Examples:", help_text)

    def test_runtime_duration_formats_hours_minutes_seconds_and_milliseconds(self):
        self.assertEqual(format_runtime_duration(3661.2344), "01:01:01.234")
        self.assertEqual(format_runtime_duration(-5), "00:00:00.000")

    def test_transfer_size_chooses_kb_mb_gb_or_tb_automatically(self):
        self.assertEqual(format_transfer_size(512), "0.50 KB")
        self.assertEqual(format_transfer_size(2 * 1024), "2.00 KB")
        self.assertEqual(format_transfer_size(3 * 1024**2), "3.00 MB")
        self.assertEqual(format_transfer_size(4 * 1024**3), "4.00 GB")
        self.assertEqual(format_transfer_size(5 * 1024**4), "5.00 TB")

    def test_final_summary_marks_transfer_size_unavailable_when_pv_measurement_is_incomplete(self):
        cfg = make_config()
        summary = ReplicationSummary(
            transferred_bytes=1024**3,
            transfer_measurement_complete=False,
        )
        stream = io.StringIO()
        logger = logging.getLogger(f"unavailable-transfer-size-{id(self)}")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        log_final_run_summary(cfg, 10, logger, summary)
        self.assertIn("Data transferred :   Unavailable", stream.getvalue())

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

        replication_summary = ReplicationSummary(
            transferred_bytes=round(1.5 * 1024**3),
        )
        log_final_run_summary(cfg, 62.345, logger, replication_summary)
        lines = stream.getvalue().splitlines()

        summary_index = next(i for i, line in enumerate(lines) if "Final run summary" in line)
        title_index = next(i for i, line in enumerate(lines) if "Backup title" in line)
        comment_index = next(i for i, line in enumerate(lines) if "Backup comment" in line)
        second_line_index = next(i for i, line in enumerate(lines) if "Second line" in line)
        transferred_index = next(i for i, line in enumerate(lines) if "Data transferred" in line)
        runtime_index = next(i for i, line in enumerate(lines) if "Total runtime" in line)

        self.assertEqual(lines[summary_index + 1], "")
        self.assertEqual(title_index, summary_index + 2)
        self.assertLess(title_index, comment_index)
        self.assertEqual(lines[title_index + 1], "")
        self.assertEqual(comment_index, title_index + 2)
        self.assertLess(comment_index, second_line_index)
        self.assertLess(second_line_index, transferred_index)
        self.assertEqual(lines[transferred_index - 1], "")
        self.assertIn("1.50 GB", lines[transferred_index])
        self.assertEqual(lines[transferred_index + 1], "")
        self.assertEqual(runtime_index, transferred_index + 2)
        self.assertIn("00:01:02.345", lines[runtime_index])

    def test_startup_multiline_comment_prefixes_every_physical_log_line(self):
        raw = {
            "backup": {
                "BackupTitle": "Nightly backup",
                "BackupComment": "First line\nSecond line\nThird line",
            },
            "syncoid": {"SyncoidCommand": "syncoid SourceDataSet DestDataSet"},
            "ssh": {"PassWord": "No"},
            "mail": {"Mail": "No"},
            "logging": {"DateTime": "%Y", "LogDestination": "No"},
            "runtime": {"SystemAction": "No"},
        }
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


    @mock.patch("syncerate.app.SystemAction")
    @mock.patch("syncerate.app.MailTo")
    def test_success_mail_can_be_disabled_without_disabling_system_action(
        self, mail_to, system_action
    ):
        cfg = make_config(
            mail_option="user@example.test",
            send_mail_on_success=False,
            system_option="echo done",
        )
        successfull_run(
            cfg,
            no_logging_context(),
            make_logger("success-mail-disabled"),
            runtime_seconds=12.5,
        )
        mail_to.assert_not_called()
        system_action.assert_called_once()

    @mock.patch("syncerate.app.send_mqtt_messages")
    def test_success_mqtt_can_be_disabled(self, send_mqtt_messages_mock):
        cfg = make_config(
            use_mqtt=True,
            mqtt_json_status=True,
            send_mqtt_on_success=False,
        )
        successfull_run(
            cfg,
            no_logging_context(),
            make_logger("success-mqtt-disabled"),
            runtime_seconds=12.5,
        )
        send_mqtt_messages_mock.assert_not_called()

    def test_logging_omits_unrelated_sections_and_secret_like_options(self):
        raw = {
            "syncoid": {
                "SyncoidCommand": "syncoid SourceDataSet DestDataSet",
                "custom_api_token": "should-not-leak",
            },
            "ssh": {"PassWord": "top-secret"},
            "mail": {"Mail": "No"},
            "logging": {"DateTime": "%Y", "LogDestination": "No"},
            "runtime": {"SystemAction": "No"},
            "other_application": {
                "username": "other-user",
                "password": "other-secret",
            },
        }
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
        overrides: dict[str, object] | None = None,
    ) -> Path:
        import json

        source = directory / "source-list"
        dest = directory / "dest-list"
        source.write_text(source_text, encoding="utf-8")
        dest.write_text(dest_text, encoding="utf-8")
        config = directory / "syncerate.toml"

        values: dict[str, dict[str, object]] = {
            "backup": {"BackupTitle": "", "BackupComment": ""},
            "syncoid": {
                "SourceListPath": str(source),
                "DestListPath": str(dest),
                "SyncoidCommand": f"{shlex.quote(script)} SourceDataSet DestDataSet",
            },
            "ssh": {
                "PassWord": "No",
                "UseSSHAgent": False,
                "SSHAgentKeyLifetimeSeconds": 3600,
            },
            "mail": {"Mail": "No", "SendMailOnSuccess": True},
            "mqtt": {
                "Use_MQTT": False,
                "SendMQTTOnSuccess": True,
                "broker_address": "",
                "broker_port": 1883,
                "mqtt_username": "",
                "mqtt_password": "",
                "mqtt_topic": "",
                "mqtt_message": "",
                "MQTT_JSON_Status": False,
                "mqtt_json_topic": "",
            },
            "home_assistant": {
                "Use_HomeAssistant": False,
                "HomeAssistant_Available": "",
            },
            "logging": {
                "DateTime": "%Y-%m-%d_%H_%M_%S",
                "LogDestination": "No",
            },
            "runtime": {
                "DryRun": False,
                "SystemAction": "No",
                "ContinueOnMissingDataset": False,
                "ContinueWithoutResume": True,
                "RetryBrokenPipe": False,
                "BrokenPipeRetryCount": 1,
                "BrokenPipeRetryWaitSeconds": 0,
            },
        }

        for dotted_name, value in (overrides or {}).items():
            section, option = dotted_name.split(".", 1)
            values[section][option] = value

        lines: list[str] = []
        for section_name, options in values.items():
            lines.append(f"[{section_name}]")
            for option, value in options.items():
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                elif isinstance(value, int):
                    rendered = str(value)
                else:
                    rendered = json.dumps(str(value))
                lines.append(f"{option} = {rendered}")
            lines.append("")

        config.write_text("\n".join(lines), encoding="utf-8")
        return config


    @mock.patch("syncerate.app.SystemAction")
    @mock.patch("syncerate.app.run_replications")
    @mock.patch("syncerate.app.private_ssh_agent")
    @mock.patch("syncerate.app.resolve_password")
    def test_config_dry_run_reports_plan_without_cli_flag(
        self, resolve_password, private_agent, replications, system_action
    ):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            marker = directory / "must-not-run"
            script = write_executable(
                directory / "fake_syncoid.py",
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/data\n",
                "backup/data\n",
                {"runtime.DryRun": True},
            )

            stream = io.StringIO()
            with mock.patch("sys.stdout", stream):
                self.assertEqual(main(["--conf", str(config)]), 0)

            self.assertFalse(marker.exists())
            resolve_password.assert_not_called()
            private_agent.assert_not_called()
            replications.assert_not_called()
            system_action.assert_not_called()
            self.assertIn("Run mode        :   DRY RUN", stream.getvalue())

    @mock.patch("syncerate.app.SystemAction")
    @mock.patch("syncerate.app.run_replications")
    @mock.patch("syncerate.app.private_ssh_agent")
    @mock.patch("syncerate.app.resolve_password")
    def test_dry_run_reports_plan_without_executing_replication_or_post_action(
        self, resolve_password, private_agent, replications, system_action
    ):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            marker = directory / "must-not-run"
            script = write_executable(
                directory / "fake_syncoid.py",
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/data\n",
                "backup/data: --no-sync-snap\n",
                {
                    "ssh.PassWord": "Ask",
                    "runtime.SystemAction": "echo must-not-run",
                },
            )

            stream = io.StringIO()
            with mock.patch("sys.stdout", stream):
                self.assertEqual(main(["--conf", str(config), "--dry-run"]), 0)

            self.assertFalse(marker.exists())
            resolve_password.assert_not_called()
            private_agent.assert_not_called()
            replications.assert_not_called()
            system_action.assert_not_called()
            output = stream.getvalue()
            self.assertIn("Dry run report", output)
            self.assertIn("NO REPLICATION WAS PERFORMED", output)
            self.assertIn("Dataset pairs planned :   1", output)
            self.assertIn("pool/data -> backup/data", output)
            self.assertIn("--no-sync-snap", output)
            self.assertIn("Run mode        :   DRY RUN", output)

    @mock.patch("syncerate.app.SystemAction")
    @mock.patch("syncerate.app.MailTo")
    @mock.patch("syncerate.app.send_mqtt_messages")
    def test_dry_run_success_notifications_use_normal_success_switches(
        self, mqtt, mail, system_action
    ):
        pair = DatasetPair("pool/data", "backup/data", ())
        cfg = make_config(
            mail_option="user@example.test",
            use_mqtt=True,
            system_option="echo must-not-run",
            send_mail_on_success=False,
            send_mqtt_on_success=False,
        )
        successfull_run(
            cfg,
            no_logging_context(),
            make_logger("dry-success-switches-off"),
            runtime_seconds=1.0,
            dry_run=True,
            dry_run_report="Dry run report",
            dry_run_dataset_pairs=[pair],
        )
        mail.assert_not_called()
        mqtt.assert_not_called()
        system_action.assert_not_called()

        enabled_cfg = make_config(
            mail_option="user@example.test",
            use_mqtt=True,
            system_option="echo must-not-run",
            send_mail_on_success=True,
            send_mqtt_on_success=True,
        )
        successfull_run(
            enabled_cfg,
            no_logging_context(),
            make_logger("dry-success-switches-on"),
            runtime_seconds=1.0,
            dry_run=True,
            dry_run_report="Dry run report",
            dry_run_dataset_pairs=[pair],
        )
        mqtt.assert_called_once()
        self.assertTrue(mqtt.call_args.kwargs["dry_run"])
        mail.assert_called_once()
        self.assertTrue(mail.call_args.kwargs["DryRun"])
        system_action.assert_not_called()

    @mock.patch("syncerate.app.run_replications")
    @mock.patch("syncerate.app.resolve_password")
    @mock.patch("syncerate.app.send_error_mail")
    @mock.patch("syncerate.app.send_mqtt_failure_status")
    def test_dry_run_preflight_failure_still_uses_failure_notifications(
        self, mqtt, mail, password, replicate
    ):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            script = write_executable(
                directory / "fake.py",
                "raise SystemExit('must not run')\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/a\n",
                "backup/b\n",
                {
                    "mail.SendMailOnSuccess": False,
                    "mqtt.SendMQTTOnSuccess": False,
                },
            )
            self.assertEqual(main(["--conf", str(config), "--dry-run"]), 1)
            password.assert_not_called()
            replicate.assert_not_called()
            mqtt.assert_called_once()
            mail.assert_called_once()
            self.assertEqual(mqtt.call_args.args[0].exit_code, 1)
            self.assertTrue(mqtt.call_args.kwargs["dry_run"])
            self.assertEqual(mail.call_args.args[0].exit_code, 1)
            self.assertTrue(mail.call_args.kwargs["dry_run"])

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

    @mock.patch("syncerate.app.run_replications")
    @mock.patch("syncerate.app.resolve_password")
    @mock.patch("syncerate.app.send_error_mail")
    @mock.patch("syncerate.app.send_mqtt_failure_status")
    def test_preflight_mismatch_stops_before_any_replication(self, mqtt, mail, password, replicate):
        for sources, destinations in (
            ("pool/good\npool/a\n", "backup/good\nbackup/b\n"),
            ("pool/a\npool/b\n", "backup/a\n"),
            ("pool/a/\n", "backup/a/\n"),
        ):
            with self.subTest(sources=sources, destinations=destinations):
                mqtt.reset_mock(); mail.reset_mock()
                with tempfile.TemporaryDirectory() as td:
                    directory = Path(td)
                    marker = directory / "must-not-run"
                    script = write_executable(
                        directory / "fake.py",
                        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
                    )
                    config = self.write_config(directory, script, sources, destinations)
                    self.assertEqual(main(["--conf", str(config)]), 1)
                    self.assertFalse(marker.exists())
                    replicate.assert_not_called()
                    password.assert_not_called()
                    self.assertEqual(mqtt.call_args.args[0].exit_code, 1)
                    self.assertEqual(mail.call_args.args[0].exit_code, 1)

    @mock.patch("syncerate.app.successfull_run")
    @mock.patch("syncerate.app.send_error_mail")
    @mock.patch("syncerate.app.send_mqtt_failure_status")
    def test_resume_required_stops_list_and_uses_error_notifications(self, mqtt, mail, success):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            marker = directory / "later-pair-ran"
            script = write_executable(
                directory / "fake_syncoid.py",
                "import pathlib, sys, time\n"
                "if sys.argv[1] == 'pool/a':\n"
                "    print('WARN: ZFS resume feature not available on target machine', flush=True)\n"
                "    time.sleep(10)\n"
                f"pathlib.Path({str(marker)!r}).write_text('ran')\n",
            )
            config = self.write_config(
                directory, script, "pool/a\npool/b\n", "backup/a\nbackup/b\n",
                {
                    "runtime.ContinueWithoutResume": False,
                    "mail.SendMailOnSuccess": False,
                    "mqtt.SendMQTTOnSuccess": False,
                },
            )
            self.assertEqual(main(["--conf", str(config)]), 4)
            self.assertFalse(marker.exists())
            success.assert_not_called()
            mqtt.assert_called_once()
            mail.assert_called_once()
            self.assertEqual(mqtt.call_args.args[0].exit_code, 4)
            self.assertEqual(mail.call_args.args[0].exit_code, 4)


    @mock.patch("syncerate.app.successfull_run")
    @mock.patch("syncerate.app.send_error_mail")
    @mock.patch("syncerate.app.send_mqtt_failure_status")
    def test_main_missing_dataset_continues_list_then_reports_failure_code_8(
        self,
        mqtt_failure_mock,
        error_mail_mock,
        success_mock,
    ):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            marker = directory / "good-ran"
            script = write_executable(
                directory / "fake_syncoid.py",
                "import pathlib, sys\n"
                f"marker = pathlib.Path({str(marker)!r})\n"
                "if sys.argv[1].endswith('/missing'):\n"
                "    print(\"cannot open 'pool/missing': dataset does not exist\", flush=True)\n"
                "    sys.exit(2)\n"
                "marker.write_text('yes')\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/missing\npool/good\n",
                "backup/missing\nbackup/good\n",
                {"runtime.ContinueOnMissingDataset": True},
            )

            self.assertEqual(main(["--conf", str(config)]), 8)
            self.assertTrue(marker.exists())
            success_mock.assert_not_called()
            mqtt_failure_mock.assert_called_once()
            error_mail_mock.assert_called_once()
            summary = mqtt_failure_mock.call_args.kwargs["replication_summary"]
            self.assertTrue(summary.has_missing_dataset_failure)
            self.assertEqual(len(summary.missing_dataset_failures), 1)

    @mock.patch("syncerate.app.successfull_run")
    @mock.patch("syncerate.app.send_error_mail")
    @mock.patch("syncerate.app.send_mqtt_failure_status")
    def test_main_missing_dataset_stops_list_by_default_and_reports_failure_code_8(
        self,
        mqtt_failure_mock,
        error_mail_mock,
        success_mock,
    ):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            marker = directory / "good-ran"
            script = write_executable(
                directory / "fake_syncoid.py",
                "import pathlib, sys\n"
                f"marker = pathlib.Path({str(marker)!r})\n"
                "if sys.argv[1].endswith('/missing'):\n"
                "    print(\"cannot open 'pool/missing': dataset does not exist\", flush=True)\n"
                "    sys.exit(2)\n"
                "marker.write_text('yes')\n",
            )
            config = self.write_config(
                directory,
                script,
                "pool/missing\npool/good\n",
                "backup/missing\nbackup/good\n",
            )

            self.assertEqual(main(["--conf", str(config)]), 8)
            self.assertFalse(marker.exists())
            success_mock.assert_not_called()
            mqtt_failure_mock.assert_called_once()
            error_mail_mock.assert_called_once()
            summary = mqtt_failure_mock.call_args.kwargs["replication_summary"]
            self.assertTrue(summary.has_missing_dataset_failure)
            self.assertEqual(len(summary.missing_dataset_failures), 1)

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
                {
                    "backup.BackupTitle": "Timer test",
                    "backup.BackupComment": "First line\nSecond line",
                },
            )
            stream = io.StringIO()
            with mock.patch("sys.stdout", stream):
                self.assertEqual(main(["--conf", str(config)]), 0)

            output = stream.getvalue()
            self.assertIn("Final run summary", output)
            self.assertIn("Backup title    :   Timer test", output)
            self.assertIn("Backup comment  :   First line", output)
            self.assertIn("Second line", output)
            self.assertIn("Data transferred :   0.00 KB", output)
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
                {
                    "mail.Mail": "user@example.test",
                    "logging.LogDestination": str(log_directory),
                    "backup.BackupTitle": "Mail timer test",
                    "backup.BackupComment": "First line\nSecond line",
                },
            )

            self.assertEqual(main(["--conf", str(config)]), 0)
            send_mail_mock.assert_called_once()
            subject, body, recipient, attachment_files = send_mail_mock.call_args.args

            self.assertIn("Final run summary\n\nBackup title    :   Mail timer test\n\nBackup comment  :   First line", body)
            self.assertIn("Backup comment  :   First line", body)
            self.assertIn("Second line\n\nData transferred :   0.00 KB\n\nTotal runtime   :", body)
            copied_log = body.split(".log file", 1)[1]
            self.assertIn("Data transferred :   0.00 KB", copied_log)
            self.assertIn("Total runtime   :", copied_log)
            self.assertEqual(recipient, "user@example.test")
            self.assertIn("Successful Syncerate.py run", subject)

            log_attachment = next(
                Path(path) for path in attachment_files if path.endswith(".log")
            )
            log_contents_at_send = log_attachment.read_text(encoding="utf-8")
            self.assertIn("Backup comment  :   First line", log_contents_at_send)
            self.assertIn("Data transferred :   0.00 KB", log_contents_at_send)
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
                {"runtime.RetryBrokenPipe": "YESS"},
            )
            self.assertEqual(main(["--conf", str(config)]), 2)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
