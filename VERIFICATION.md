# Syncerate 0.4.37 verification

## Release scope

The immediate baseline for this release is Syncerate `0.4.36`. This release increments exactly one patch step to `0.4.37`.

This release fixes the missing-dataset/pool runtime path reported from a real Syncoid receive. Dataset-list preflight, normal successful replication, Broken Pipe retry policy, SSH credential handling, notification routing, and normal fatal-error handling remain unchanged.

The reported run validated all configured source/destination suffixes, then Syncoid reported a missing destination parent dataset. Syncerate recognized the missing-data failure but only wrote its generic interpretation to the `.err` log and could wait indefinitely for the already-failed Syncoid/mbuffer/SSH pipeline to finish before the outer dataset loop regained control.

Version 0.4.37 therefore makes two narrow changes:

- relevant raw Syncoid/ZFS/mbuffer output around a recognized missing-data failure is copied into normal ERROR logging, so it is present in the `.err` log as well as the complete raw `.out` stream;
- after a definitive non-warning missing dataset/pool diagnostic, Syncoid receives a fixed 5-second cleanup window. If the failed child remains stuck, Syncerate stops only that failed attempt, records the pair as failed, and continues to the next configured pair. Authentication, connection, permission, and unrelated failures retain their fatal behavior.

No user configuration option or CLI flag was added or renamed.

## Checks completed

- Confirmed the source CLI reports `Syncerate.py 0.4.37` with `--version`.
- Confirmed `--help` exits successfully and documents `--conf`/`-c`, `--help`/`-h`, and `--version`.
- Confirmed invocation without the required config, an unknown flag, and a missing config file each return exit code `2`.
- Confirmed importing `Syncerate.py` is silent and does not start application work.
- Compiled all 21 Python source/test files successfully with `compileall`.
- `bash -n build_pyinstaller.sh` passed.
- All 116 regression tests passed when run in bounded groups: 69 application/config/dataset/notification/packaging/system-action tests plus all 47 Syncoid-runner tests. One larger Syncoid batch exceeded the execution environment's per-command time ceiling while its last test was running; that test and the remaining tests were rerun in smaller groups and all passed.
- Added a regression using the real failure shape: mbuffer warning, `cannot open ... dataset does not exist`, and `cannot receive new filesystem stream: unable to restore to destination`. It verifies the raw context is copied to `.err` and that a later pair runs.
- Added a regression whose failed Syncoid child intentionally sleeps for 30 seconds after the missing-dataset line. With the cleanup timeout shortened only inside the test, Syncerate terminates that already-failed attempt and executes the next pair.
- Confirmed the shipped example config still contains 29 unique configuration keys and every key is documented in the current README.
- Confirmed the existing executable permissions are preserved for `Syncerate.py`, `build_pyinstaller.sh`, and `dist/Syncerate`.
- The final release tree preserves the same 41 regular-file paths as 0.4.36; no baseline project file is removed and no new runtime file is required.
- `PACKAGE_MANIFEST.json` is regenerated from the 0.4.36 baseline versus the final 0.4.37 tree using SHA-256 hashes and stored Unix modes, with the manifest's own release hash excluded to avoid self-reference.
- Packaging cleanup removes `__pycache__`, `.pyc`, `.pyo`, build cache/output created during verification, and temporary files before the final ZIP is produced.

## Standalone executable limitation

The preserved `dist/Syncerate` executable still reports `Syncerate 0.4.29`. It is an original project file and is **not** a 0.4.37 executable.

This verification environment does not contain PyInstaller or Paho MQTT, so the standalone executable cannot be rebuilt here without installing dependencies. Use the 0.4.37 Python source entry point, or rebuild `dist/Syncerate` on a compatible Linux host with `build_pyinstaller.sh` before treating the standalone executable as version 0.4.37.

## What was not fully tested

No live ZFS pool, real Syncoid replication, remote SSH host, production MQTT broker/Home Assistant instance, local mail delivery, or real post-success system action was exercised. Those paths are covered by the regression suite using controlled child processes and mocked/stubbed external integrations.

The real uploaded log was used to reproduce the missing-parent output pattern, but the exact remote host/pool state from that production run was not modified or replayed.

The PyInstaller build itself was not executed because its required modules are unavailable in this environment. Platform-specific behavior of a newly rebuilt frozen executable therefore remains to be verified on the target build host.
