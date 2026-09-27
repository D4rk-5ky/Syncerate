import json
import configparser
import types
import unittest
from unittest import mock

from syncerate.app import main, successfull_run
from syncerate.errors import SyncerateError
from syncerate.models import DatasetPair, MissingDatasetFailure, ReplicationSummary
from syncerate.notifications import (
    MailTo,
    build_mqtt_status_payload,
    mqtt_error_output,
    run_summary_header_text,
    send_error_mail,
    send_mqtt_failure_status,
)
from tests.helpers import make_config, make_logger, no_logging_context


class NotificationTests(unittest.TestCase):
    def setUp(self):
        """Capture MQTT publishes locally without connecting to a broker."""

        self.publish = mock.Mock()
        paho = types.ModuleType("paho")
        mqtt = types.ModuleType("paho.mqtt")
        mqtt.publish = types.SimpleNamespace(multiple=self.publish)
        paho.mqtt = mqtt
        patcher = mock.patch.dict("sys.modules", {"paho": paho, "paho.mqtt": mqtt})
        patcher.start()
        self.addCleanup(patcher.stop)

    def mqtt_config(self, **overrides):
        """Provide valid broker/topics with inert test defaults."""

        raw = configparser.RawConfigParser()
        raw.read_dict({"Syncerate Config": {
            "broker_address": "broker.example.test",
            "broker_port": "1883",
            "mqtt_topic": "syncerate/result",
            "mqtt_message": "ON",
            "mqtt_json_topic": "syncerate/status",
            "HomeAssistant_Available": "syncerate/available",
        }})
        return make_config(raw_config=raw, **overrides)

    def test_error_publish_routing_ignores_success_switch(self):
        error = SyncerateError("connection refused", 7, child_warning="SSH detail")
        for legacy, structured, expected_topic in (
            (True, False, "syncerate/result/error"),
            (False, True, "syncerate/status"),
            (True, True, "syncerate/status"),
        ):
            for success_enabled in (True, False):
                with self.subTest(legacy=legacy, structured=structured, success_enabled=success_enabled):
                    self.publish.reset_mock()
                    cfg = self.mqtt_config(
                        use_mqtt=legacy, mqtt_json_status=structured,
                        use_home_assistant=True,
                        send_mqtt_on_success=success_enabled,
                    )
                    send_mqtt_failure_status(error, cfg, make_logger())
                    self.publish.assert_called_once()
                    messages = self.publish.call_args.args[0]
                    self.assertEqual(len(messages), 1)
                    self.assertEqual(messages[0]["topic"], expected_topic)
                    self.assertIs(messages[0]["retain"], False)
                    self.assertEqual(messages[0]["qos"], 0)
                    payload = json.loads(messages[0]["payload"])
                    self.assertEqual(payload["status"], "failure")
                    self.assertIs(payload["success"], False)
                    self.assertEqual(payload["exit_code"], 7)
                    self.assertEqual(payload["error"], "connection refused")
                    self.assertEqual(payload["stderr"], "SSH detail")

    @mock.patch("syncerate.notifications.send_mail", return_value=(0, ""))
    def test_success_switches_are_independent_for_success_and_warning(self, mail):
        for warning in (False, True):
            for mail_enabled in (False, True):
                for mqtt_enabled in (False, True):
                    with self.subTest(warning=warning, mail=mail_enabled, mqtt=mqtt_enabled):
                        mail.reset_mock()
                        self.publish.reset_mock()
                        cfg = self.mqtt_config(
                            mail_option="user@example.test", use_mqtt=True,
                            mqtt_json_status=True, use_home_assistant=True,
                            send_mail_on_success=mail_enabled,
                            send_mqtt_on_success=mqtt_enabled,
                        )
                        summary = ReplicationSummary(
                            broken_pipe_failed_datasets=[DatasetPair("pool/a", "backup/a", ())]
                            if warning else []
                        )
                        successfull_run(cfg, no_logging_context(), make_logger(), summary)
                        self.assertEqual(mail.call_count, int(mail_enabled))
                        self.assertEqual(self.publish.call_count, int(mqtt_enabled))
                        if mqtt_enabled:
                            messages = self.publish.call_args.args[0]
                            self.assertEqual([m["topic"] for m in messages], [
                                "syncerate/available", "syncerate/result", "syncerate/status"
                            ])
                            self.assertEqual([m["retain"] for m in messages], [True, True, False])
                            self.assertEqual(messages[0]["payload"], "online")
                            self.assertEqual(messages[1]["payload"], "ON")
                            self.assertEqual(json.loads(messages[2]["payload"])["warning"], warning)

    @mock.patch("syncerate.notifications.send_mail", return_value=(0, ""))
    def test_default_success_switches_send_enabled_channels(self, mail):
        cfg = self.mqtt_config(mail_option="user@example.test", use_mqtt=True)
        successfull_run(cfg, no_logging_context(), make_logger())
        mail.assert_called_once()
        self.publish.assert_called_once()
        self.assertEqual(self.publish.call_args.args[0], [
            {"topic": "syncerate/result", "payload": "ON", "retain": True, "qos": 0}
        ])

    @mock.patch("syncerate.notifications.send_mail")
    def test_disabled_channels_remain_silent_on_success_and_failure(self, mail):
        cfg = self.mqtt_config()
        error = SyncerateError("failed", 7)
        successfull_run(cfg, no_logging_context(), make_logger())
        send_mqtt_failure_status(error, cfg, make_logger())
        send_error_mail(error, cfg, no_logging_context(), make_logger())
        self.publish.assert_not_called()
        mail.assert_not_called()

    def test_mqtt_errors_and_unavailable_config_do_not_republish(self):
        send_mqtt_failure_status(SyncerateError("bad config", 2), None, make_logger())
        send_mqtt_failure_status(
            SyncerateError("broker unavailable", 10, kind="mqtt"),
            self.mqtt_config(use_mqtt=True), make_logger(),
        )
        self.publish.assert_not_called()

    @mock.patch("syncerate.app.load_app_config")
    @mock.patch("syncerate.app.load_dataset_pairs", return_value=[])
    @mock.patch("syncerate.app.run_replications")
    @mock.patch("syncerate.notifications.send_mail", return_value=(0, ""))
    def test_main_failure_still_sends_mail_when_error_mqtt_fails(
        self, mail, replications, pairs, load_config
    ):
        load_config.return_value = self.mqtt_config(
            mail_option="user@example.test", use_mqtt=True,
            send_mail_on_success=False, send_mqtt_on_success=False,
        )
        replications.side_effect = SyncerateError("connection refused", 7, kind="syncoid")
        self.publish.side_effect = OSError("broker unavailable")
        self.assertEqual(main(["--conf", "mocked.cfg"]), 7)
        self.publish.assert_called_once()
        mail.assert_called_once()
        self.assertIn("Syncoid error", mail.call_args.args[0])

    def test_run_summary_email_header_matches_terminal_layout(self):
        cfg = make_config(
            backup_title="Nightly backup",
            backup_comment="First line\nSecond line",
        )
        header = run_summary_header_text(cfg, 62.345)
        self.assertIn(
            "Final run summary\n\nBackup title    :   Nightly backup\n\nBackup comment  :   First line",
            header,
        )
        self.assertIn("Backup comment  :   First line", header)
        self.assertIn("Second line\n\nTotal runtime   :   00:01:02.345", header)

    def test_run_summary_email_header_includes_transferred_size(self):
        cfg = make_config(backup_title="Nightly backup")
        summary = ReplicationSummary(transferred_bytes=2 * 1024**3)
        header = run_summary_header_text(cfg, 62.345, summary)
        self.assertIn("Data transferred :   2.00 GB", header)
        self.assertIn(
            "Data transferred :   2.00 GB\n\nTotal runtime   :   00:01:02.345",
            header,
        )

    def test_json_success_payload_includes_warning_and_skipped_pairs(self):
        pair = DatasetPair("pool/a", "backup/a", ())
        summary = ReplicationSummary([pair])
        cfg = make_config(backup_title="Nightly")
        payload = json.loads(
            build_mqtt_status_payload(
                cfg,
                success=True,
                exit_code=0,
                replication_summary=summary,
            )
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["title"], "Nightly")
        self.assertTrue(payload["warning"])
        self.assertEqual(
            payload["skipped_datasets"],
            [{"source": "pool/a", "destination": "backup/a"}],
        )


    def test_json_failure_payload_lists_missing_dataset_failures(self):
        pair = DatasetPair("pool/missing", "backup/missing", ())
        summary = ReplicationSummary(
            missing_dataset_failures=[
                MissingDatasetFailure(
                    pair,
                    ("cannot open 'pool/missing': dataset does not exist",),
                )
            ]
        )
        cfg = make_config(backup_title="Nightly")
        payload = json.loads(
            build_mqtt_status_payload(
                cfg,
                success=False,
                exit_code=8,
                error_message="missing dataset",
                replication_summary=summary,
            )
        )
        self.assertEqual(
            payload["failed_datasets"],
            [
                {
                    "source": "pool/missing",
                    "destination": "backup/missing",
                    "reason": "cannot open 'pool/missing': dataset does not exist",
                }
            ],
        )

    def test_json_failure_payload_contains_error_and_stderr(self):
        cfg = make_config()
        payload = json.loads(
            build_mqtt_status_payload(
                cfg,
                success=False,
                exit_code=7,
                error_message="connection refused",
                stderr_text="detail",
            )
        )
        self.assertEqual(payload["status"], "failure")
        self.assertFalse(payload["success"])
        self.assertEqual(payload["exit_code"], 7)
        self.assertEqual(payload["error"], "connection refused")
        self.assertEqual(payload["stderr"], "detail")


    @mock.patch("syncerate.notifications.send_mail", return_value=(0, ""))
    def test_missing_dataset_failure_mail_lists_failed_pair_and_reason(self, send_mail_mock):
        pair = DatasetPair("pool/missing", "backup/missing", ())
        summary = ReplicationSummary(
            missing_dataset_failures=[
                MissingDatasetFailure(
                    pair,
                    ("cannot open 'pool/missing': dataset does not exist",),
                )
            ]
        )
        cfg = make_config(mail_option="user@example.test", backup_title="Nightly")
        MailTo(
            cfg,
            no_logging_context(),
            make_logger("missing-mail"),
            Exit_Code=8,
            RuntimeSeconds=12.5,
            ReplicationSummaryData=summary,
        )

        send_mail_mock.assert_called_once()
        subject, body, recipient = send_mail_mock.call_args.args[:3]
        self.assertIn("Missing ZFS dataset or pool", subject)
        self.assertEqual(recipient, "user@example.test")
        self.assertIn("pool/missing -> backup/missing", body)
        self.assertIn("dataset does not exist", body)
        self.assertIn("exit code 8", body)


    @mock.patch("syncerate.notifications.MailTo")
    def test_error_mail_ignores_success_mail_switch(self, mail_to_mock):
        cfg = make_config(
            mail_option="user@example.test",
            send_mail_on_success=False,
        )
        error = SyncerateError("script failed", 2, kind="script")

        send_error_mail(
            error,
            cfg,
            no_logging_context(),
            make_logger("error-mail-success-switch-off"),
        )

        mail_to_mock.assert_called_once()

    @mock.patch("syncerate.notifications.send_mqtt_messages")
    def test_mqtt_failure_status_ignores_success_mqtt_switch(
        self, send_mqtt_messages_mock
    ):
        cfg = make_config(
            mqtt_json_status=True,
            send_mqtt_on_success=False,
        )
        error = SyncerateError("replication failed", 7, kind="syncoid")

        send_mqtt_failure_status(
            error,
            cfg,
            make_logger("mqtt-failure-success-switch-off"),
        )

        send_mqtt_messages_mock.assert_called_once()
        self.assertFalse(send_mqtt_messages_mock.call_args.kwargs["success"])
        self.assertEqual(send_mqtt_messages_mock.call_args.kwargs["exit_code"], 7)

    def test_mqtt_error_output_is_bounded_from_the_end(self):
        error = SyncerateError(
            "x",
            2,
            child_before="a" * 10,
            child_warning="b" * 10,
            syncoid_before="c" * 10,
        )
        text = mqtt_error_output(error, max_chars=12)
        self.assertEqual(len(text), 12)
        self.assertTrue(text.endswith("c" * 10))


if __name__ == "__main__":
    unittest.main()
