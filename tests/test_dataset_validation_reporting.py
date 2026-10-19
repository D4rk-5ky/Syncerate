"""Full source/destination preflight audits, failure routing and presentation."""

import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from syncerate.app import main
from syncerate.datasets import compare_dataset_names, format_dataset_validation_report, load_dataset_pairs
from syncerate.errors import EXIT_LIST_ERROR, SyncerateError
from tests.helpers import make_config, make_logger


class DatasetValidationReportingTests(unittest.TestCase):
    def test_all_entries_including_final_and_surplus_lines_are_audited(self):
        sources = ["pool/good", "pool/wrong-one", "pool/good-two", "pool/last"]
        destinations = ["backup/good", "backup/different", "backup/good-two", "backup/different-last", "backup/extra"]
        report = compare_dataset_names(sources, destinations)
        self.assertEqual([item.line_number for item in report.matches], [1, 3])
        self.assertEqual([item.line_number for item in report.mismatches], [2, 4, 5])
        self.assertEqual(report.mismatches[-1].reason, "Missing source list entry")
        text = format_dataset_validation_report(report)
        self.assertLess(text.index("MISMATCHING DATASET PAIRS"), text.index("MATCHING DATASET PAIRS"))
        for path in sources + destinations:
            self.assertIn(path, text)
        self.assertIn("Final dataset names differ", text)

    def test_trailing_slash_and_empty_lists_fail_closed(self):
        report = compare_dataset_names(["pool/a/", "pool/valid"], ["backup/a/", "backup/valid"])
        self.assertEqual(len(report.matches), 1)
        self.assertEqual(len(report.mismatches), 1)
        self.assertIn("must not end", report.mismatches[0].reason)
        report = compare_dataset_names([], ["backup/data"])
        self.assertEqual(report.mismatches[0].source, None)
        self.assertIn("(missing)", format_dataset_validation_report(report))

    def test_preflight_failure_mail_mqtt_and_terminal_report_all_mismatches(self):
        for log_enabled in (False, True):
            for json_enabled in (False, True):
                with self.subTest(log_enabled=log_enabled, json_enabled=json_enabled), tempfile.TemporaryDirectory() as root:
                    root = Path(root)
                    src, dst = root / "sources", root / "destinations"
                    src.write_text("pool/good\npool/wrong\npool/good-two\npool/last\n", encoding="utf-8")
                    dst.write_text('backup/good\nbackup/other: --no-sync-snap\nbackup/good-two\nbackup/last-wrong\n', encoding="utf-8")
                    config_file = root / "backup.toml"
                    config_file.write_text("", encoding="utf-8")
                    logs = root / "logs"
                    logs.mkdir()
                    cfg = make_config(
                        config_path=str(config_file),
                        source_list_path=str(src), destination_list_path=str(dst),
                        log_destination=str(logs) + "/" if log_enabled else None,
                        mail_option="test@example.invalid", use_mqtt=True,
                        mqtt_json_status=json_enabled,
                        send_mqtt_on_success=False, send_mail_on_success=False,
                        system_option="must-not-run",
                    )
                    publication = mock.Mock()
                    paho = types.ModuleType("paho")
                    mqtt = types.ModuleType("paho.mqtt")
                    mqtt.publish = types.SimpleNamespace(multiple=publication)
                    paho.mqtt = mqtt
                    console = io.StringIO()
                    with (
                        mock.patch.dict("sys.modules", {"paho": paho, "paho.mqtt": mqtt}),
                        mock.patch("syncerate.app.load_app_config", return_value=cfg),
                        mock.patch("syncerate.notifications.send_mail", return_value=(0, "")) as mail,
                        mock.patch("syncerate.app.resolve_password") as password,
                        mock.patch("syncerate.app.run_replications") as replicate,
                        mock.patch("syncerate.app.SystemAction") as system_action,
                        contextlib.redirect_stdout(console),
                    ):
                        status = main(["-c", str(config_file)])
                    self.assertEqual(status, EXIT_LIST_ERROR)
                    password.assert_not_called()
                    replicate.assert_not_called()
                    system_action.assert_not_called()
                    mail.assert_called_once()
                    publication.assert_called_once()

                    subject, body, recipient = mail.call_args.args[:3]
                    self.assertIn("Source/destination datasets mismatch", subject)
                    self.assertEqual(recipient, "test@example.invalid")
                    self.assertTrue(body.startswith("Source/destination dataset validation FAILED"))
                    self.assertLess(body.index("MISMATCHING DATASET PAIRS"), body.index("MATCHING DATASET PAIRS"))
                    self.assertLess(body.index("MISMATCHING DATASET PAIRS"), body.index("Final run summary"))
                    self.assertLess(body.index("Final run summary"), body.index("Failure reason:"))
                    self.assertIn("Total datasets   :   4", body)
                    self.assertIn("Completed datasets :   0", body)
                    self.assertIn("Failed datasets  :   0", body)
                    self.assertIn("pool/wrong", body)
                    self.assertIn("backup/other", body)
                    self.assertIn("pool/last", body)
                    self.assertIn("backup/last-wrong", body)
                    self.assertIn("pool/good-two", body)
                    payloads = publication.call_args.args[0]
                    self.assertEqual(len(payloads), 1)
                    self.assertFalse(payloads[0]["retain"])
                    self.assertEqual(payloads[0]["topic"], "syncerate/status" if json_enabled else "syncerate/result/error")
                    payload = json.loads(payloads[0]["payload"])
                    self.assertEqual(payload["status"], "failure")
                    self.assertEqual(payload["exit_code"], EXIT_LIST_ERROR)
                    self.assertEqual([d["line"] for d in payload["mismatching_datasets"]], [2, 4])
                    self.assertEqual([d["line"] for d in payload["matching_datasets"]], [1, 3])
                    self.assertEqual([d["line"] for d in payload["failed_datasets"]], [2, 4])
                    self.assertEqual(payload["source_dataset_count"], 4)
                    self.assertEqual(payload["destination_dataset_count"], 4)

                    output = console.getvalue()
                    self.assertIn("========== DATASET VALIDATION FAILURE ==========", output)
                    self.assertIn("MISMATCHING DATASET PAIRS", output)
                    self.assertIn("MATCHING DATASET PAIRS", output)
                    self.assertEqual(output.strip().splitlines()[-1].split(' ERROR: ')[-1],
                                     "========== END DATASET VALIDATION FAILURE ==========")
                    if log_enabled:
                        attachment_names = {Path(path).suffix for path in mail.call_args.args[3]}
                        self.assertTrue({".log", ".err"}.issubset(attachment_names))
                        self.assertIn("MISMATCHING DATASET PAIRS", body)
                        log_text = "\n".join(path.read_text(encoding="utf-8") for path in logs.iterdir())
                        self.assertIn("MISMATCHING DATASET PAIRS", log_text)
                        self.assertIn("MATCHING DATASET PAIRS", log_text)
                    else:
                        self.assertNotIn(".err file", body)

    def test_last_dataset_mismatch_stops_dry_run_too(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            src, dst = root / "sources", root / "destinations"
            src.write_text("pool/first\npool/last\n", encoding="utf-8")
            dst.write_text("backup/first\nbackup/not-last\n", encoding="utf-8")
            toml = root / "backup.toml"
            toml.write_text("", encoding="utf-8")
            cfg = make_config(config_path=str(toml), source_list_path=str(src),
                              destination_list_path=str(dst))
            with self.assertRaises(SyncerateError) as caught:
                load_dataset_pairs(cfg, make_logger("last-pair-preflight"))
            self.assertEqual(caught.exception.exit_code, EXIT_LIST_ERROR)
            report = caught.exception.dataset_validation_report
            self.assertEqual(report.matches[0].line_number, 1)
            self.assertEqual(report.mismatches[0].line_number, 2)
            with (mock.patch("syncerate.app.load_app_config", return_value=cfg),
                  mock.patch("syncerate.app.resolve_password") as password,
                  mock.patch("syncerate.app.run_replications") as replicate,
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(main(["--conf", str(toml), "--dry-run"]), EXIT_LIST_ERROR)
            password.assert_not_called()
            replicate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
