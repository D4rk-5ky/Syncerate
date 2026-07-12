# Syncerate versioning

Syncerate uses three-part versions in the form:

```text
major.minor.patch
```

Every created release increments by exactly `0.0.1` unless a larger version change is explicitly requested.

The patch number rolls over as follows:

```text
0.0.98 -> 0.0.99 -> 0.1.0
```

It must never become `0.0.100`.

## 0.4.6

Previous version: `0.4.5`.

- Corrected the current release number to `0.4.6` so the project continues from version `0.4.5` without reusing an already-created version number.
- Updated `Syncerate.py`, `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` so every current-version reference is `0.4.6`.
- Rebuilt and reverified the complete project package.
- No application behavior was changed from version `0.4.5`.

## 0.4.5

- Completed the single-file runtime-state refactor while keeping all application code in `Syncerate.py`.
- Moved command-line parsing, configuration loading, timestamp creation, logger setup, dataset loading, password resolution, replication startup, success handling, and top-level error handling into `main()` and functions called by it.
- Made importing `Syncerate.py` side-effect free: importing defines constants, dataclasses, exceptions, and functions only; it does not require `--conf`, read files, create logs, ask for a password, or start Syncoid.
- Added `AppConfig` to carry configuration values explicitly instead of using runtime configuration globals.
- Added `RunContext` to carry the per-run timestamp and optional `.log`, `.err`, and `.out` paths.
- Added `DatasetPair` to keep each validated source, destination, and per-destination argument set together.
- Added `SyncoidAttemptResult` to return the child process, modified command, repeat state, resume-retry request, and known missing-destroy-snapshot state explicitly.
- Removed runtime globals including parsed arguments, raw configuration state, source/destination lists, resolved passwords, timestamp/log paths, and Syncoid control flags.
- Replaced internal `sys.exit()` calls in list validation, Syncoid monitoring, MQTT handling, mail handling, and error handling with `SyncerateError` exceptions or explicit result objects.
- Kept `sys.exit(main())` only at the executable program boundary.
- Preserved existing exit codes, command construction, source/destination validation, password behavior, lazy MQTT/HA behavior, notification order, one-time `--no-resume` retry, the exact nonfatal unavailable-resume warning, generic warning failure, known missing-destroy-snapshot handling, local effective-user behavior, and remote SSH-user behavior.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the refactored application behavior.

## 0.4.4

- Created the first intermediate build of the single-file runtime-state refactor.
- Began moving startup work into `main()` and replacing runtime globals with explicit state objects.
- This intermediate build was completed and fully documented in version `0.4.5`.

## 0.4.3

- Kept local Syncoid and ZFS execution under the effective user that starts `Syncerate.py`; no alternate local account is introduced.
- Added logging of the effective local username and UID before every Syncoid process starts.
- Documented that remote ZFS commands use the SSH user written in the remote source or destination endpoint.
- Added a dedicated handler for Syncoid's exact nonfatal `ZFS resume feature not available ... sync will continue without resume support` message.
- Changed that exact resume-capability message from fatal exit code `4` to a logged warning that waits for Syncoid's real final exit status.
- Kept unrelated Syncoid warnings fatal and preserved the existing resume-retry, authentication, dataset, repeated-pattern, and missing-destroy-snapshot safety behavior.
- Updated `README.md`, `commented_code_map.md`, and the example configuration for current version `0.4.3` behavior.

## 0.4.2

- Removed the GitHub Pages configuration file `_config.yaml` from the distributed project.
- Removed the GitHub Pages layout file `_layouts/default.html` from the distributed project.
- Kept all application, configuration, Home Assistant reference, and documentation files unchanged except for version references.
- Updated application and documentation version references to `0.4.2`.

## 0.4.1

- Removed the unconditional top-level `paho-mqtt` import.
- Added a lazy `paho-mqtt` import inside `send_mqtt_messages()` so the dependency is loaded only when MQTT publishing actually runs.
- Added a clear MQTT exit-code `10` error when MQTT is enabled but `paho-mqtt` is unavailable.
- Made `Use_MQTT` optional with a safe disabled fallback.
- Added support for `No`, `False`, `0`, and `Off` as disabled MQTT and Home Assistant values.
- Made `Use_HomeAssistant` optional.
- Moved Home Assistant option loading into the successful MQTT publishing path.
- Prevented Home Assistant configuration from being accessed during normal startup and configuration logging.
- Kept the Home Assistant availability topic unread unless Home Assistant support is enabled.
- Prevented disabled MQTT integration settings from being accessed for configuration logging.
- Added the application version constant and the `--version` command.
- Updated `config/example-Syncerate.cfg` with all available options and disabled MQTT and Home Assistant defaults.
- Replaced `README.md` with documentation for current application behavior only.
- Added `commented_code_map.md` describing every function, execution stage, command, and safety-related branch.
- Expanded `.gitignore` for Python bytecode, build caches, test caches, and temporary files.

## 0.4.0

Baseline version supplied for this work.

Observed baseline capabilities:

- Reads paired source and destination ZFS dataset lists.
- Validates equal list lengths and matching final dataset names.
- Builds safe argument-list Syncoid commands from `SourceDataSet` and `DestDataSet` placeholders.
- Supports dataset names containing spaces.
- Supports per-destination extra Syncoid arguments.
- Executes Syncoid through `pexpect` and handles known SSH, password, warning, resume, and connection patterns.
- Supports optional logs, email notifications, MQTT publishing, Home Assistant MQTT availability, and a successful-run system action.
