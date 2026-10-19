"""Real OS-level tests of Syncerate's per-TOML single-run safelock."""

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from syncerate.app import main
from syncerate.errors import EXIT_BACKUP_LOCKED, EXIT_LOCK_ERROR, SyncerateError
from syncerate.locking import BackupLock
from syncerate.logging_setup import create_run_context
from tests.helpers import make_config


class BackupLockTests(unittest.TestCase):
    def test_same_toml_aliases_are_exclusive_and_file_is_safely_reused(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "nightly.toml"
            config.write_text("[runtime]\nDryRun = true\n", encoding="utf-8")
            alias = Path(root) / "alias.toml"
            alias.symlink_to(config)

            first = BackupLock.acquire(str(config))
            try:
                    self.assertEqual(first.path, Path(str(config) + ".lock"))
                    self.assertTrue(first.path.exists())
                    contents = first.path.read_text(encoding="utf-8")
                    self.assertIn(f"config={config}", contents)
                    self.assertIn(f"pid={os.getpid()}", contents)
                    with self.assertRaises(SyncerateError) as error:
                        BackupLock.acquire(str(alias))
                    self.assertEqual(error.exception.exit_code, EXIT_BACKUP_LOCKED)
                    with self.assertRaises(SyncerateError) as error:
                        BackupLock.acquire(str(config.parent / "." / config.name))
                    self.assertEqual(error.exception.exit_code, EXIT_BACKUP_LOCKED)
            finally:
                first.release()
                first.release()  # safe idempotence

            # Deliberately persist the inode to prevent unlink/recreate races.
            self.assertTrue(Path(str(config) + ".lock").exists())
            again = BackupLock.acquire(str(alias))
            again.release()

    def test_different_configs_same_basename_can_run_together(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root) / "host-a" / "backup.toml", Path(root) / "host-b" / "backup.toml"
            a.parent.mkdir()
            b.parent.mkdir()
            a.write_text("", encoding="utf-8")
            b.write_text("", encoding="utf-8")
            first = BackupLock.acquire(str(a))
            try:
                second = BackupLock.acquire(str(b))
                second.release()
            finally:
                first.release()

    def test_cross_process_conflict_then_lock_recovers_after_crash(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "backup.toml"
            config.write_text("", encoding="utf-8")
            script = (
                "import sys,time; from syncerate.locking import BackupLock; "
                "lock=BackupLock.acquire(sys.argv[1]); print('READY', flush=True); "
                "time.sleep(30)"
            )
            holder = subprocess.Popen(
                [sys.executable, "-B", "-c", script, str(config)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            try:
                self.assertEqual(holder.stdout.readline().strip(), "READY")
                with self.assertRaises(SyncerateError) as error:
                    BackupLock.acquire(str(config))
                self.assertEqual(error.exception.exit_code, EXIT_BACKUP_LOCKED)
            finally:
                holder.kill()  # simulated SIGKILL: no explicit release runs
                holder.communicate(timeout=5)
            after_crash = BackupLock.acquire(str(config))
            after_crash.release()

    def test_unwritable_or_unsafe_lock_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "backup.toml"
            config.write_text("", encoding="utf-8")
            (Path(str(config) + ".lock")).symlink_to(config)
            with self.assertRaises(SyncerateError) as error:
                BackupLock.acquire(str(config))
            self.assertEqual(error.exception.exit_code, EXIT_LOCK_ERROR)
            self.assertIn("refusing to run unlocked", str(error.exception))
            self.assertEqual(config.read_text(encoding="utf-8"), "")

    def test_duplicate_main_emits_failure_mail_and_nonretained_mqtt_without_touching_original_logs(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            config = root / "syncerate.toml"
            config.write_text("", encoding="utf-8")
            log_dir = root / "logs"
            log_dir.mkdir()
            cfg = make_config(
                config_path=str(config), mail_option="backup@example.test",
                use_mqtt=True, mqtt_json_status=True,
                send_mail_on_success=False, send_mqtt_on_success=False,
                log_destination=str(log_dir) + "/", datetime_format="%Y",
            )
            active_context = create_run_context(cfg)
            active_log = Path(active_context.log_file)
            active_err = Path(active_context.error_file)
            active_out = Path(active_context.output_file)
            for file in (active_log, active_err, active_out):
                file.write_text("ACTIVE RUN MARKER\n", encoding="utf-8")
            original = BackupLock.acquire(str(config))
            try:
                delivered = []
                published = []

                def fake_mail(subject, body, recipient, attachments=None):
                    delivered.append((subject, body, recipient, attachments))
                    return 0, ""

                def fake_mqtt(config, logger, **options):
                    published.append(options)

                with mock.patch("syncerate.app.load_app_config", return_value=cfg), \
                     mock.patch("syncerate.app.load_dataset_pairs") as load_pairs, \
                     mock.patch("syncerate.notifications.send_mail", side_effect=fake_mail), \
                     mock.patch("syncerate.notifications.send_mqtt_messages", side_effect=fake_mqtt), \
                     contextlib.redirect_stdout(io.StringIO()):
                    result = main(["--conf", str(config)])
                self.assertEqual(result, EXIT_BACKUP_LOCKED)
                load_pairs.assert_not_called()
                for file in (active_log, active_err, active_out):
                    self.assertEqual(file.read_text(encoding="utf-8"), "ACTIVE RUN MARKER\n")
                self.assertEqual(len(published), 1)
                self.assertFalse(published[0]["success"])
                self.assertEqual(published[0]["exit_code"], EXIT_BACKUP_LOCKED)
                self.assertIn("Backup already running", published[0]["error_message"])
                self.assertEqual(len(delivered), 1)
                subject, body, recipient, attachments = delivered[0]
                self.assertIn("Backup already running", subject)
                self.assertEqual(recipient, "backup@example.test")
                self.assertIn("Final run summary", body)
                self.assertIn("Total runtime", body)
                self.assertLess(body.index("Total runtime"), body.index("Failure reason"))
                self.assertIn("Backup already running", body)
                self.assertIn(".err file", body)
                self.assertNotIn(".out file", body)  # no Syncoid started
                self.assertGreaterEqual(len(attachments), 2)
                self.assertTrue(all("lock-rejected" in str(a) for a in attachments))
                self.assertTrue(all(Path(a).exists() for a in attachments))
                self.assertNotIn(str(active_log), attachments)
                # The duplicate must NEVER release the original owner's lock.
                with self.assertRaises(SyncerateError) as error:
                    BackupLock.acquire(str(config))
                self.assertEqual(error.exception.exit_code, EXIT_BACKUP_LOCKED)
            finally:
                original.release()

    def test_rejected_run_still_sends_mail_when_failure_logging_is_unavailable(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            config = root / "backup.toml"
            config.write_text("", encoding="utf-8")
            # Deliberately supply an existing regular file as a log directory.
            log_path = root / "not-a-directory"
            log_path.write_text("Do not overwrite me", encoding="utf-8")
            cfg = make_config(
                config_path=str(config), mail_option="ops@example.test",
                log_destination=str(log_path) + "/",
            )
            owner = BackupLock.acquire(str(config))
            try:
                with mock.patch("syncerate.app.load_app_config", return_value=cfg), \
                     mock.patch("syncerate.notifications.send_mail", return_value=(0, "")) as mail, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["-c", str(config)]), EXIT_BACKUP_LOCKED)
                mail.assert_called_once()
                subject, body, recipient = mail.call_args.args[:3]
                self.assertIn("Backup already running", subject)
                self.assertIn("Failure reason", body)
                self.assertEqual(recipient, "ops@example.test")
                self.assertEqual(log_path.read_text(encoding="utf-8"), "Do not overwrite me")
            finally:
                owner.release()

    def test_owner_keeps_lock_until_success_reporting_finishes(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "backup.toml"
            config.write_text("", encoding="utf-8")
            cfg = make_config(config_path=str(config))
            checked = []

            def while_reporting(*args, **kwargs):
                with self.assertRaises(SyncerateError) as conflict:
                    BackupLock.acquire(str(config))
                checked.append(conflict.exception.exit_code)

            with mock.patch("syncerate.app.load_app_config", return_value=cfg), \
                 mock.patch("syncerate.app.load_dataset_pairs", return_value=[]), \
                 mock.patch("syncerate.app.successfull_run", side_effect=while_reporting), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["-c", str(config), "--dry-run"]), 0)
            self.assertEqual(checked, [EXIT_BACKUP_LOCKED])
            next_run = BackupLock.acquire(str(config))
            next_run.release()

    def test_owner_keeps_lock_until_failure_reporting_finishes(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "backup.toml"
            config.write_text("", encoding="utf-8")
            cfg = make_config(config_path=str(config))
            checked = []

            def while_reporting(*args, **kwargs):
                with self.assertRaises(SyncerateError) as conflict:
                    BackupLock.acquire(str(config))
                checked.append(conflict.exception.exit_code)

            with mock.patch("syncerate.app.load_app_config", return_value=cfg), \
                 mock.patch("syncerate.app.load_dataset_pairs", side_effect=SyncerateError("preflight", 1)), \
                 mock.patch("syncerate.app.send_error_mail", side_effect=while_reporting), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["-c", str(config)]), 1)
            self.assertEqual(checked, [EXIT_BACKUP_LOCKED])
            next_run = BackupLock.acquire(str(config))
            next_run.release()

    def test_real_cli_dry_run_creates_and_reuses_lock_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            config = root / "real.toml"
            sources = root / "sources.txt"
            destinations = root / "destinations.txt"
            sources.write_text("pool/share\n", encoding="utf-8")
            destinations.write_text("pool/backup/share\n", encoding="utf-8")
            config.write_text(
                '[syncoid]\nSourceListPath = "' + str(sources) + '"\n'
                'DestListPath = "' + str(destinations) + '"\n'
                'SyncoidCommand = "syncoid SourceDataSet DestDataSet"\n'
                '[ssh]\nPassWord = "No"\n'
                '[mail]\nMail = "No"\n'
                '[logging]\nDateTime = "%Y-%m-%d"\nLogDestination = "No"\n'
                '[runtime]\nSystemAction = "No"\nDryRun = true\n',
                encoding="utf-8",
            )
            source_main = Path(__file__).resolve().parents[1] / "Syncerate.py"
            original = BackupLock.acquire(str(config))
            try:
                process = subprocess.run(
                    [sys.executable, "-B", str(source_main), "-c", str(config)],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(process.returncode, EXIT_BACKUP_LOCKED, process.stdout)
                self.assertIn("Backup already running", process.stdout)
                self.assertNotIn("syncoid pool/share", process.stdout)
            finally:
                original.release()
            process = subprocess.run(
                [sys.executable, "-B", str(source_main), "-c", str(config)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertIn("DRY RUN", process.stdout)
            self.assertTrue(Path(str(config) + ".lock").exists())

    def test_main_lock_setup_error_fails_and_notifies(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "backup.toml"
            config.write_text("", encoding="utf-8")
            (Path(str(config) + ".lock")).symlink_to(config)
            cfg = make_config(config_path=str(config), mail_option="ops@example.test", use_mqtt=True)
            with mock.patch("syncerate.app.load_app_config", return_value=cfg), \
                 mock.patch("syncerate.app.load_dataset_pairs") as lists, \
                 mock.patch("syncerate.notifications.send_mail", return_value=(0, "")) as mail, \
                 mock.patch("syncerate.notifications.send_mqtt_messages") as mqtt, \
                 contextlib.redirect_stdout(io.StringIO()):
                result = main(["-c", str(config), "--dry-run"])
            self.assertEqual(result, EXIT_LOCK_ERROR)
            lists.assert_not_called()
            mail.assert_called_once()
            mqtt.assert_called_once()
            self.assertIn("Backup lock unavailable", mail.call_args.args[0])
            self.assertIn("Final run summary", mail.call_args.args[1])
            self.assertEqual(mqtt.call_args.kwargs["exit_code"], EXIT_LOCK_ERROR)


if __name__ == "__main__":
    unittest.main()
