"""Safe subprocess/argument-contract smoke tests for the source CLI."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from syncerate import VERSION
from syncerate.cli import parse_arguments


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CLIContractTests(unittest.TestCase):
    """Protect CLI behavior without touching ZFS, SSH, mail, or MQTT."""

    def run_source_cli(self, *args):
        """Invoke the real entry point from an empty directory without bytecode output."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            completed = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "Syncerate.py"), *args],
                cwd=temporary_directory,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            self.assertEqual(list(Path(temporary_directory).iterdir()), [])
            return completed

    def test_version_works_without_configuration_or_side_effects(self):
        """Version selection exits before config reading or replication startup."""
        completed = self.run_source_cli("--version")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), f"Syncerate.py {VERSION}")
        self.assertFalse(completed.stderr.strip())

    def test_help_works_without_configuration_or_side_effects(self):
        """Help documents supported switches without loading any configuration."""
        completed = self.run_source_cli("--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for expected in ("--conf", "-c", "--dry-run", "--help", "--version", "credentials", "SystemAction"):
            self.assertIn(expected, completed.stdout)

    def test_missing_config_and_unknown_options_are_rejected(self):
        """argparse prevents unconfigured/invalid invocations reaching runtime."""
        for args in ((), ("--unknown",)):
            with self.subTest(args=args):
                completed = self.run_source_cli(*args)
                self.assertEqual(completed.returncode, 2)
                self.assertIn("--conf", completed.stderr)

    def test_short_and_long_config_and_one_way_dry_run_parsing(self):
        """Short/long config flags are equivalent; dry-run defaults false."""
        short = parse_arguments(["-c", "example.toml"])
        long = parse_arguments(["--conf", "example.toml", "--dry-run"])
        self.assertEqual(short.conf, long.conf)
        self.assertFalse(short.dry_run)
        self.assertTrue(long.dry_run)


if __name__ == "__main__":
    unittest.main()
