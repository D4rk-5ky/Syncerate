import json
import unittest

from syncerate.errors import SyncerateError
from syncerate.models import DatasetPair, ReplicationSummary
from syncerate.notifications import (
    build_mqtt_status_payload,
    mqtt_error_output,
    run_summary_header_text,
)
from tests.helpers import make_config


class NotificationTests(unittest.TestCase):
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
