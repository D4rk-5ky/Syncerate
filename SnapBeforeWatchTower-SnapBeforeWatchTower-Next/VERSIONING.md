# Versioning and complete change log

`SnapBeforeWatchTower.py::__version__` is the application version embedded in release metadata and MQTT reports. The current release is 0.0.6. The public application interface remains TOML-only with `-c CONFIG` as its single public CLI option.

Each new created release advances by one patch step. The patch component ranges from 0 through 99: `0.0.98 -> 0.0.99 -> 0.1.0 -> 0.1.1`. Never emit `0.0.100`. Do not invent releases for intermediate edits while preparing a single release. Update this file with every release and record every code change, documentation change, and added file. Keep README.md focused on current usage and keep configuration examples and commented_code_map.md synchronized.

## 0.0.6 — 2026-09-25

### Application code and behavior

- Bump the application version from 0.0.5 to 0.0.6 so MQTT release metadata identifies this behavior release.
- Add `MissingDatasetsError` as an aggregate final failure used only after the script has processed all remaining configured datasets and normal log cleanup following one or more missing-dataset errors.
- Add `is_missing_dataset_error()` to classify captured ZFS stderr conservatively. It recognizes `dataset does not exist` and `no such pool or dataset`; unrelated ZFS errors are not continuable.
- Add `remember_missing_dataset()` to record each missing dataset once and log that processing will continue with later datasets.
- In `create` mode, catch missing-dataset failures from both `zfs snapshot` (`subprocess.CalledProcessError`) and retention `zfs list` (`CommandError`) around each dataset. Skip only that dataset, continue later datasets, then run normal log cleanup.
- In `delete` mode, catch the same missing-dataset condition from the per-dataset snapshot listing, continue later datasets, then run normal log cleanup.
- After remaining work finishes, raise `MissingDatasetsError` so the process still has a failure outcome. Failure mail is sent when mail is enabled, with a dedicated `SnapBeforeWatchTower FAILED - missing dataset` subject and introductory text naming the reason. `on_success=true` does not cause an additional success mail for this run.
- Preserve the MQTT schema and Home Assistant contract: no new status/event is introduced. Missing-dataset runs publish `status: "failure"`, `exit_code: 1`, and keep `warning: false`; the existing `error` field now names the missing dataset(s) and says `dataset does not exist`, while `stderr` retains bounded current-run error detail.
- Preserve the immediate-abort safety behavior for every non-missing ZFS error such as permission failures. No retention selection, snapshot naming, destroy safety, Docker behavior, root enforcement, TOML schema, MQTT publish/QoS/retain/TLS behavior, or dry-run mutation boundary is changed.

### Documentation, tests, integration, and packaging

- Update README.md for current behavior only: missing-dataset continuation, final failure/mail behavior, unchanged MQTT success/failure contract, and the distinction between continuable missing datasets and immediately fatal unrelated ZFS errors.
- Update `config-example.toml` and `config.example.md` to describe the missing-dataset behavior without adding any new configuration setting. All existing settings and the single public `-c CONFIG` option remain unchanged.
- Update `commented_code_map.md` for the new exception/helpers, run coordination, and regression tests.
- Add regression coverage for exact missing-dataset stderr classification, create-mode continuation plus failure mail, delete-mode continuation, unrelated-error immediate abort, and the unchanged MQTT failure schema/reason.
- Update MQTT regression fixture version strings to 0.0.6.
- Keep the supplied Home Assistant automation control flow unchanged because it already branches on `status == "success"` and `status == "failure"` and displays the existing `error`/`stderr` fields.
- Keep `SAFETY.md` and its disclaimer/liability/data-loss notices unchanged.
- Refresh `VERIFICATION.md` and package a clean release ZIP with all original project paths and no Python/cache/build/temp artifacts.

## 0.0.5 — 2026-09-25

### Application code and behavior

- Bump the application version from 0.0.4 to 0.0.5 so MQTT release metadata identifies this maintenance release.
- Update MQTT regression-test sample version strings from 0.0.4 to 0.0.5 so test fixtures match the current release metadata.
- No ZFS snapshot creation/deletion logic, retention selection, Docker digest behavior, root enforcement, mail behavior, MQTT validation/publish behavior, dry-run semantics, operation order, or destructive-operation safety boundaries changed.

### Configuration, documentation, integration, and packaging

- Repair the stale `config.example.md` that was present in the supplied 0.0.4 archive even though the 0.0.4 history/verification described it as removed. Preserve the path rather than deleting it and rewrite it as a current supplemental TOML reference.
- Document the single public `-c CONFIG` option and every supported `[application]`, `[mail]`, and `[mqtt]` setting in `config.example.md`; remove obsolete multi-flag and `mqtt.json` instructions from that file.
- Keep `config-example.toml` as the loadable fully commented example; add README/setup guidance to copy `datasets.example.txt` to the configured dataset filename before first use.
- Correct README current-use text that incorrectly claimed `datasets`, `snaplist`, and `full-snaplist` were included in the supplied archive. The release only ships `datasets.example.txt`; no missing historical files were invented or reconstructed.
- Fix `.gitignore` so broad private `config*` exclusion still protects operational configs while explicitly keeping `config-example.toml` and `config.example.md` trackable, alongside the existing `datasets.example.txt` exception.
- Fix copied Home Assistant naming remnants: replace `Syncerate`/`syncerate` descriptions, fallback names, trigger ID, and unknown-status title with `SnapBeforeWatchTower`/`snapbeforewatchtower`. The MQTT topic and notification logic are unchanged.
- Extend `commented_code_map.md` with the current configuration, safety, dependency, `.gitignore`, dataset-example, and Home Assistant integration files while retaining complete Python function/class/command explanations.
- Keep `SAFETY.md` and its disclaimer/liability/data-loss notices unchanged.
- Refresh `VERIFICATION.md` with post-change compile, regression, CLI-boundary, documentation/config-coverage, naming, manifest, and clean-package checks.
- Preserve every path present in the supplied 0.0.4 archive. No source/project file is removed and no runtime/cache material is added to the release ZIP.

## 0.0.4 — 2026-09-15

### Application code changes (complete)

- Bump the application version from 0.0.3 to 0.0.4.
- Replace the multi-flag runtime interface with one TOML configuration file. The only public application CLI option is now `-c CONFIG`.
- Remove public `--version`, `--mqtt-config`, `--command`, `--file`, `--older-than`, `--retain-count`, `--send-mail`, `--mail-on-success`, `--dry-run`, and the automatic `-h/--help` option so operational settings cannot be split between CLI and TOML.
- Add `load_app_config()` using Python 3.11+ standard-library `tomllib`. It validates the exact `[application]`, optional `[mail]`, and optional `[mqtt]` tables and rejects unsupported/legacy keys.
- Map TOML application values into the existing runtime attributes so the original ZFS snapshot creation/deletion, retention, Docker digest, logging, mail, root-check, and operation-order code can be reused unchanged.
- Reuse the existing `parse_older_than()` function for TOML `older_than` validation instead of creating a second retention-duration parser.
- Resolve `dataset_file` relative to the TOML file, making scheduled execution independent of the process working directory.
- Move mail settings into optional `[mail]` with explicit `enabled`, `recipient`, and `on_success`. Disabled mail maps to the original no-recipient behavior.
- Change `mqtt_report.load_config()` into `validate_config()` for TOML-sourced values. MQTT retains direct plain-string `password`, QoS, verified TLS, certificate, timeout, non-retained publish, sanitized error, and child-process behavior.
- Add explicit `[mqtt].enabled`. Disabled MQTT requires no broker fields/Paho dependency, while unsupported MQTT keys are still rejected.
- Normalize TOML empty strings for optional MQTT username/password/certificate fields to `None`, because TOML has no JSON-style `null` literal.
- Resolve MQTT CA/client certificate/key paths relative to the TOML file.
- Preserve dry-run MQTT suppression and validate enabled MQTT settings without requiring Paho during dry-run.
- Update the private `mqtt_report.py --publish` worker error text to point users to `SnapBeforeWatchTower.py -c CONFIG`; `--publish` remains internal-only and is not a public app flag.
- No ZFS retention selection rules, snapshot naming, Docker failure semantics, mail command behavior, root enforcement, MQTT payload schema, MQTT retain/QoS semantics, or destructive-operation safety behavior changed.

### Configuration, documentation, tests, and packaging

- Add `config-example.toml` as the single complete configuration example. Every setting has inline comments explaining purpose, valid values, defaults/behavior, relative-path rules, and security implications.
- Include all former `mqtt.json` settings directly in `[mqtt]`, including the requested plain `password = "<String>"`, and include mail as an optional TOML feature.
- Set the example to `dry_run = true`, `[mail].enabled = false`, and `[mqtt].enabled = false` for a safer first run.
- Remove obsolete `config.example.md`, `mqtt.example.json`, and operational `mqtt.json`, because the application no longer reads those formats/files.
- Update `.gitignore` to ignore `config.toml`, the expected private operational TOML that may contain an MQTT password.
- Rewrite README.md for current TOML-only usage, the single `-c CONFIG` invocation, every TOML setting, dataset format, retention behavior, external commands, optional mail/MQTT, logging, and safety. No old-version history is kept in README.
- Rewrite `commented_code_map.md` to cover every application/test function/class and every external/private command, including why each exists and which original helpers remain preserved but unused.
- Update regression tests for TOML loading, relative paths, optional section defaults, legacy-key rejection, direct MQTT password handling, TLS paths, and the single-public-flag parser boundary while retaining the original retention/dry-run/root/order/mail tests.
- Refresh VERIFICATION.md after compile, TOML parse, CLI-boundary, documentation-coverage, regression, manifest, clean-package, and fresh-ZIP checks.

## 0.0.3 — 2026-09-15

### Application code changes (complete)

- Bump the application version from 0.0.2 to 0.0.3.
- Replace the MQTT `password_env` environment-variable credential model with the requested direct JSON field `"password": "<String>"`.
- `mqtt_report.load_config()` now accepts `password` as an optional nonempty string, requires `username` when a password is supplied, and rejects the old `password_env` key as unsupported.
- `mqtt_report.worker()` now passes the configured JSON password directly to Paho authentication instead of looking up an environment variable.
- Remove now-unused `os` and `re` imports from `mqtt_report.py`.
- Update `--mqtt-config` CLI help to state that username/password are read directly from JSON.
- Preserve the existing MQTT child-worker boundary: broker credentials remain off the process command line, publish failures remain sanitized, timeout/QoS/TLS/retain behavior is unchanged, and MQTT failure still cannot replace the underlying snapshot job outcome.
- No ZFS snapshot creation/deletion, retention calculation, Docker capture, logging, mail, root enforcement, MQTT payload schema, TLS behavior, publish QoS/retain behavior, or operation ordering changed.

### Configuration, documentation, tests, and packaging

- Migrate the supplied operational `mqtt.json` from `password_env` to `password`, preserving the user's existing configured broker password under the requested key.
- Update `mqtt.example.json` and `config.example.md` to show `"password": "<String>"` directly and remove environment-variable/sudo-preservation setup.
- Update README.md for current 0.0.3 behavior only: direct JSON password configuration, ordinary `sudo` invocation, current payload version, file-permission warning, and unchanged sanitized child-worker behavior.
- Update `commented_code_map.md` for version 0.0.3 and the direct-password validation/publish/test paths.
- Update CLI and MQTT tests to expect 0.0.3, direct JSON password authentication, username/password validation, and rejection of the retired `password_env` key.
- Refresh VERIFICATION.md after release checks and rebuild a clean ZIP excluding `.git`, runtime logs, Python caches/bytecode, test/build caches, and temporary files.

## 0.0.2 — 2026-09-15

### Application code changes (complete)

- Bump the application version from 0.0.1 to 0.0.2.
- Keep the existing safe MQTT credential model: `password_env` still names an environment variable and the password is still never accepted as a JSON password field.
- Add explicit validation that `password_env` is a conventional environment-variable name (`[A-Za-z_][A-Za-z0-9_]*`). This catches the exact misconfiguration where a literal broker password was placed in `password_env` instead of a variable name.
- Replace the ambiguous missing-password error with actionable `sudo --preserve-env=<password_env-name>` guidance while deliberately not echoing the configured value, because a mistaken value could itself be a password.
- Expand the `--mqtt-config` CLI help so the environment-variable requirement and dry-run behavior are visible directly in `--help`.
- No ZFS snapshot creation/deletion, retention calculation, Docker capture, logging, mail, root enforcement, MQTT payload schema, TLS behavior, publish QoS/retain behavior, or operation ordering changed.

### Configuration, documentation, tests, and packaging

- Correct the supplied operational `mqtt.json` so `password_env` contains `SNAP_MQTT_PASSWORD` instead of a literal secret; no broker password is retained in the release copy.
- Update `mqtt.example.json` to demonstrate a username plus `SNAP_MQTT_PASSWORD` variable reference rather than leaving the credential relationship implicit.
- Update README.md and config.example.md with the exact export plus `sudo --preserve-env=SNAP_MQTT_PASSWORD` invocation, service-manager guidance, variable-name rules, and current 0.0.2 payload example. README remains current-usage documentation only.
- Update `commented_code_map.md` for version 0.0.2, the stricter `load_config()` behavior, the MQTT regression test, and `.gitignore`.
- Extend CLI tests so `--mqtt-config` must appear in `--help`, and update version expectations to 0.0.2.
- Extend MQTT tests to cover malformed environment-variable names, the literal-password mistake, missing/empty variables with sudo guidance, and continued secret redaction.
- Fix `.gitignore` typo `__pycachhe__/` to `__pycache__/` and add common Python bytecode, pytest, build, dist, and egg-info exclusions required by the clean-package policy.
- Refresh VERIFICATION.md after the release checks and package only clean project files, excluding `.git`, runtime logs, Python caches/bytecode, test/build caches, and temporary files.

## 0.0.1 — 2026-09-15

The supplied `SnapBeforeWatchTower-main.zip` contained four files and no explicit version or version history. This is its first recorded release; the unversioned input is treated as the 0.0.0 baseline for this initial increment, not claimed as an earlier published release.

### Application code changes (complete)

- Add the module constant `__version__ = "0.0.1"`.
- Register `--version` on the existing parser. It exits before logging, privilege checks, or external commands.
- Add optional `--mqtt-config PATH` final reporting using `mqtt_report.py` and optional `paho-mqtt` dependency.
- Validate MQTT JSON, dependency availability, credentials by environment-variable reference, publish topics, QoS, timeout, and verified TLS/certificate settings before dataset operations.
- Publish one non-retained JSON report matching the supplied Home Assistant fields: `status`, `title`, `name`, `job`, `exit_code`, `warning`, `error`, and `stderr`, plus command/version/run metadata.
- Suppress MQTT delivery during dry-run so a preview cannot advance automation; preserve the underlying process result when MQTT delivery fails.
- Bound MQTT work in a child process and enforce a 1–120 second total timeout. Keep secrets and broker parameters off the child command line and sanitize publish errors.
- Split the original `main()` operation body into `run(args, reporter)` so the reporter can observe final success, exceptions, and non-root exits without duplicating operation logic.
- Clarify existing `--retain-count` help: it applies to snapshot and log retention, and nonpositive values disable the count floor.
- Clarify existing `--mail-on-success` help: it adds success mail without disabling failure mail.
- Clarify existing `--dry-run` help: ZFS listing, logging, and requested mail still occur.
- No snapshot creation/deletion, retention, ZFS/Docker command execution, logging, email, or privilege-check behavior changed. All original functions and classes, including unused helpers, are retained.

### Documentation and project files

- Rewrite README.md for current setup, every command/flag, dataset format, retention rules, logging, notifications, exit behavior, and existing operational limitations. Correct the Python minimum from 3.9 to 3.10 and remove unsupported guarantees.
- Preserve the original README disclaimers and license statement in SAFETY.md.
- Add commented_code_map.md explaining every application and test function, nested helper, class, and command, including why it exists and whether the CLI uses it.
- Add config.example.md with all available flags and aliases, both command modes, defaults, and email/dry-run behavior; add datasets.example.txt.
- Add mqtt.example.json and requirements-mqtt.txt with every MQTT setting and the optional dependency range.
- Add tests/test_app.py and tests/test_mqtt.py with standard-library tests of retention, dry-run boundaries, non-root refusal, errors, command order, CLI parsing/version behavior, MQTT JSON/schema compatibility, config validation, redaction, TLS/auth arguments, timeouts, and final-report lifecycle. External operations are mocked.
- Add this VERSIONING.md as the single version history file (no duplicate differing only by filename case).
- Preserve `snaplist` and `full-snaplist` byte for byte; retain all four original paths.

### Verification and packaging

Check Python compilation, CLI help/version and invalid arguments, mocked behavior tests, unchanged operational source structure, documentation coverage, original-file preservation, and ZIP extraction/content equality. Exclude Python bytecode, caches, temporary files, and runtime logs. Exact results and per-file SHA-256 manifests accompany the release ZIP in the verification report. Live Linux/ZFS/Docker/mail integration requires a suitable test host and is not certified by these checks.
