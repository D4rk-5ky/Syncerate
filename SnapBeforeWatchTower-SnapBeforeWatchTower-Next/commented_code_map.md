# Commented code map

This map describes the current application, why each function/class exists, and every external command the code can execute. It is not a version history.

## `SnapBeforeWatchTower.py`

### Module-level behavior

- `__version__` — current application release number embedded in MQTT reports and maintained in `VERSIONING.md`. There is no public version CLI flag in the TOML-only interface.
- TOML is parsed with Python's standard-library `tomllib`. The only public CLI option is `-c CONFIG`; all operational values come from that file.

### Classes and functions

- `CustomLogger(logging.Logger)` — retained original helper that builds a logger with file and console handlers. The current main flow uses `setup_logger()` instead, but this class is preserved because it came from the original application and may still be useful to installations importing it.
  - `CustomLogger.__init__(name, log_filename)` — installs DEBUG file output and INFO console output with the standard formatter.

- `setup_logger(log_folder, log_date)` — creates the active main logger and error logger for a run. It returns both loggers plus the `.err` path so final cleanup can remove an empty error file.
  - nested `_build_logger(name, level, handlers)` — centralizes handler formatting/installation and clears stale handlers so repeated in-process test/application runs do not duplicate output.

- `choose_log_folder(preferred_root_folder, fallback_folder=None)` — retained original root/non-root log-folder helper. The current run path uses `pick_log_folder()`; this function remains for compatibility with the original source.

- `pick_log_folder(script_log_folder, tmp_name="SnapBeforeWatchTower")` — implements the active log-location policy. Non-root always uses a temporary directory. Root first tests whether the script-local log directory is writable, then falls back to temporary storage if necessary.
  - nested `_ensure_writable(path)` — safely probes a directory by creating/removing a small `.write_test` file; failure returns `False` instead of aborting the run.

- `CommandError(RuntimeError)` — structured exception for failed external commands run through `run_cmd()`. It retains the command, return code, stdout, and stderr so the real failure propagates without silently continuing destructive logic.
  - `CommandError.__init__(cmd, returncode, stdout, stderr)` — stores command-result details and creates a concise exception message.

- `MissingDatasetsError(RuntimeError)` — aggregate final failure raised only after all remaining configured datasets and normal log cleanup have been processed when one or more datasets were absent. Its message names the missing dataset(s) and contains the explicit `dataset does not exist` reason so mail and MQTT can distinguish this condition without adding a new status value.
  - `MissingDatasetsError.__init__(datasets)` — stores the missing dataset names and builds the user-facing final failure text.

- `is_missing_dataset_error(exc)` — inspects captured ZFS stderr from either `subprocess.CalledProcessError` or `CommandError` and returns true only for known absent-dataset wording (`dataset does not exist` or `no such pool or dataset`). This prevents permission errors and unrelated command failures from being treated as safe-to-continue.

- `remember_missing_dataset(error_logger, missing_datasets, dataset, exc)` — centralizes per-dataset continuation. It records each missing dataset once, logs that later datasets will continue, and returns false for any unrelated error so the caller re-raises it immediately.

- `run_cmd(cmd, logger=None, error_logger=None, check=True, dry_run=False)` — shared captured-subprocess helper. It avoids terminal spam, records failures through the error logger, raises `CommandError` when requested, and suppresses actual execution when `dry_run=True`.

- `get_newest_files(log_dir, prefix)` — finds the newest `.log` and `.err` independently by modification time for email reporting. Independent selection preserves the application's existing mail behavior even when one file is missing.

- `send_mail(subject, body, recipient, attachment_files=None)` — invokes the local `mail` program, placing all options before the recipient for compatibility with common mail/mailx implementations. It returns the mail process exit code and stderr instead of hiding delivery failure.

- `MailTo(logger, error_logger, recipient, log_folder, subject=..., intro=..., prefix=...)` — builds the email body from the newest non-empty error log and newest main log, attaches available logs, sends the message, then delegates result logging to `WasMailSent()`.

- `WasMailSent(logger, error_logger, MailExitCode, popenstderr)` — writes a clear success/failure result for the local mail command without changing the underlying snapshot result.

- `parse_older_than(value)` — converts `Nd`, `Nw`, or `Nm` strings to `datetime.timedelta`. Months intentionally mean 30 days. It rejects negative, fractional, uppercase, and malformed values. TOML loading reuses this existing parser instead of duplicating retention-age logic.

- `create_snapshot(logger, error_logger, dataset, dry_run=False)` — creates one timestamped managed snapshot for one dataset. In dry-run it only reports what would be created. Real ZFS failures are logged and re-raised so later logic cannot treat a failed creation as success.

- `extract_snapshot_date(snapshot_name)` — retained original timestamp parser for a managed snapshot-name fragment. The active retention implementation performs its own regex parse because it needs the complete snapshot match.

- `is_older_than(logger, error_logger, snapshot_date_str, older_than)` — retained original age helper. A malformed timestamp logs an error and returns `False`, which is the safe no-delete outcome.

- `delete_old_snapshots(logger, error_logger, dataset, older_than, retain_count, dry_run=False)` — lists snapshots for one dataset, selects only names matching SnapBeforeWatchTower's managed pattern, protects the newest count floor, applies the strict age cutoff, then destroys only snapshots that satisfy both rules. Invalid/unmanaged names are never selected. The ZFS list is executed even in dry-run so the preview is based on real current state.

- `delete_old_files(logger, error_logger, log_folder, older_than, retain_count, dry_run=False)` — groups `.log`, `.err`, and `.digest` files by embedded run timestamp, protects the configured newest group count, then deletes only old eligible groups. Dry-run reports candidates without removing them.

- `print_separator(logger, error_logger=None)` — writes the existing visual separator to the selected logger so terminal/log output remains readable.

- `save_docker_image_digests(logger, error_logger, log_folder, log_date, dry_run=False)` — runs `docker images --digests` during real `create` operations and writes the output into the same timestamp group as the logs. Dry-run skips Docker. Docker failure is nonfatal but is captured as an error/warning, and partial digest output is not intentionally retained.

- `load_app_config(path)` — loads the single TOML file and converts its settings into the existing runtime shape used by `run()`. It validates supported sections/keys/types, reuses `parse_older_than()`, resolves `dataset_file` relative to the TOML, turns disabled mail into `send_mail=None`, and delegates `[mqtt]` validation to `mqtt_report.validate_config()`. Reusing the existing runtime attributes lets the ZFS/mail operation code stay unchanged.

- `main()` — exposes the only public CLI option, `-c CONFIG`. It rejects every other flag, loads TOML before operations, creates the optional MQTT `RunReporter`, and enters the unchanged operation flow.

- `run(args, reporter)` — active operation coordinator. It chooses logging, attaches the MQTT error observer, enforces root before dataset/Docker/ZFS operations, reads datasets, and executes create/delete behavior in file order. A ZFS missing-dataset error from snapshot creation or snapshot listing is recorded per dataset and processing continues; after later datasets and normal log cleanup finish, `MissingDatasetsError` makes the overall run fail, selects missing-dataset failure mail, and gives MQTT a specific failure reason. Any other operation error still propagates immediately. Optional success mail and empty-current-`.err` cleanup remain unchanged.

## `mqtt_report.py`

### Constants

- `DEFAULTS` — default MQTT port/title/auth/QoS/TLS/certificate/timeout settings used only when MQTT is enabled.
- `SUPPORTED_KEYS` — exact accepted TOML `[mqtt]` keys after the top-level `enabled` switch has been removed by `load_app_config()`.
- `OPTIONAL_STRING_KEYS` — optional string fields that may be represented by `""` in TOML because TOML has no `null` value. Empty strings are normalized to `None` before publishing.

### Classes and functions

- `validate_config(supplied, base_dir, dry_run=False, enabled=True)` — validates TOML-sourced MQTT settings. Unsupported keys are rejected even when disabled. When disabled, no broker details or Paho dependency are required. When enabled, it validates broker/topic/QoS/timeout/TLS/auth, resolves TLS files relative to the TOML directory, normalizes empty optional strings, and checks for `paho-mqtt` unless the whole application is in dry-run.

- `ErrorCapture(logging.Handler)` — bounded in-memory collector for current-run error messages used in MQTT payloads. It avoids rereading older `.err` files and caps captured text at 4096 characters.
  - `ErrorCapture.__init__()` — configures ERROR-level capture and starts with empty text.
  - `ErrorCapture.emit(record)` — ignores separator-only messages and retains only the newest bounded error text.

- `build_payload(config, command, version, exc, errors, run_id)` — translates the actual process outcome into the Home Assistant JSON contract. It distinguishes success/failure exit codes, preserves nonfatal logged errors as `warning=true`, adds bounded failure/stderr text, and includes command/version/run/time metadata.

- `publish_report(config, payload)` — starts the same Python module as a bounded child worker and passes broker settings/payload over stdin as JSON. Credentials therefore do not appear in the child command line. Worker output is not copied into application errors because it could contain broker/credential details.

- `RunReporter` — context manager that observes exactly one application run and publishes at most one final MQTT status without masking the underlying result.
  - `RunReporter.__init__(config, command, version, dry_run=False)` — records settings, creates a unique run ID, and prepares an `ErrorCapture` handler.
  - `RunReporter.__enter__()` — returns the reporter for attachment to the application's error logger.
  - `RunReporter.attach(error_logger)` — attaches current-run error capture after logging is initialized.
  - `RunReporter.__exit__(exc_type, exc, traceback)` — detaches capture, suppresses publishing when disabled/dry-run, builds/publishes the final payload otherwise, logs sanitized MQTT failure/timeout messages, and always returns `False` so original exceptions continue propagating.

- `worker()` — child-process Paho publisher. It reads its request from stdin, constructs optional username/password auth and verified TLS context, then publishes exactly one non-retained message.

- module `__main__` guard — accepts only the private internal `--publish` worker switch. This is not a public application flag; users run `SnapBeforeWatchTower.py -c CONFIG`. Any other direct invocation of `mqtt_report.py` exits.

## External commands and why they exist

- `zfs snapshot DATASET@SnapBeforeWatchTower-Date-...` — creates the managed recovery point requested by `command="create"`.
- `zfs list -H -t snapshot -o name DATASET` — obtains current snapshot names for safe, explicit retention calculation. It is intentionally non-recursive and also runs in dry-run.
- `zfs destroy SNAPSHOT` — destroys only managed snapshots selected by both count-floor and age rules; suppressed in dry-run.
- `docker images --digests` — records the current local Docker image/digest inventory before snapshots during a real `create` run. Failure is nonfatal.
- `mail -s SUBJECT [--attach FILE ...] RECIPIENT` — optional local email notification transport; enabled only by TOML `[mail]` settings.
- `[python, -B, mqtt_report.py, --publish]` — private bounded MQTT child process. `--publish` is internal-only and is never a user-facing SnapBeforeWatchTower flag.

## `tests/test_app.py`

- `temporary_directory()` — disposable filesystem fixture with cleanup for portable tests.
- `write_config(...)` — creates minimal TOML configurations so integration tests exercise the real loader instead of fabricating argparse namespaces.
- `BehaviorTests` — regression suite for configuration mapping plus original safety/retention/mail/Docker/run-order behavior.
  - `setUp()` — creates mock loggers.
  - `test_duration_units_and_invalid_input()` — verifies accepted/rejected age syntax.
  - `test_toml_config_maps_former_flags_and_resolves_relative_dataset()` — proves old operational flags now come from TOML, mail/MQTT map correctly, and dataset paths are TOML-relative.
  - `test_toml_optional_sections_default_disabled()` — proves omitted optional notification sections are safely disabled.
  - `test_toml_invalid_values_and_old_flag_keys_are_rejected()` — rejects invalid core values, unknown/legacy keys, invalid enabled mail, retired `password_env`, and unsupported sections.
  - `test_retention_preserves_newest_and_ignores_unmanaged_or_invalid_dates()` — verifies count-floor ordering and managed-name filtering.
  - `test_retention_preserves_recent_snapshot_without_count_floor()` — verifies age protection still applies with no count floor.
  - `test_nonpositive_count_disables_floor()` — verifies zero/negative counts do not accidentally protect old snapshots.
  - `test_dry_run_lists_but_never_creates_destroys_or_captures_docker()` — proves destructive/create commands are suppressed while real snapshot listing remains.
  - `test_list_failure_prevents_destroy()` — proves a failed ZFS list aborts before destroy.
  - `test_create_failure_propagates()` — proves the low-level snapshot helper still re-raises ZFS creation failures for the run coordinator to classify.
  - `test_missing_dataset_detection_only_accepts_missing_zfs_messages()` — proves only known absent-dataset stderr is classified as continuable while permission errors are not.
  - `test_create_continues_after_missing_dataset_then_fails_run_and_sends_failure_mail()` — proves create mode skips one missing dataset, processes the next, runs log cleanup, then returns the aggregate failure and selects missing-dataset failure mail instead of success mail.
  - `test_delete_continues_after_missing_dataset_and_processes_following_dataset()` — proves delete/retention mode has the same per-dataset continuation and final-failure behavior.
  - `test_unrelated_dataset_command_error_still_aborts_immediately()` — proves unrelated ZFS errors retain the old immediate-abort safety boundary.
  - `test_log_groups_count_age_and_dry_run()` — verifies log-group retention and dry-run behavior.
  - `test_docker_nonzero_is_logged_and_returns_none()` — verifies Docker digest failure stays nonfatal and leaves no digest artifact.
  - `test_nonroot_refuses_before_dataset_or_external_commands()` — verifies root enforcement occurs before dataset/ZFS/Docker operations.
  - `test_main_create_order_and_docker_failure_continuation()` — verifies create-mode ordering remains digest, create/retain per dataset, then log cleanup.
  - `test_mail_options_precede_recipient()` — verifies safe/compatible local `mail` argument order.
- `CLITests` — parser-boundary regression suite.
  - `run_cli(*args)` — invokes the real script parser in a subprocess without bytecode generation.
  - `test_only_config_flag_is_accepted()` — verifies `-c CONFIG` is the only public CLI option and old/help/version/long-config flags are rejected.

## `tests/test_mqtt.py`

- `MQTTTests` — offline validation and publish-lifecycle suite; no real broker or Paho installation is required.
  - `setUp()` — builds a reusable validated-looking MQTT baseline.
  - `validate(value, dry_run=True, enabled=True)` — convenience wrapper around the real TOML-era MQTT validator in a disposable base directory.
  - `test_config_defaults_tls_port_and_disabled_mode()` — verifies defaults, implicit TLS port when omitted, and disabled mode.
  - `test_invalid_config_stops_early()` — verifies bad topic/port/QoS/timeout/TLS/auth/certificate/legacy/unknown values are rejected.
  - `test_password_optional_strings_and_dependency_validation()` — verifies direct password auth, empty-string normalization, username requirement, and conditional Paho dependency enforcement.
  - `test_tls_relative_paths_resolve_from_toml_directory()` — verifies certificate files use the TOML directory as their base.
  - `test_payload_success_warning_and_failure_contract()` — verifies JSON payload status/exit/warning metadata for representative outcomes.
  - `test_missing_dataset_failure_keeps_existing_failure_contract_and_reason()` — proves a missing-dataset aggregate remains `status=failure`, `exit_code=1`, `warning=false`, and carries the specific missing-dataset reason in `error` without changing the Home Assistant contract.
  - `test_capture_is_bounded_and_ignores_separators()` — verifies MQTT error text is bounded and cosmetic separators are ignored.
  - `test_worker_publish_uses_auth_tls_and_no_retain()` — verifies Paho receives direct auth, TLS context, payload, and `retain=false`.
  - `test_publisher_timeout_stdin_and_failure()` — verifies timeout usage, stdin transport, and secret-safe worker failure handling.
  - `test_disabled_and_dry_run_never_publish()` — verifies disabled/dry-run reporting cannot publish.
  - `test_reporter_publishes_once_and_does_not_mask_failure()` — verifies one failure report while the original exception still propagates.
  - `test_publish_errors_preserve_original_outcome()` — verifies MQTT delivery failure is sanitized and never changes the underlying operation outcome.

## Configuration and integration files

- `config-example.toml` — loadable, fully commented example containing every supported `[application]`, `[mail]`, and `[mqtt]` setting. It defaults to dry-run with mail and MQTT disabled for a safer first copy.
- `config.example.md` — supplemental human-readable reference for the same current TOML-only interface. It documents the single public `-c CONFIG` option and every supported TOML setting, but is never parsed by the application.
- `datasets.example.txt` — minimal two-line example of the dataset-list format consumed by `dataset_file`.
- `requirements-mqtt.txt` — optional Paho MQTT dependency list required only for real MQTT publishing.
- `homeassistant/SnapBeforeWatchtower-mqtt-persistent-notification.yaml` — example Home Assistant MQTT status automation for SnapBeforeWatchTower. It listens for the JSON report, sends Pushover success/failure/unknown notifications, and uses SnapBeforeWatchTower naming throughout.
- `SAFETY.md` — preserved disclaimer/liability/data-loss notices for this project.
- `.gitignore` — excludes private operational `config*` files, runtime dataset/list files, logs, Python caches, and build artifacts while explicitly keeping the shipped `config-example.toml`, `config.example.md`, and `datasets.example.txt` examples trackable.
