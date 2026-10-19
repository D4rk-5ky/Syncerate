# Syncerate 0.4.48 verification

## Baseline and scope

Built from the user's original `Syncerate-0.4.47.zip` (43 regular files). The safety change is limited to a per-canonical-TOML lock and its failure-reporting/log-isolation integration, plus source code/documentation/version/test updates. Every baseline file is preserved. See `PACKAGE_MANIFEST.json` for per-file original/release SHA-256, modes and added/modified/unchanged classifications.

## Verification performed

- **158 tests passed**. The 105 tests in `tests.test_app_and_logging`, `tests.test_config`, `tests.test_datasets`, `tests.test_notifications`, `tests.test_packaging`, `tests.test_cli_contract`, `tests.test_system_actions`, and the new `tests.test_locking` passed together. The existing 53 `tests.test_syncoid_runner` tests passed separately in individual subprocesses (40-second per-test bounds; four parallel test workers) to avoid the known environment-dependent Pexpect full-suite hang. This is not a claim of an uninterrupted single-process full-suite pass.
- Real OS-level lock tests verify atomic conflict between processes, relative/symlink aliases resolving to one TOML, independent TOML files, persistent inode reuse after release, post-`SIGKILL` recovery, symlink-unsafe lock denial, no dataset processing on lock denial, error mail/MQTT even with disabled success notifications, distinct duplicate `.log`/`.err` files, and that the first run's log files and ownership survive the rejected run.
- Actual CLI tests loaded a real, valid TOML with `DryRun = true`, saw exit code 13 under a competing owner lock, then exit 0 with dry-run reporting after release. Success/failure stage tests confirm the owner retains the file lock until all requested reporting is complete.
- Python source/test files parsed and compiled; `python3 -B Syncerate.py --version` prints `Syncerate.py 0.4.48`. `--help` documents `--conf`/`-c`, `--dry-run`, `--version`, lock semantics and exit codes. `bash -n build-pyinstaller.sh` passed, and source/build/test version checks agree.
- `config/example-Syncerate.toml` parses with all **31** supported settings matching `CONFIG_OPTION_LOCATIONS`. No runtime configuration option/default/retry policy was added or changed. README retains both user-supplied disclaimers. `commented_code_map.md` explains new lock functions/CLI flow/tests.
- Compared final ZIP file set and modes to every original archive file. Verified every included file hash against the final manifest, no original files were omitted, and the ZIP CRC integrity check completed. Excluded Python caches, bytecode, lock artifacts, log files and temporary outputs.

## Safety and operational limits

- No live ZFS dataset send/receive, full destination, SSH connection, external mail command, MQTT broker or HA notification was used; transports were mocked for notification tests. Delivery remains best-effort and requires real configuration and external services.
- Per-TOML `fcntl.flock` only synchronizes processes that use the same canonical configuration path and compatible local/shared kernel flock semantics. **It does not prevent two distinct TOML configs from targeting the same destination**, and safe locking across different hosts/network filesystems is not established by these tests. Do not delete the persistent `.toml.lock` inode while a backup runs.
- Syncerate's original timestamp-derived log file naming remains unchanged for normal runs. If two **different** TOML files run concurrently with the same `LogDestination` and a colliding `DateTime` format, they can overwrite each other's normal log filenames. Use distinct log destinations for simultaneous jobs. Denied same-TOML launches have uniquely suffixed rejection logs and do not truncate the owner's logs.
- The lock requires create/write permissions in the TOML directory and on the lock file. A read-only/unsafe directory or symlink lock fails closed with exit 14, and configured mail/MQTT failure is attempted.
- The bundled `dist/Syncerate` is the original old **0.4.29** PyInstaller binary, **not** a 0.4.48 build; it does **not** implement the lock feature. PyInstaller packaging dependencies were unavailable so no replacement binary was built. Use the **0.4.48 Python source** or install the requirements and run `./build-pyinstaller.sh` on a compatible Linux build host to produce the current standalone executable.
