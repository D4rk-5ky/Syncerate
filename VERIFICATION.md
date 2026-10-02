# Syncerate 0.4.39 verification

## Release scope

The supplied baseline archive for this change was Syncerate `0.4.38` (`Syncerate-0.4.38.zip`, SHA-256 `cb537768a474eb62cf28aeec3e849364da821933e538e0afc1071c8fdf91d845`). This release increments exactly one patch step to `0.4.39`.

Version 0.4.39 makes dry-run a real settings-file option:

- `[Syncerate Config]` now supports strict Boolean `DryRun`.
- `DryRun = False` is the default and performs a normal replication run.
- `DryRun = True` activates the safe planning/report mode without requiring a CLI flag.
- `--dry-run` remains available as a one-way override that can force dry-run on even when the config says `False`; it never disables `DryRun = True`.
- Dry-run safety remains unchanged: no password/passphrase resolution, private ssh-agent startup, Syncoid child process, data transfer, or `SystemAction` execution.
- `SendMailOnSuccess` and `SendMQTTOnSuccess` still control successful notifications for both real and dry runs. Configured failure notifications remain independent of those success switches.

The shipped example configuration now contains `DryRun = False` with comments explaining both values and the CLI override.

## Checks completed

- Confirmed `python3 Syncerate.py --version` reports `Syncerate.py 0.4.39`.
- Confirmed `python3 Syncerate.py --help` exits successfully and documents `--conf`/`-c`, `--dry-run`, `--help`/`-h`, `--version`, and that `--dry-run` forces dry-run on even when `DryRun = False` in the config.
- Confirmed invoking without the required `--conf`/`-c` remains an argparse error.
- Confirmed `config/example-Syncerate.cfg` loads successfully, contains all 30 current configuration options, and resolves `DryRun = False` to `AppConfig.dry_run == False`.
- Confirmed omitted `DryRun` defaults to false and every documented Boolean spelling (`Yes/No`, `True/False`, `1/0`, `On/Off`, case-insensitive) is accepted; typo values are rejected before replication.
- Ran a source-mode config-driven dry-run with `DryRun = True`, `PassWord = Ask`, a configured `SystemAction`, and a fake Syncoid executable that would create a marker if started. The run returned `0`, printed `Dry run report`, printed `NO REPLICATION WAS PERFORMED`, printed the final `DRY RUN` summary, skipped `SystemAction`, and did not create the fake-child marker.
- Verified the existing CLI `--dry-run` path still activates the same safe mode when the config setting is false or omitted.
- Compiled `Syncerate.py`, all `syncerate/*.py`, and all tests successfully with `python3 -m compileall -q`.
- `bash -n build_pyinstaller.sh` passed.
- All 125 regression tests passed:
  - 22 `test_app_and_logging` tests;
  - 22 `test_config` tests;
  - 8 `test_datasets` tests;
  - 20 `test_notifications` tests;
  - 3 `test_packaging` tests;
  - 47 `test_syncoid_runner` tests;
  - 3 `test_system_actions` tests.
- The Syncoid suite was run in bounded groups because one long batch reached the environment command-time ceiling while a slow fake-child test was still running. The remaining tests were rerun separately and all passed; no assertion failure was observed.
- Audited Python AST symbols against `commented_code_map.md`; all 231 production/test classes and functions are represented.
- Confirmed the README documents all 30 options present in the shipped example configuration, including `DryRun`.
- Confirmed executable modes remain preserved for `Syncerate.py`, `build_pyinstaller.sh`, and `dist/Syncerate`.
- Packaging cleanup removes `__pycache__`, `.pyc`, `.pyo`, build caches, and temporary verification files before the final ZIP is produced.
- `PACKAGE_MANIFEST.json` is regenerated against the supplied 0.4.38 baseline using SHA-256 hashes and stored Unix modes, with the manifest's own release hash excluded to avoid self-reference.

## Standalone executable limitation

The preserved `dist/Syncerate` executable still reports `Syncerate 0.4.29`. It is an original project file and is **not** a 0.4.39 executable.

This verification environment has `pexpect 4.9.0`, but does not have PyInstaller or Paho MQTT installed. The standalone executable therefore cannot be rebuilt and honestly verified here. Use the 0.4.39 Python source entry point, or rebuild `dist/Syncerate` on a compatible Linux host with `build_pyinstaller.sh` before treating the standalone executable as version 0.4.39.

## What was not fully tested

No live ZFS pool, real Syncoid replication, remote SSH host, production MQTT broker/Home Assistant instance, local mail server/delivery path, or real post-success `SystemAction` was exercised. Those paths are covered by regression tests using controlled fake child processes and mocked/stubbed external integrations.

The dry-run implementation deliberately does not query live ZFS state, remote reachability, permissions, available destination space, or real Syncoid behavior; a successful dry run proves configuration/list/command planning, not that a later real replication will succeed.

The PyInstaller build itself was not executed because required build/runtime modules are unavailable in this environment. Platform-specific behavior of a newly rebuilt frozen executable therefore remains to be verified on the target build host.
