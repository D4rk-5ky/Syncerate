import shlex
import tempfile
import unittest
from pathlib import Path

from syncerate.errors import (
    EXIT_PASSWORD_DENIED,
    EXIT_REPEATED_PATTERN,
    EXIT_WARNING,
    SyncerateError,
)
from syncerate.models import DatasetPair
from syncerate.syncoid_runner import (
    build_syncoid_command,
    extract_ssh_key_path,
    private_ssh_agent,
    run_replications,
    send_secret,
)
from tests.helpers import make_config, make_logger, no_logging_context, write_executable


class SyncoidRunnerTests(unittest.TestCase):
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

    def run_fake(self, body: str, *, command_prefix: str = "", **config_overrides):
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
                make_logger("fake-run"),
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

    def test_generic_warning_remains_fatal(self):
        with self.assertRaises(SyncerateError) as cm:
            self.run_fake("print('WARNING: synthetic warning', flush=True)\n")
        self.assertEqual(cm.exception.exit_code, EXIT_WARNING)

    def test_repeated_normal_sending_progress_is_not_mistaken_for_a_loop(self):
        body = "for _ in range(8): print('INFO: Sending incremental', flush=True)\n"
        summary = self.run_fake(body)
        self.assertFalse(summary.has_broken_pipe_warning)

    def test_exact_resume_unavailable_warning_remains_nonfatal(self):
        summary = self.run_fake(
            "print('WARN: ZFS resume feature not available on source and target machines - sync will continue without resume support.', flush=True)\n"
        )
        self.assertFalse(summary.has_broken_pipe_warning)


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
