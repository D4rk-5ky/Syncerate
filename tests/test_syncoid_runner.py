import shlex
import tempfile
import unittest
from pathlib import Path

from syncerate.errors import (
    EXIT_DATASET_MISSING,
    EXIT_PASSWORD_DENIED,
    EXIT_REPEATED_PATTERN,
    EXIT_WARNING,
    SyncerateError,
)
from syncerate.models import DatasetPair
from syncerate.logging_setup import create_run_context
from syncerate.syncoid_runner import (
    TransferByteCounter,
    build_syncoid_command,
    extract_ssh_key_path,
    pv_amount_to_bytes,
    private_ssh_agent,
    run_replications,
    send_secret,
)
from tests.helpers import make_config, make_logger, no_logging_context, write_executable


class SyncoidRunnerTests(unittest.TestCase):
    def test_pv_amount_to_bytes_handles_binary_decimal_and_comma_decimal(self):
        self.assertEqual(pv_amount_to_bytes("64.0", "KiB"), 64 * 1024)
        self.assertEqual(pv_amount_to_bytes("1,5", "GiB"), round(1.5 * 1024**3))
        self.assertEqual(pv_amount_to_bytes("2.5", "GB"), 2_500_000_000)

    def test_transfer_counter_sums_maximum_progress_per_syncoid_stream(self):
        counter = TransferByteCounter()
        counter.feed(
            "INFO: Sending oldest full snapshot pool/a@snap (~ 1 MB) to new target filesystem:\r\n"
            "64.0KiB 0:00:00 [1.0MiB/s] [==> ] 6%\r"
            "1.00MiB 0:00:01 [1.0MiB/s] [====] 100%\r\n"
            "INFO: Updating new target filesystem with incremental pool/a@old ... new (~ 2 MB):\r\n"
            "512KiB 0:00:00 [2.0MiB/s] [=> ] 25%\r"
            "1,50MiB 0:00:01 [2.0MiB/s] [====] 100%\r\n"
        )
        transferred_bytes, complete = counter.finish()
        self.assertTrue(complete)
        self.assertEqual(transferred_bytes, round(2.5 * 1024**2))

    def test_transfer_counter_marks_started_stream_without_pv_bytes_incomplete(self):
        counter = TransferByteCounter()
        counter.feed(
            "INFO: Sending incremental pool/a@s1 ... s2 (~ 1 MB):\r\n"
            "transfer output without pv byte counter\r\n"
        )
        transferred_bytes, complete = counter.finish()
        self.assertEqual(transferred_bytes, 0)
        self.assertFalse(complete)

    def test_build_command_preserves_dataset_spaces_and_extra_args(self):
        command = build_syncoid_command(
            "syncoid remote:SourceDataSet DestDataSet --compress none",
            "pool/Data Set",
            "backup/Data Set",
            ["--identifier", "nightly backup"],
        )
        self.assertEqual(command[0], "syncoid")
        self.assertIn("remote:pool/Data Set", command)
        self.assertIn("backup/Data Set", command)
        self.assertEqual(command[-2:], ["--identifier", "nightly backup"])

    def test_build_command_rejects_missing_placeholders(self):
        with self.assertRaises(ValueError):
            build_syncoid_command("syncoid pool/a pool/b", "pool/a", "pool/b")

    def test_send_secret_refuses_when_expected_noecho_never_activates(self):
        class Child:
            def __init__(self):
                self.logfile = "attached"
                self.sent = []

            def waitnoecho(self, timeout):
                self.timeout = timeout
                return False

            def sendline(self, value):
                self.sent.append(value)

        child = Child()
        output_handle = object()
        child.logfile = output_handle

        with self.assertRaises(SyncerateError) as caught:
            send_secret(child, "secret", output_handle, True)

        self.assertEqual(caught.exception.exit_code, EXIT_PASSWORD_DENIED)
        self.assertEqual(child.sent, [])
        self.assertIs(child.logfile, output_handle)

    def test_extract_ssh_key_path_supports_both_forms_and_last_value(self):
        self.assertEqual(
            extract_ssh_key_path(
                "syncoid SourceDataSet DestDataSet --sshkey first --sshkey=second"
            ),
            "second",
        )

    def test_private_agent_disabled_yields_none(self):
        cfg = make_config(use_ssh_agent=False)
        with private_ssh_agent(cfg, None, make_logger("agent-disabled")) as session:
            self.assertIsNone(session)

    def run_fake(self, body: str, *, command_prefix: str = "", logger=None, **config_overrides):
        with tempfile.TemporaryDirectory() as td:
            script = write_executable(Path(td) / "fake_syncoid.py", body)
            template = (
                f"{shlex.quote(script)} {command_prefix} SourceDataSet DestDataSet"
            ).strip()
            cfg = make_config(syncoid_command=template, **config_overrides)
            return run_replications(
                cfg,
                no_logging_context(),
                [DatasetPair("pool/data", "backup/data", ())],
                None,
                logger if logger is not None else make_logger("fake-run"),
            )

    def test_missing_destroy_message_does_not_mask_unrelated_nonzero_exit(self):
        with self.assertRaises(SyncerateError) as cm:
            self.run_fake(
                "import sys\n"
                "print('could not find any snapshots to destroy; check snapshot names.', flush=True)\n"
                "print('unrelated fatal failure', flush=True)\n"
                "sys.exit(42)\n"
            )
        self.assertEqual(cm.exception.exit_code, 42)
        self.assertEqual(cm.exception.kind, "syncoid")

    def test_missing_destroy_message_is_nonfatal_when_syncoid_exits_zero(self):
        summary = self.run_fake(
            "print('could not find any snapshots to destroy; check snapshot names.', flush=True)\n"
        )
        self.assertFalse(summary.has_broken_pipe_warning)


    def test_openssh_permanently_added_known_host_warning_is_nonfatal(self):
        summary = self.run_fake(
            "print(\"Warning: Permanently added '10.0.0.135' (ED25519) to the list of known hosts.\", flush=True)\n"
        )
        self.assertFalse(summary.has_missing_dataset_failure)

    def test_missing_dataset_exit_two_is_recorded_and_list_continues(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "good-ran"
            script = write_executable(
                Path(td) / "fake_syncoid.py",
                "import pathlib, sys\n"
                f"marker = pathlib.Path({str(marker)!r})\n"
                "if sys.argv[1].endswith('/missing'):\n"
                "    print(\"CRITICAL ERROR: cannot open 'pool/missing': dataset does not exist\", flush=True)\n"
                "    sys.exit(2)\n"
                "marker.write_text('yes')\n",
            )
            cfg = make_config(
                syncoid_command=f"{shlex.quote(script)} SourceDataSet DestDataSet"
            )
            pairs = [
                DatasetPair("pool/missing", "backup/missing", ()),
                DatasetPair("pool/good", "backup/good", ()),
            ]
            summary = run_replications(
                cfg,
                no_logging_context(),
                pairs,
                None,
                make_logger("missing-continue"),
            )

            self.assertTrue(marker.exists())
            self.assertTrue(summary.has_missing_dataset_failure)
            self.assertEqual(len(summary.missing_dataset_failures), 1)
            failure = summary.missing_dataset_failures[0]
            self.assertEqual(failure.dataset_pair, pairs[0])
            self.assertIn("dataset does not exist", "\n".join(failure.messages))

    def test_missing_pool_exit_two_is_recorded(self):
        summary = self.run_fake(
            "import sys\n"
            "print(\"cannot open 'missingpool': no such pool\", flush=True)\n"
            "sys.exit(2)\n"
        )
        self.assertTrue(summary.has_missing_dataset_failure)
        self.assertIn(
            "no such pool",
            "\n".join(summary.missing_dataset_failures[0].messages),
        )


    def test_missing_pool_import_message_is_recorded(self):
        summary = self.run_fake(
            "import sys\n"
            "print(\"cannot import 'missingpool': no such pool available\", flush=True)\n"
            "sys.exit(2)\n"
        )
        self.assertTrue(summary.has_missing_dataset_failure)
        self.assertIn(
            "no such pool available",
            "\n".join(summary.missing_dataset_failures[0].messages),
        )

    def test_skipping_dataset_warnings_are_ignored(self):
        for warning in (
            "WARNING: Skipping dataset for another reason",
            "WARNING: Skipping dataset (dataset no longer exists): pool/data...",
        ):
            with self.subTest(warning=warning):
                summary = self.run_fake(f"print({warning!r}, flush=True)\n")
                self.assertFalse(summary.has_missing_dataset_failure)

    def test_missing_dataset_text_does_not_mask_unrelated_exit_code(self):
        with self.assertRaises(SyncerateError) as caught:
            self.run_fake(
                "import sys\n"
                "print(\"cannot open 'pool/data': dataset does not exist\", flush=True)\n"
                "print('later unrelated fatal error', flush=True)\n"
                "sys.exit(42)\n"
            )
        self.assertEqual(caught.exception.exit_code, 42)
        self.assertEqual(caught.exception.kind, "syncoid")

    def test_generic_warnings_are_ignored(self):
        for prefix in ("WARN:", "WARNING:", "Warning:", "WARN ", "  warning:"):
            with self.subTest(prefix=prefix):
                summary = self.run_fake(f"print({prefix + ' synthetic warning'!r}, flush=True)\n")
                self.assertFalse(summary.has_missing_dataset_failure)
                self.assertFalse(summary.has_broken_pipe_warning)

    def test_repeated_normal_sending_progress_is_not_mistaken_for_a_loop(self):
        body = "for _ in range(8): print('INFO: Sending incremental', flush=True)\n"
        summary = self.run_fake(body)
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_run_replications_collects_actual_pv_bytes_across_streams(self):
        summary = self.run_fake(
            "print('INFO: Sending oldest full snapshot pool/data@s1 (~ 1 MB) to new target filesystem:', flush=True)\n"
            "print('512KiB 0:00:00 [1.0MiB/s] [=> ] 50%', flush=True)\n"
            "print('1.00MiB 0:00:01 [1.0MiB/s] [====] 100%', flush=True)\n"
            "print('INFO: Updating new target filesystem with incremental pool/data@s1 ... s2 (~ 2 MB):', flush=True)\n"
            "print('1,50MiB 0:00:01 [2.0MiB/s] [====] 100%', flush=True)\n"
        )
        self.assertTrue(summary.transfer_measurement_complete)
        self.assertEqual(summary.transferred_bytes, round(2.5 * 1024**2))

    def test_exact_resume_unavailable_warning_remains_nonfatal(self):
        summary = self.run_fake(
            "print('WARN: ZFS resume feature not available on source and target machines - sync will continue without resume support.', flush=True)\n"
        )
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_resume_unavailable_can_stop_or_continue(self):
        for label in ("WARN", "WARNING", "Warning"):
            for machine in ("source machine", "target machine", "source and target machines"):
                warning = f"{label}: ZFS resume feature not available on {machine} - sync will continue without resume support."
                with self.subTest(warning=warning):
                    body = f"print({warning!r}, flush=True)\n"
                    logger = make_logger("resume-warning-test")
                    with self.assertLogs(logger, level="WARNING") as logs:
                        self.run_fake(body, continue_without_resume=True, logger=logger)
                    self.assertTrue(any(warning in message for message in logs.output))
                    with self.assertRaises(SyncerateError) as caught:
                        self.run_fake(body + "import time; time.sleep(10)\n", continue_without_resume=False)
                    self.assertEqual(caught.exception.exit_code, EXIT_WARNING)
                    self.assertIn("ContinueWithoutResume", caught.exception.message)

    def test_continue_without_resume_preserves_real_nonzero_exit(self):
        with self.assertRaises(SyncerateError) as caught:
            self.run_fake(
                "import sys\n"
                "print('WARN: ZFS resume feature not available on target machine', flush=True)\n"
                "sys.exit(42)\n", continue_without_resume=True,
            )
        self.assertEqual(caught.exception.exit_code, 42)

    def test_warning_error_words_do_not_trigger_error_or_prompt_handlers(self):
        warnings = [
            "WARNING: Permission denied",
            "WARNING: Connection timed out",
            "WARNING: Connection refused",
            "WARN: Broken pipe",
            "WARNING: cannot open 'pool/data': dataset does not exist",
            "WARNING: Are you sure you want to continue connecting",
            "WARNING: Enter passphrase for key '/tmp/test':",
            "WARNING: user@example.test's password:",
            "WARN: zfs destroy failed: 256",
        ]
        body = "\n".join(f"print({line!r}, flush=True)" for line in warnings) + "\n"
        logger = make_logger("ignored-warning-test")
        with self.assertNoLogs(logger, level="WARNING"):
            summary = self.run_fake(body, retry_broken_pipe=True, logger=logger)
        self.assertFalse(summary.has_missing_dataset_failure)
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_warning_chunks_and_unterminated_warning_are_consumed(self):
        summary = self.run_fake(
            "import sys, time\n"
            "for chunk in ('WARN', 'ING:', ' Permission denied; ', 'Broken pipe'):\n"
            "    sys.stdout.write(chunk); sys.stdout.flush(); time.sleep(0.03)\n",
            retry_broken_pipe=True,
        )
        self.assertFalse(summary.has_broken_pipe_warning)
        self.assertFalse(summary.has_missing_dataset_failure)

    def test_ignored_warnings_remain_in_raw_log_without_affecting_transfer_count(self):
        with tempfile.TemporaryDirectory() as td:
            warning = "WARNING: INFO: Sending full is only a diagnostic example"
            script = write_executable(Path(td) / "fake.py", f"print({warning!r}, flush=True)\n")
            cfg = make_config(
                syncoid_command=f"{shlex.quote(script)} SourceDataSet DestDataSet",
                log_destination=td + "/",
            )
            context = create_run_context(cfg)
            summary = run_replications(
                cfg, context, [DatasetPair("pool/data", "backup/data", ())],
                None, make_logger("raw-warning-log"),
            )
            self.assertIn(warning, Path(context.output_file).read_text())
            self.assertTrue(summary.transfer_measurement_complete)
            self.assertEqual(summary.transferred_bytes, 0)

    def test_resume_warning_chunks_are_checked_at_eof(self):
        with self.assertRaises(SyncerateError) as caught:
            self.run_fake(
                "import sys, time\n"
                "for chunk in ('WARN:', ' ZFS resume feature ', 'not available on source machine'):\n"
                "    sys.stdout.write(chunk); sys.stdout.flush(); time.sleep(0.03)\n",
                continue_without_resume=False,
            )
        self.assertEqual(caught.exception.exit_code, EXIT_WARNING)

    def test_nonwarning_errors_after_warning_still_fail(self):
        for error, code in (("Permission denied", 5), ("Connection timed out", 6), ("Connection refused", 7)):
            with self.subTest(error=error):
                with self.assertRaises(SyncerateError) as caught:
                    self.run_fake(
                        "print('WARN: an ignored warning', flush=True)\n"
                        f"print({error!r}, flush=True)\n"
                    )
                self.assertEqual(caught.exception.exit_code, code)

    def test_ignored_warning_preserves_exit_and_signal_failures(self):
        for ending, expected in (("sys.exit(42)", 42), ("os.kill(os.getpid(), signal.SIGTERM)", 143)):
            with self.subTest(ending=ending):
                with self.assertRaises(SyncerateError) as caught:
                    self.run_fake(
                        "import os, signal, sys\n"
                        "print('WARNING: synthetic warning', flush=True)\n" + ending + "\n"
                    )
                self.assertEqual(caught.exception.exit_code, expected)

    def test_missing_dataset_warning_alone_does_not_reclassify_exit_two(self):
        with self.assertRaises(SyncerateError) as caught:
            self.run_fake(
                "import sys\n"
                "print('WARNING: Skipping dataset (dataset no longer exists): pool/data...', flush=True)\n"
                "sys.exit(2)\n"
            )
        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(caught.exception.kind, "syncoid")

    def test_nonwarning_missing_dataset_after_warning_is_still_recorded(self):
        summary = self.run_fake(
            "import sys\n"
            "print('WARNING: Skipping dataset for another reason', flush=True)\n"
            "print(\"cannot open 'pool/data': dataset does not exist\", flush=True)\n"
            "sys.exit(2)\n"
        )
        self.assertTrue(summary.has_missing_dataset_failure)

    def test_reset_warning_preserves_nonwarning_broken_pipe_recovery(self):
        summary = self.run_fake(
            "print('WARNING: resetting partially receive state because the snapshot source no longer exists', flush=True)\n"
            "print('Broken pipe', flush=True)\n"
            "print('INFO: Sending full', flush=True)\n",
            retry_broken_pipe=True,
        )
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_fresh_send_restores_nonwarning_broken_pipe_retry_handling(self):
        summary = self.run_fake(
            "import time\n"
            "print('WARN: resetting partially receive state because the snapshot source no longer exists', flush=True)\n"
            "print('INFO: Sending full', flush=True)\n"
            "print('Broken pipe', flush=True)\n"
            "time.sleep(10)\n",
            retry_broken_pipe=True, broken_pipe_retry_count=0,
        )
        self.assertTrue(summary.has_broken_pipe_warning)


    def test_benign_password_word_in_output_does_not_trigger_secret_prompt(self):
        summary = self.run_fake(
            "print('processing pool/password-archive', flush=True)\n"
        )
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_benign_warnings_word_is_not_treated_as_warn_line(self):
        summary = self.run_fake(
            "print('WARNINGS dataset summary', flush=True)\n"
        )
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_actual_passphrase_prompt_with_password_disabled_fails_code_5(self):
        with self.assertRaises(SyncerateError) as cm:
            self.run_fake(
                "print(\"Enter passphrase for key '/tmp/id_test':\", end='', flush=True)\n"
                "input()\n"
            )
        self.assertEqual(cm.exception.exit_code, EXIT_PASSWORD_DENIED)

    def test_typical_openssh_password_prompt_with_password_disabled_fails_code_5(self):
        with self.assertRaises(SyncerateError) as caught:
            self.run_fake('print("user@example.test\'s password:", end="", flush=True); input()\n')
        self.assertEqual(caught.exception.exit_code, 5)

    def test_password_prompt_with_password_disabled_fails_code_5(self):
        with self.assertRaises(SyncerateError) as cm:
            self.run_fake(
                "print('user@example password:', end='', flush=True)\n"
                "input()\n"
            )
        self.assertEqual(cm.exception.exit_code, EXIT_PASSWORD_DENIED)

    def test_broken_pipe_disabled_preserves_real_nonzero_exit(self):
        with self.assertRaises(SyncerateError) as cm:
            self.run_fake(
                "import sys\n"
                "print('Broken pipe', flush=True)\n"
                "sys.exit(23)\n",
                retry_broken_pipe=False,
            )
        self.assertEqual(cm.exception.exit_code, 23)

    def test_broken_pipe_retry_count_is_per_dataset_and_exhaustion_is_warning_success(self):
        with tempfile.TemporaryDirectory() as td:
            counter = Path(td) / "counter"
            script = write_executable(
                Path(td) / "broken_pipe.py",
                "import pathlib, sys, time\n"
                "p = pathlib.Path(sys.argv[1])\n"
                "n = int(p.read_text()) + 1 if p.exists() else 1\n"
                "p.write_text(str(n))\n"
                "print('Broken pipe', flush=True)\n"
                "time.sleep(30)\n",
            )
            template = (
                f"{shlex.quote(script)} {shlex.quote(str(counter))} "
                "SourceDataSet DestDataSet"
            )
            cfg = make_config(
                syncoid_command=template,
                retry_broken_pipe=True,
                broken_pipe_retry_count=1,
                broken_pipe_retry_wait_seconds=0,
            )
            pair = DatasetPair("pool/data", "backup/data", ())
            summary = run_replications(
                cfg,
                no_logging_context(),
                [pair],
                None,
                make_logger("broken-pipe-retry"),
            )
            self.assertTrue(summary.has_broken_pipe_warning)
            self.assertEqual(summary.broken_pipe_failed_datasets, [pair])
            self.assertEqual(counter.read_text(), "2")

    def test_repeated_host_key_prompt_fails_code_9(self):
        with self.assertRaises(SyncerateError) as cm:
            self.run_fake(
                "for _ in range(6):\n"
                "    print('Are you sure you want to continue connecting', flush=True)\n"
                "    input()\n"
            )
        self.assertEqual(cm.exception.exit_code, EXIT_REPEATED_PATTERN)


if __name__ == "__main__":
    unittest.main()
