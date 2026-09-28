# Syncerate commented code map

This document maps the modular Syncerate implementation in version `0.4.35`. It explains what every module, class, function, command stage, and safety branch does and why it exists.

## Application layout

```text
Syncerate.py
Syncerate.spec
build_pyinstaller.sh
requirements-build.txt
syncerate/
├── __init__.py
├── app.py
├── cli.py
├── config.py
├── datasets.py
├── errors.py
├── logging_setup.py
├── models.py
├── notifications.py
├── syncoid_runner.py
└── system_actions.py
tests/
├── __init__.py
├── helpers.py
├── test_app_and_logging.py
├── test_config.py
├── test_datasets.py
├── test_notifications.py
├── test_packaging.py
├── test_syncoid_runner.py
└── test_system_actions.py
```

The dependency direction is intentionally one-way:

```text
Syncerate.py
    -> syncerate.app
        -> cli / config / datasets / logging_setup
        -> notifications / syncoid_runner / system_actions
            -> models / errors
```

Lower-level modules do not import `app.py` or `Syncerate.py`. This prevents circular imports and keeps each module independently testable.

Importing `Syncerate.py` or `syncerate` only defines/imports code. It does not:

- parse command-line arguments;
- require `--conf`;
- read a configuration file;
- create log files;
- read dataset lists;
- request a password;
- import `paho-mqtt`;
- start Syncoid;
- send notifications;
- execute a system action.

All runtime work begins when `main()` is called.

## `Syncerate.py`

This remains the executable used by existing commands:

```bash
./Syncerate.py --conf /path/to/Syncerate.cfg
./Syncerate.py --help
./Syncerate.py --version
```

It imports and re-exports the existing public constants, classes, and functions so code that imports names from `Syncerate.py` remains compatible. The only process exit is:

```python
if __name__ == "__main__":
    sys.exit(main())
```

Keeping `sys.exit()` at this boundary means internal modules return values or raise `SyncerateError` instead of terminating the interpreter unexpectedly.

## `syncerate/__init__.py`

### `VERSION` and `__version__`

```python
VERSION = "0.4.35"
__version__ = VERSION
```

This is the single authoritative application version. `cli.py` uses it for `--version`, and `Syncerate.py` re-exports it for compatibility.

## `syncerate/errors.py`

This module contains shared exit codes and the application exception. Keeping these values in a dependency-light module lets every other module use the same codes without circular imports.

### Exit-code constants

- `EXIT_OK = 0`: successful run.
- `EXIT_LIST_ERROR = 1`: source/destination parsing or validation failed.
- `EXIT_SCRIPT_ERROR = 2`: application/configuration failure or exhausted ordinary Broken Pipe retries.
- `EXIT_WARNING = 4`: resume support is unavailable and `ContinueWithoutResume` is false.
- `EXIT_PASSWORD_DENIED = 5`: password, SSH permission, or ZFS permission failure.
- `EXIT_CONNECTION_TIMEOUT = 6`: remote connection timed out.
- `EXIT_CONNECTION_REFUSED = 7`: remote connection was refused.
- `EXIT_DATASET_MISSING = 8`: Syncoid skipped a dataset.
- `EXIT_REPEATED_PATTERN = 9`: one output pattern repeated beyond its safety limit.
- `EXIT_MQTT_ERROR = 10`: optional MQTT dependency or publish operation failed.
- `EXIT_SYSTEM_ACTION_ERROR = 11`: reserved for system-action failures; current behavior still logs system-action exceptions without converting them to this code.

### `SyncerateError`

A known application exception carrying:

- `message`: text for the error log;
- `exit_code`: final process code;
- `kind`: `list`, `known_child`, `syncoid`, `mqtt`, or `script`;
- captured `pexpect` output when relevant.

It replaces internal `sys.exit()` calls. `app.main()` catches it, logs the correct diagnostics, optionally publishes a JSON MQTT failure status, optionally sends error mail, and returns its exit code.

## `syncerate/models.py`

This module contains data only. It does not start work or import higher-level modules.

### `AppConfig`

Immutable configuration state loaded from one INI file. It replaces former runtime globals such as:

- `config`;
- `MailOption`;
- `SystemOption`;
- `Use_MQTT`;
- `SendMailOnSuccess`;
- `SendMQTTOnSuccess`;
- `MQTT_JSON_Status`;
- `mqtt_json_topic` (dedicated JSON-only topic read from the raw config);
- `DateTime`;
- `LogDestination`;
- `BackupTitle`;
- `BackupComment`;
- `PassWordOption`;
- `SyncoidCommand`;
- `UseSSHAgent`;
- `SSHAgentKeyLifetimeSeconds`;
- `ContinueWithoutResume`;
- `RetryBrokenPipe`;
- `BrokenPipeRetryCount`;
- `BrokenPipeRetryWaitSeconds`.

Fields:

- `config_path`: selected configuration path for logs;
- `raw_config`: retained `RawConfigParser` for lazy MQTT/HA option reads;
- `mail_option`: recipient or `No`;
- `system_option`: successful-run command or `No`;
- `use_mqtt`: normalized Boolean enabling retained success MQTT and non-retained failure events;
- `send_mail_on_success`: normalized Boolean controlling only success/warning-success mail; defaults to `True` when the INI option is omitted;
- `send_mqtt_on_success`: normalized Boolean controlling only success/warning-success MQTT publishing across both legacy/HA and JSON success paths; defaults to `True` when the INI option is omitted;
- `mqtt_json_status`: normalized Boolean independently enabling structured non-retained success/failure MQTT status;
- `use_home_assistant`: the strictly validated legacy Home Assistant availability Boolean reused by notifications instead of reparsing raw text;
- `datetime_format`: filename timestamp format;
- `log_destination`: normalized directory or `None`;
- `backup_title` / `backup_comment`: optional descriptive text; `backup_comment` may contain embedded newlines loaded from standard indented INI continuation lines;
- `source_list_path` / `destination_list_path`: dataset-list files;
- `password_option`: `No`, `Ask`, or a literal credential;
- `syncoid_command`: command template;
- `use_ssh_agent`: normalized Boolean enabling the isolated per-run agent path;
- `ssh_agent_key_lifetime_seconds`: positive lifetime for the loaded private-agent identity, defaulting to `3600`;
- `continue_without_resume`: normalized Boolean, default true, permitting continuation after the resume-unavailable warning; false stops the run with code 4;
- `retry_broken_pipe`: normalized Boolean controlling optional per-dataset retries;
- `broken_pipe_retry_count`: validated retries available to each individual dataset, defaulting to `1`;
- `broken_pipe_retry_wait_seconds`: validated whole seconds to wait before each retry, defaulting to `10`.

Properties:

- `mail_enabled`: mail is enabled unless the value is `No`;
- `system_action_enabled`: system action is enabled unless the value is `No`;
- `logging_enabled`: file logging is enabled when a log directory exists.

The raw parser remains available for MQTT broker credentials, payloads, and topics. Boolean feature switches are validated once at startup and carried as typed fields instead of being interpreted again later.

### `RunContext`

Immutable values created for one invocation:

- timestamp;
- log directory;
- `.log` path;
- `.err` path;
- `.out` path.

It replaces global timestamp and log-path variables. When logging is disabled, all file paths are `None` and terminal logging still works.

### `DatasetPair`

One validated replication unit containing:

- source dataset;
- destination dataset;
- destination-specific Syncoid arguments.

It replaces three parallel source/destination/argument lists, preventing arguments from becoming associated with the wrong dataset.

### `SSHAgentSession`

Mutable per-run state for the isolated OpenSSH agent. It stores only process/socket metadata and never stores the passphrase. Fields include the foreground agent process, private temporary directory, socket path, child environment, selected identity path, `ssh-add` executable, and key lifetime. Keeping this state explicit lets `app.main()` guarantee cleanup around the complete replication list.

### `MissingDatasetFailure`

Immutable record for one configured `DatasetPair` that encountered a recognized missing ZFS dataset/pool condition. It stores the pair plus every matched ZFS/Syncoid message so terminal logging, MQTT JSON, and email can report the same evidence without reparsing logs.

### `ReplicationSummary`

Carries aggregate state for the processed dataset list. Its `broken_pipe_failed_datasets` list is retained for compatibility with callers constructing summaries; current execution stops on retry exhaustion and does not populate that list, while `missing_dataset_failures` contains `MissingDatasetFailure` records for pairs that hit the continue-but-fail missing-data path. `has_broken_pipe_warning` identifies that compatibility case for externally constructed summaries; `has_missing_dataset_failure` identifies a completed-list failure that must return exit code `8`. `transferred_bytes` accumulates actual Syncoid/`pv` bytes across attempts, and `transfer_measurement_complete` remains true only when every started Syncoid send stream supplied a usable byte counter.

#### `has_broken_pipe_warning`

Returns whether the compatibility `broken_pipe_failed_datasets` list is nonempty. Current runtime does not populate it; notification helpers still accept externally constructed summaries.

#### `has_missing_dataset_failure`

Returns true when at least one pair was recorded as failed because a ZFS dataset or pool was missing. `app.main()` uses this to defer the final exit-code-`8` failure until the remaining dataset list has completed.

### `SyncoidAttemptResult`

Returned by one monitored Syncoid attempt. It contains:

- the `pexpect` child;
- the exact command used for the attempt;
- repeated-pattern status;
- whether the known missing-destroy-snapshot condition was observed;
- whether this attempt stopped after detecting an ordinary Broken Pipe;
- whether recognized missing dataset/pool output was observed;
- the matched missing dataset/pool messages for later per-pair reporting;
- the actual `pv` bytes observed during this attempt;
- whether transfer measurement was complete for every started stream in this attempt.

It replaces former mutable control globals and carries transfer/error state without requiring a second Syncoid/ZFS query.

## `syncerate/cli.py`

### `parse_arguments(argv=None)`

Creates the `argparse` parser only when called.

Supported flags/commands:

```bash
./Syncerate.py --conf /path/to/Syncerate.cfg
./Syncerate.py -c ./config/Syncerate.cfg
./Syncerate.py --help
./Syncerate.py --version
```

- `--conf FILE` / `-c FILE`: required for a normal run, has no hidden/default path, and passes the selected INI path to `load_app_config()`. Relative paths remain relative to the caller's current working directory.
- `-h` / `--help`: argparse's built-in help action; prints the full syntax, descriptions, and examples and exits before configuration/runtime work.
- `--version`: argparse version action using `%(prog)s` plus the authoritative `VERSION`, so the displayed name is `Syncerate.py` for the source entry point and `Syncerate` for the standalone executable. It exits before configuration/runtime work.

The parser uses `RawDescriptionHelpFormatter` so the multi-line examples in the epilog keep their intended layout. The optional `argv` parameter lets tests pass an explicit argument list without modifying process arguments.

## `syncerate/config.py`

### `CONFIG_SECTION`

```python
CONFIG_SECTION = "Syncerate Config"
```

Keeps the INI section name consistent between normal configuration loading and lazy notification settings.

### `option_is_enabled(value)`

Legacy compatibility helper that returns true only for `YES`, `TRUE`, `1`, or `ON` after normalization. External imports of this helper continue to work, but runtime configuration loading uses the stricter parser below so typo values cannot silently become false.

### `parse_boolean_option(raw_config, option_name, *, fallback="No")`

Reads one documented Boolean and accepts exactly the enabled/disabled spellings `Yes/No`, `True/False`, `1/0`, and `On/Off` case-insensitively. Any other nonempty spelling raises `ValueError` before replication begins. This is used for `UseSSHAgent`, `ContinueWithoutResume`, `RetryBrokenPipe`, `Use_MQTT`, `SendMailOnSuccess`, `SendMQTTOnSuccess`, `Use_HomeAssistant`, and `MQTT_JSON_Status`. Most callers use the default fallback `No`; the two success-notification controls and `ContinueWithoutResume` deliberately pass `fallback="Yes"` so omitted keys preserve successful notifications and continuation without resume support.

### `validate_syncoid_command_template(command_template)`

Parses the configured template with `shlex.split()`, rejects empty/malformed commands, and requires exactly one occurrence of `SourceDataSet` and exactly one occurrence of `DestDataSet`. Validation is called both while loading configuration and while building argv, so direct callers of `build_syncoid_command()` get the same protection.

### `_required_text(raw_config, option_name)`

Private startup helper that reads a required option, strips surrounding whitespace, and rejects an empty value. It centralizes the same validation used by `Mail`, `SystemAction`, `DateTime`, both list paths, `PassWord`, `SyncoidCommand`, and `LogDestination`.

### `load_app_config(config_path)`

Reads and validates the selected INI file, then returns immutable `AppConfig`. It verifies the file and section, validates all required nonempty text, strictly parses supported Booleans, validates the Syncoid template before any dataset is touched, validates positive/non-negative numeric retry/agent settings, normalizes `LogDestination = No` to `None`, and validates enabled MQTT channels before replication. `SendMailOnSuccess`, `SendMQTTOnSuccess`, and `ContinueWithoutResume` are optional strict Booleans with `Yes` defaults so omitted options preserve successful notifications and continuation without resume support. Invalid values fail at startup; the parsed resume policy is stored on `AppConfig` and passed to every Syncoid attempt.

For MQTT it requires a broker address, port `1..65535`, the legacy topic/message when `Use_MQTT` is enabled, the HA availability topic when that legacy integration is enabled, and a dedicated JSON topic when `MQTT_JSON_Status` is enabled. Conflicting retained/non-retained topics are rejected. Broker credentials, payload text, and topic values stay in `raw_config`; validated feature switches are stored as typed fields in `AppConfig`.

It does not create logs, read datasets, resolve credentials, import `paho-mqtt`, or start external commands. Expected parser/configuration exceptions are converted by `app.main()` into a clear exit-code-2 configuration error.

## `syncerate/logging_setup.py`

### `create_run_context(app_config)`

Creates the current timestamp and derives:

```text
Syncerate-<timestamp>.log
Syncerate-<timestamp>.err
Syncerate-<timestamp>.out
```

When logging is disabled it returns a context with no file paths.

### `get_logger(run_context)`

Configures the named `syncerate` logger.

Always adds:

- INFO output to the terminal.

When file logging is enabled, also adds:

- an INFO `.log` handler;
- an ERROR-only `.err` handler.

Existing handlers are closed and removed first so repeated `main()` calls in tests do not duplicate output.

### `get_console_logger()`

Creates a terminal-only logger for errors occurring before configuration or log-path creation completes.

### `_format_multiline_value_lines(prefix, value)`

Returns aligned physical text lines for one labelled multiline value. Both the logger path and the plain-text email/final-summary formatter reuse this helper so continuation indentation is defined in one place.

### `log_multiline_value(logger, prefix, value)`

Writes `_format_multiline_value_lines()` one physical line at a time. This keeps every comment/configuration line inside a real logging record so terminal and `.log` output retain timestamps/levels instead of allowing embedded newlines to create unprefixed text.

### `log_backup_metadata(app_config, logger)`

Shared title/comment renderer used by startup logging. It reuses `log_multiline_value()` so one-line and multiline `BackupComment` values follow the same formatting path without duplicated line handling. When both `BackupTitle` and `BackupComment` are present, it writes one blank logging record between them for readability; title-only/comment-only configurations avoid the extra blank line.

### `format_runtime_duration(elapsed_seconds)`

Converts the non-negative monotonic elapsed duration to `HH:MM:SS.mmm`. Millisecond precision is retained for short runs and hours are not limited to two digits.

### `format_transfer_size(transferred_bytes)`

Formats the non-negative measured byte total using 1024-based thresholds and automatically selects `KB`, `MB`, `GB`, or `TB`, always with two decimal places. Values below 1 KiB are intentionally rendered as a fractional `KB` so the final summary stays inside the requested unit set instead of adding a separate bytes unit.

### `format_missing_dataset_failures(replication_summary)`

Formats every recorded missing-data failure as `source -> destination` followed by the matched ZFS/Syncoid lines. It is shared by the top-level error diagnostics and failure email so the same pair/reason formatting is not duplicated.

### `format_final_run_summary(app_config, elapsed_seconds, replication_summary=None)`

Builds the canonical plain-text final summary shared by logging and email. It renders `Final run summary`, one blank line, then the optional metadata. When both metadata fields exist it renders `BackupTitle`, one blank line, the multiline `BackupComment` with aligned continuation lines, and another blank line. When a completed `ReplicationSummary` is supplied it then renders `Data transferred` using `format_transfer_size()` if measurement was complete, otherwise `Data transferred :   Unavailable`; one blank line follows the transfer row before `Total runtime`. Ordinary interrupted failure/legacy callers that do not have a complete replication summary retain the runtime-only form. The missing-dataset/pool path deliberately completes the remaining list, so it may pass that completed summary and report the measured transfer total alongside the failure. Keeping this as plain text prevents terminal, `.log`, and email layouts from drifting apart.

### `log_final_run_summary(app_config, elapsed_seconds, logger, replication_summary=None)`

Writes `format_final_run_summary()` one physical line at a time through the normal logger, wrapped in the existing separator block. On success this happens before mail is constructed, so the file handler has already written/flushed both the transfer total and runtime into `.log`; ordinary interrupted failure paths use the same function without claiming a complete transfer total, while the completed-list missing-data failure can safely pass its collected summary.

### `log_startup_configuration(app_config, run_context, logger)`

Logs startup details while hiding secrets.

It logs only `[Syncerate Config]`, never unrelated INI sections. It omits `PassWord`, MQTT username/password, common secret-like option names (`password`, `secret`, `token`, `credential`, API-key forms), and disabled integration-only settings. This preserves useful diagnostics while reducing the chance that a shared INI file or a future secret option is echoed accidentally.

The startup `Backup information` heading is followed by a blank logging record before the metadata for readability. Backup metadata and other configuration values are emitted through `log_multiline_value()`, so standard INI continuation lines cannot inject unprefixed physical lines into the output.

## `syncerate/datasets.py`

### `missmatchinglists(Lenght, Names, logger)`

Logs either a list-length error or final-dataset-name mismatch, then raises `SyncerateError` with exit code `1`.

The original parameter names and messages are preserved for behavior compatibility.

### `read_dataset_list(path)`

Reads active lines from a source or destination file. It strips surrounding whitespace and ignores:

- blank lines;
- lines beginning with `#`.

Dataset names containing internal spaces remain intact.

### `parse_destination_line(line)`

Splits optional destination-specific arguments from the first exact `: ` separator.

Example:

```text
backup@host:Pool/Data: --recvoptions="o compression=zstd"
```

becomes:

- destination: `backup@host:Pool/Data`;
- extra argv: `--recvoptions=o compression=zstd`.

The SSH `host:dataset` colon is not followed by a space, so it is not confused with the separator. Splitting only once also allows a quoted extra-argument value to contain later `: ` text. `shlex.split()` preserves quoted argument grouping and reports malformed quoting.

### `parse_destination_list(destination_lines)`

Runs `parse_destination_line()` for every destination and returns matching dataset and argument lists. It is retained as a separately testable parser helper.

### `load_dataset_pairs(app_config, logger)`

Loads, logs, validates, and combines both files.

It verifies:

1. both files contain at least one active dataset;
2. source and destination counts match;
3. neither side ends with `/`, preventing an accidental empty final component;
4. the final dataset component in each positional pair matches.

It then returns `list[DatasetPair]`, keeping each pair and its extra arguments together. These checks run before Syncoid is started.

## `syncerate/notifications.py`

This module contains all optional email, MQTT, and Home Assistant behavior.

### `BROKEN_PIPE_SUCCESS_SUBJECT`

Retains the compatibility email subject for callers supplying a Broken Pipe warning summary: `Syncerate Succsful - WARNING BROKEN PIPE`. Keeping it in one constant prevents the logged/body wording and mail subject from drifting apart.

### `backup_header_text(app_config)`

Builds the legacy optional backup-title/comment email prefix. It remains public and exported through `Syncerate.py` for compatibility with existing imports/manual `MailTo()` usage. Runtime-aware normal application mail uses the helper below.

### `run_summary_header_text(app_config, runtime_seconds, replication_summary=None)`

Builds the email header from the shared `format_final_run_summary()` formatter whenever a runtime is supplied, followed by the normal separator. Success callers (including compatibility warning-summary callers) pass their completed `ReplicationSummary`, so email gets the same title/blank-line/comment/blank-line/transfer-total/runtime layout already written to terminal and `.log`. Failure callers omit the replication summary because an interrupted run cannot claim a complete total. If a legacy/manual caller supplies no runtime, it falls back to `backup_header_text()` rather than dropping the old metadata.

### `send_mail(subject, body, recipient, attachment_files=None)`

Runs the local command:

```bash
mail -s <subject> <recipient> --attach <file> ...
```

The email body is passed on standard input. The function returns the command exit code and stderr instead of terminating the application.

### `WasMailSent(mail_exit_code, popen_stderr, logger)`

Logs whether the local mail program accepted the message. It keeps the existing public function name for compatibility.

### `MailTo(app_config, run_context, logger, ..., ReplicationSummaryData=None)`

Builds the current success and failure message variants:

- successful run;
- a Broken Pipe warning summary supplied by a compatibility caller (current execution stops on retry exhaustion);
- missing ZFS dataset/pool failure after the remaining list has completed;
- script error;
- Syncoid error;
- MQTT error.

When called from `main()`, `RuntimeSeconds` carries the already captured monotonic run duration. Successful calls pass `ReplicationSummaryData`, and the special missing-data failure also passes it because the list has deliberately finished. That missing-data mail uses an explicit subject, reports exit code `8`, lists every affected source/destination pair plus its matched ZFS/Syncoid reason, and can include the completed transfer total. Other interrupted error variants omit the summary so they do not present a possibly incomplete total. For compatibility callers supplying a Broken Pipe warning summary, the subject is exactly `Syncerate Succsful - WARNING BROKEN PIPE`. The body reports the configured per-dataset retry count and wait time, then lists each skipped dataset pair. When logging is enabled it attaches available `.log`, `.err`, and `.out` files. When logging is disabled it sends a text-only message. It does not call `sys.exit()`.

### `mqtt_error_output(error, max_chars=4000)`

Collects the most useful captured child/Syncoid output for a JSON failure report. It joins available Pexpect/Syncoid error text and keeps only the last 4000 characters by default so an MQTT error payload cannot grow without bound. It never includes configuration credentials directly.

### `build_mqtt_status_payload(app_config, *, success, exit_code, error_message="", stderr_text="", replication_summary=None)`

Builds the structured Home Assistant status JSON. The payload contains:

- `status`: `success` or `failure`;
- `success`: real JSON Boolean;
- `title`: `BackupTitle` or `Syncerate`;
- `name`: the same title value kept as a compatibility alias for older automations;
- `job`: `syncerate`;
- `exit_code`;
- `error`;
- `stderr`;
- `warning`;
- `skipped_datasets`;
- `failed_datasets`.

The configured `SyncoidCommand` is deliberately excluded from MQTT JSON so connection endpoints, key paths, and command options are not exposed to MQTT subscribers. For compatibility callers supplying a Broken Pipe warning summary, the payload retains the success status, warning flag, and skipped dataset list. Current execution stops with code `2` on retry exhaustion and publishes a failure. Missing dataset/pool runs publish `status: failure`, exit code `8`, and structured source/destination/reason objects in `failed_datasets`. `json.dumps()` is used instead of hand-built JSON so quotes, newlines, and non-ASCII text are escaped correctly.

### `send_mqtt_messages(app_config, logger, *, success=True, exit_code=0, error_message="", stderr_text="", replication_summary=None)`

Publishes retained success signals and non-retained JSON events using the existing payload builder.

Important behavior:

1. The function can be reached when either `Use_MQTT` or `MQTT_JSON_Status` is enabled.
2. `paho.mqtt.publish` is imported lazily only when an MQTT publish is actually attempted.
3. On a successful run with `Use_MQTT = Yes`, the configured `mqtt_message` is published to `mqtt_topic` with `retain=True`, preserving the historical Syncerate behavior.
4. On that same legacy path, validated `app_config.use_home_assistant` additionally publishes retained payload `online` to `HomeAssistant_Available`, preserving historical behavior without reparsing the raw Boolean.
5. `MQTT_JSON_Status = Yes` independently publishes structured success/failure JSON to `mqtt_json_topic` with `retain=False` hard-coded. JSON never replaces or shares the old retained topic.
6. When `Use_MQTT` is enabled without `MQTT_JSON_Status`, failures use the same JSON payload on the exact `mqtt_topic` plus `/error`. The derived subtopic keeps retained success/HA consumers separate. When JSON status is enabled, its dedicated topic takes precedence and no duplicate error is published.
7. `app.successfull_run()` calls this function for successful runs only when `send_mqtt_on_success` is true. The notification function itself still accepts `success=False` for the independent failure path.
8. Fatal failure calls produce only JSON status; the old success-only MQTT and HA availability signals are not emitted for a failed run.
9. Publish/dependency failures still raise `SyncerateError` with exit code `10`.

### `send_mqtt_failure_status(error, app_config, logger, replication_summary=None)`

Best-effort fatal-failure publisher used by the top-level exception boundary whenever either `Use_MQTT` or `MQTT_JSON_Status` is enabled. `SendMQTTOnSuccess` is intentionally not consulted here: disabling success MQTT must never hide configured failure reporting. The optional completed `ReplicationSummary` is forwarded for the missing-data path so `failed_datasets` is populated. It calls `send_mqtt_messages()` with `success=False`, so one non-retained JSON failure event is published on `mqtt_json_topic` when JSON status is enabled, or `<mqtt_topic>/error` for `Use_MQTT` alone. If that MQTT publish also fails, the secondary failure is logged but the original application exit code is preserved. MQTT-originated errors are skipped to prevent recursion.

### `send_error_mail(error, app_config, run_context, logger, runtime_seconds=None, replication_summary=None)`

Chooses the correct `MailTo()` variant from the error kind and forwards the captured runtime. It checks only whether `Mail` itself is enabled; `SendMailOnSuccess` is intentionally ignored so disabling successful-run mail never suppresses configured error mail. For `dataset_missing`, it also forwards the completed `ReplicationSummary` so the dedicated exit-code-`8` email lists failed pairs/reasons and can include the completed transfer total. Notification failure is caught and logged so it cannot replace the original application exit code.

## `syncerate/system_actions.py`

### `SystemAction(app_config, logger)`

Runs the configured successful-run shell command.

When mail is also enabled, the existing two-minute delay is preserved to allow the mail command time before a shutdown or similar action. Without mail, the command runs immediately.

It uses:

```python
subprocess.run(command, shell=True, check=False)
```

The function has one execution path for mail/no-mail cases. It logs execution exceptions and non-zero shell return codes explicitly instead of raising the reserved exit code `11`, preserving the established best-effort post-success behavior. When mail is enabled it still waits exactly 120 seconds before the action.

## `syncerate/syncoid_runner.py`

This module contains all credential resolution, Syncoid command construction, `pexpect` monitoring, retry behavior, and transfer result handling.

### `resolve_password(app_config, logger)`

Handles:

- `PassWord = Ask`: securely prompts with `getpass()`;
- `PassWord = No`: returns `None`;
- any other value: treats it as the configured literal credential.

The credential is never written to logs.

### `safe_text(value)`

Converts optional `pexpect` values into safe strings. `None` becomes an empty string so error construction does not fail while handling another failure.

### `send_secret(child, password, output_handle, logging_enabled, *, wait_for_noecho=True)`

Central secret-sending helper. It detaches the Pexpect logfile, optionally waits up to three seconds for terminal echo to turn off, sends the secret, and always restores the logfile in `finally`. If the direct-child path expects no-echo and it never activates, the helper refuses to send the secret and raises code `5`.

Direct `ssh-add` uses the default no-echo safety check. Nested Syncoid password/passphrase prompts reuse the same logfile-safe helper with `wait_for_noecho=False`, preserving the established 0.4.21 direct-send behavior while removing duplicated detach/restore code.

### `extract_ssh_key_path(command_template)`

Parses `SyncoidCommand` with `shlex.split()` and returns the last `--sshkey FILE` or `--sshkey=FILE` value, matching Syncoid's single scalar key option. Private-agent mode deliberately reuses the existing Syncoid key setting instead of introducing a second identity path that could drift out of sync. A malformed `--sshkey` fails before replication starts.

### `start_private_ssh_agent(app_config, logger)`

Creates one isolated agent for the whole Syncerate run. It:

1. requires an existing regular file selected by `--sshkey`;
2. requires `ssh-agent` and `ssh-add`;
3. creates a random `syncerate-ssh-agent-*` temporary directory and forces mode `0700`;
4. discards any inherited `SSH_AUTH_SOCK`, `SSH_AGENT_PID`, and `SSH_ASKPASS`;
5. forces `SSH_ASKPASS_REQUIRE=never`;
6. starts `ssh-agent -D` in the foreground with a fixed private socket and configured identity lifetime;
7. waits up to five seconds for the Unix socket and validates that it is actually a socket;
8. forces the socket mode to `0600`;
9. returns `SSHAgentSession` with the environment that only points at this agent.

Running the agent in the foreground gives Syncerate a real child PID it can terminate directly instead of parsing/evaluating shell output. The bounded OpenSSH identity lifetime limits how long an orphaned agent can still authenticate if the parent is terminated without running Python cleanup.

### `add_identity_to_private_agent(session, password, logger)`

Runs `ssh-add -q -t <lifetime> <identity>` under Pexpect **directly**, which is the path verified to accept the encrypted-key passphrase on newer OpenSSH. It matches the complete `Enter passphrase for ...:` prompt, reuses `send_secret()` for no-echo input, never attaches the Syncerate output logfile, and fails instead of repeatedly sending the same rejected secret. Unencrypted keys can load with `PassWord = No`; encrypted keys require a resolved passphrase.

### `private_agent_has_identity(session)`

Checks that the private agent process is alive and runs `ssh-add -l` against only its socket. Return code `0` means an identity is present, `1` means the bounded lifetime expired or the agent is empty, and other statuses are treated as an agent failure. This check avoids blindly assuming a long Syncerate job still has a usable key.

### `ensure_private_agent_identity(session, password, logger)`

Runs before each dataset when agent mode is enabled. If the isolated agent became empty because the configured lifetime expired, it reloads the same identity using direct Pexpect/`ssh-add`. An already-authenticated Syncoid SSH control connection does not need the key to remain loaded, so refresh is only needed before starting the next dataset.


### `stop_private_ssh_agent(session, logger)`

Best-effort cleanup first asks the private agent to remove all identities with `ssh-add -D`, then terminates the foreground agent, escalates to kill only if it fails to stop within three seconds, and removes the random socket directory. Cleanup errors are logged instead of hiding the original replication/application error.

### `private_ssh_agent(app_config, password, logger)`

A context manager around the complete replication list. When `UseSSHAgent` is disabled it simply yields `None`, preserving legacy behavior. When enabled it starts the isolated agent, loads the key, yields the session to `run_replications()`, and always calls cleanup in `finally` for normal completion and Python exceptions.

### `close_child_logfile(child, logger=None)`

Flushes and closes the per-child `.out` handle without closing the child itself. It clears `child.logfile` to prevent duplicate closes.

### `die(...)`

Converts the former internal termination paths into `SyncerateError`.

For a known child-output error it:

1. captures `child.before`, `child.after`, and `child.buffer`;
2. force-terminates the child;
3. closes the output logfile;
4. raises a categorized error.

For a completed Syncoid child with a nonzero status, it captures the last output and raises a `syncoid` error. It never calls `sys.exit()`.

### `log_command_debug(command_list, logger)`

Logs three representations of the command:

- shell-style with `shlex.join()`;
- raw Python argv list;
- each indexed argument.

This is important for proving that dataset names containing spaces remain one process argument.

### `build_syncoid_command(command_template, source_dataset, destination_dataset, extra_args=None)`

Builds an argv list safely:

1. parses the command template with `shlex.split()`;
2. replaces `SourceDataSet` and `DestDataSet` inside already-separated arguments;
3. appends destination-specific arguments.

Replacing placeholders after splitting preserves spaces inside dataset names.

### `effective_user_name()`

Returns the username belonging to the effective UID. It falls back to `UID <number>` when no passwd entry is available.

This confirms that local commands run as the user executing Syncerate. Remote commands remain under the SSH user written in the endpoint.

### `pv_amount_to_bytes(amount_text, unit_text)`

Converts one parsed `pv` progress amount to integer bytes. It accepts both period and comma decimal separators, binary `B/KiB/MiB/GiB/TiB/PiB/EiB` units, and decimal `KB/MB/GB/TB/PB/EB` units. This is intentionally limited to recognized progress fields rather than Syncoid's rounded estimate text.

### `TransferByteCounter`

Stateful stream-aware parser used by one monitored Syncoid attempt. It watches Syncoid transfer-start lines and normal `pv -b` progress output, keeps only the maximum byte value seen for the current send stream, commits that value when the next stream starts, and sums streams without double-counting carriage-return progress refreshes.

#### `__init__(measurement_possible=True)`

Initializes the total/current-stream byte state and records whether progress measurement is expected at all. Keeping this state per Syncoid attempt avoids mutable process-global accounting; setting `measurement_possible=False` for `--quiet` prevents Syncerate from presenting an invented transfer size.

#### `_finish_current_transfer()`

Commits only the maximum byte counter observed for the active stream and resets its temporary state. If a stream started but never exposed a byte counter, it marks the attempt incomplete; this prevents carriage-return refreshes from being double-counted and prevents missing measurements from being guessed.

#### `_start_transfer()`

Finishes the previous stream and starts a fresh stream-accounting window. This is required because one Syncoid invocation can perform several send streams and each stream's `pv` counter restarts from zero.

#### `_process_line(line)`

Recognizes Syncoid transfer-start lines and parseable `pv` progress lines, updating only the maximum byte value for the active stream. It also tolerates a parseable `pv` line without a recognized heading so compatible Syncoid/custom output is still measured instead of discarded.

#### `feed(text)`

Consumes arbitrary Pexpect output chunks, joins them with any buffered partial line, and treats both carriage return and newline as progress boundaries. This is necessary because `pv` commonly refreshes one terminal line with `\r` rather than emitting only newline-terminated records.

#### `finish()`

Processes any final partial buffered line, commits the last stream, and returns `(total_bytes, measurement_complete)`. Centralizing finalization ensures EOF and other monitored exit paths use the same complete accounting result.

The counter measures bytes actually sent through Syncoid's stream pipeline. Repeated progress updates are not double-counted, while a Broken Pipe retry is a new attempt and therefore its actually retransmitted bytes are intentionally included in the run total.

### `build_attempt_result(child, modified_command, transfer_counter, *, repeated_pattern, ignored_missing_destroy_snapshot, broken_pipe_detected=False, missing_dataset_or_pool_detected=False, missing_dataset_or_pool_messages=())`

Finalizes the attempt's `TransferByteCounter` and constructs one `SyncoidAttemptResult` with process/error flags, recognized missing-data evidence, and measured byte fields. Centralizing this return path ensures EOF, Broken Pipe, and repetition-stop exits cannot forget to finalize accounting.

### `read_warning_line(child, prefix)`

Consumes the remainder of a matched warning up to CR, LF, or EOF and returns the complete text, including the prefix already matched by `ssh_command()`. This prevents words inside a warning from reaching password, connection, missing-dataset, or Broken Pipe handlers when output is delivered in several chunks. Pexpect continues writing raw output to the configured `.out` logfile. A final unterminated warning is processed at EOF.

### `ssh_command(syncoid_command, password, run_context, logger, retry_broken_pipe=False, process_env=None, continue_without_resume=True)`

Starts Syncoid under Pexpect using an argv list and optional private-agent environment. The monitor processes warnings as complete lines before considering error/prompt matches on the same line. Labels `WARN` and `WARNING` are matched case-insensitively at a line boundary, with optional indentation. A following delimiter is required so an ordinary word such as `WARNINGS` is not mistaken for a warning.

Warning behavior:

1. Read the whole line through `read_warning_line()` before classifying its contents.
2. If the warning body begins `ZFS resume feature not available`, log it. Continue when `continue_without_resume` is true; otherwise terminate the child through `die()` with code 4. The normal application error boundary then handles error notifications.
3. Recognize only the exact disappeared-dataset skip warning as missing-data evidence, record its full text, and wait for the real child status. Ignore other ordinary warning lines, including generic skips, cleanup, and known-host warnings.
4. Retain silent bookkeeping for Syncoid's stale receive-state reset announcement. This preserves the existing handling of a subsequent non-warning Broken Pipe during recovery; the warning itself never fails the run.
5. Exclude warning text from transfer accounting while preserving the preceding line boundary, so words resembling transfer headings cannot change the byte total. Raw `.out` capture remains intact.

Non-warning behavior remains:

- SSH host-key confirmation is answered with `yes`.
- Real password/passphrase prompts use `send_secret()`; no configured password yields code 5.
- Permission denied, connection timeout, and connection refusal use codes 5, 6, and 7.
- The known missing destroy-snapshot message is remembered without masking a later non-zero exit.
- Missing stale-resume source output marks recovery active. Fresh `INFO: Sending incremental/full` output clears it.
- A non-warning Broken Pipe follows recovery and optional retry handling. When missing-data evidence is already recorded, wait for the actual child status instead of treating its secondary Broken Pipe as a separate retry condition.
- Complete non-warning missing dataset/pool and destination-parent/receive errors matching `_ZFS_MISSING_DATASET_OR_POOL_TEXT` record deferred failure evidence. EOF checks the remaining unterminated lines using the same expression. Generic no-datasets messages and missing snapshots/bookmarks do not qualify.
- EOF returns the actual child and attempt summary; `run_replications()` checks its exit status or signal.

Only automatically answered interactive host-key/password/passphrase patterns are limited to five matches. Warnings and normal transfer progress have no repetition limit. Error-looking text within an ordinary warning is ignored, but a following separate non-warning error is handled normally.

### `run_replications(app_config, run_context, dataset_pairs, password, logger, ssh_agent_session=None)`

Runs all validated pairs sequentially.

For each pair it:

1. builds the command exactly from `SyncoidCommand`, the dataset pair, and per-destination arguments;
2. when private-agent mode is active, verifies/reloads the one agent identity but **does not modify the Syncoid argv**;
3. logs extra arguments and argv details;
4. passes `app_config.continue_without_resume` to `ssh_command()` for every attempt, with Pexpect controlling Syncoid in both agent and non-agent modes; agent mode only adds the isolated `SSH_AUTH_SOCK` environment and still passes `PassWord` to the original nested-prompt handler;
5. leaves stale interrupted-receive recovery inside the same Syncoid process instead of constructing a second resume-bypass command;
6. when enabled, gives each dataset its own `app_config.broken_pipe_retry_count` allowance and waits `app_config.broken_pipe_retry_wait_seconds` before every ordinary Broken Pipe retry;
7. raises a script error with code `2` when ordinary Broken Pipe retries are exhausted, stopping the whole list; zero retries fails on the first ordinary Broken Pipe;
8. closes the child;
9. converts signal termination to `128 + signal`;
10. only when a recognized runtime missing-data error or the exact disappeared-dataset warning was observed, accepts Syncoid exit `0`, `1`, or `2`, records a `MissingDatasetFailure`, and continues to the next pair; exit codes alone never permit continuation;
11. preserves any other real Syncoid exit code immediately, including an exit outside `0`/`1`/`2` after earlier missing-data text, so a later unrelated failure is not masked;
12. treats the missing-destroy-snapshot message as nonfatal only if Syncoid ultimately exits `0`; any other exit remains authoritative;
13. adds each attempt's actual measured bytes to the run-level `ReplicationSummary` and ANDs its completeness flag into the run-level measurement status.

The function returns `ReplicationSummary`, including any accumulated missing-data failures, instead of raising code `8` immediately. This allows the remaining configured pairs to run before `app.main()` marks the overall run failed. `broken_pipe_retries_used` is initialized inside the dataset loop, so every dataset pair receives the full configured retry count independently. Bytes transferred by failed Broken Pipe attempts remain part of the total because those bytes really crossed the send pipeline before the retry; the replacement attempt contributes its own bytes separately. No transfer is started in parallel, preserving sequential behavior.

## `syncerate/app.py`

### `log_syncerate_error(error, logger)`

Writes the appropriate final diagnostics for:

- known matched child errors;
- deferred missing ZFS dataset/pool failures, including every recorded pair/reason and the final script exit code;
- unknown Syncoid nonzero exits;
- MQTT failures;
- general script failures.

List validation already writes its detailed message in `datasets.py`, so it is not duplicated here.

### `successfull_run(app_config, run_context, logger, replication_summary=None, runtime_seconds=None)`

Runs the post-transfer order after successful replication. For compatibility, callers can also supply a Broken Pipe warning summary to select warning text; current `main()` stops on retry exhaustion before reaching this function:

1. append successful-run text to `.out` when enabled;
2. when `send_mqtt_on_success` is true, publish original retained MQTT/optional HA success signals when `Use_MQTT` is enabled plus independent non-retained JSON success status when `MQTT_JSON_Status` is enabled; when false, skip every successful-run MQTT publish without changing the configured failure path;
3. write the completed transfer total plus already captured runtime summary to terminal/`.log`;
4. when both `Mail` and `send_mail_on_success` are enabled, attempt best-effort success email using that same `ReplicationSummary` and runtime value; when success mail is disabled, skip only that success email;
5. best-effort system action.

Writing the summary before step 4 guarantees the email's `.log` copy/attachment already contains both `Data transferred` and `Total runtime`. `runtime_seconds=None` remains supported for compatibility with direct internal/manual calls. MQTT failure during an attempted success publish remains fatal with code `10`. Success-mail exceptions are logged instead of masking completed replication, and the system action still runs afterward. The two success switches are deliberately confined to this function; top-level error notification helpers do not consult them. System-action failure is likewise logged without changing the completed replication result.

### `main(argv=None)`

Owns all startup and the final exception boundary.

Execution order:

1. capture a monotonic start time immediately before argument parsing;
2. parse arguments (`--help`/`--version` still exit through argparse without a runtime summary);
3. load and strictly validate `AppConfig`;
4. create `RunContext`;
5. configure logger;
6. log safe startup settings;
7. load and validate `DatasetPair` objects;
8. resolve the optional password/passphrase;
9. enter `private_ssh_agent()` (a no-op when disabled);
10. run all replications and collect `ReplicationSummary`;
11. leave the agent context so identities/socket/process are cleaned before notifications;
12. if `ReplicationSummary.has_missing_dataset_failure` is true, build one code-`8` `dataset_missing` error containing all affected pairs/reasons instead of entering the success stage;
13. otherwise capture the monotonic elapsed runtime and pass it into successful completion handling;
14. return `0` only when no fatal/completed-list failure exists.

For the deferred missing-data failure, the exception boundary passes the completed `ReplicationSummary` into final-summary logging, MQTT JSON failure reporting, and the dedicated failure email. This preserves the already processed transfer total and structured `failed_datasets` details while still preventing success-only MQTT and `SystemAction` execution. Expected file/config/parser errors during `load_app_config()` are first converted into a clear script/configuration `SyncerateError` with code `2`. Known and unexpected errors log their diagnostics, capture/log the monotonic runtime before failure notifications, best-effort publish JSON failure status where applicable, and pass the same runtime into error mail. This ordering deliberately excludes the time needed to send the email itself and any later `SystemAction`; that is the only way the email can contain the same stable runtime value that is already present in the `.log` it attaches.

## Configuration and command data flow

```text
--conf path
    -> cli.parse_arguments()
    -> config.load_app_config()
    -> models.AppConfig

AppConfig
    -> logging_setup.create_run_context()
    -> models.RunContext

AppConfig dataset paths
    -> datasets.load_dataset_pairs()
    -> list[DatasetPair]

AppConfig + password
    -> syncoid_runner.private_ssh_agent()
    -> optional SSHAgentSession

AppConfig + RunContext + DatasetPair + password + optional SSHAgentSession
    -> syncoid_runner.run_replications()
    -> SyncoidAttemptResult per attempt
    -> ReplicationSummary for the full list

Successful completion
    -> notifications
    -> system_actions
```

This explicit flow is why modules do not need shared mutable runtime globals.
## Standalone PyInstaller packaging

### `Syncerate.spec`

- Defines the checked-in PyInstaller build recipe instead of relying on generated command-line state.
- `collect_submodules("pexpect")`: explicitly includes the Pexpect package family used by Syncoid/SSH interaction.
- `collect_submodules("paho.mqtt")`: explicitly includes all MQTT submodules even though Paho is imported dynamically inside notification code only when MQTT is enabled. This prevents a standalone build from working without MQTT but failing later when MQTT is turned on.
- `Analysis(...)`: starts dependency analysis at the compatibility entry point `Syncerate.py` and adds the explicit third-party hidden imports.
- `PYZ(...)`: creates the compressed Python module archive used by the executable.
- `EXE(...)`: creates one console executable named `Syncerate`; one-file mode is achieved by passing analyzed binaries/data directly into `EXE` without a `COLLECT` stage. UPX is deliberately disabled for predictable builds.

### `build_pyinstaller.sh`

- Uses `set -euo pipefail` so missing variables and failed build/check commands stop the build instead of leaving a misleading partial release.
- Resolves the project root from the script location and builds from that directory so the command works regardless of the caller's current working directory.
- Imports `PyInstaller`, `pexpect`, and `paho.mqtt` before building and reports a clear dependency error before deleting/creating release output if a required build module is unavailable.
- Removes only generated `build/` and `dist/` directories, then invokes `python -m PyInstaller --clean --noconfirm Syncerate.spec`.
- Verifies that `dist/Syncerate` exists and is executable.
- Runs the new executable with `--version`, derives the expected program name from `basename dist/Syncerate`, and checks for exactly `Syncerate 0.4.35`, then runs `--help`; a broken/incomplete frozen application therefore fails the build script without falsely expecting the source filename `Syncerate.py`.

### `requirements-build.txt`

- Pins `PyInstaller`, `pyinstaller-hooks-contrib`, `pexpect`, and `paho-mqtt` for the documented standalone build environment. Transitive dependencies are resolved by pip.
- These packages are build inputs; a user running `dist/Syncerate` does not install them separately.

## Regression test suite

The packaged `tests/` directory uses only Python `unittest` plus Syncerate's existing runtime dependency `pexpect`; it does not require pytest. Real tiny child processes are used where Pexpect behavior matters.

### `tests/helpers.py`

- `make_logger(name)`: isolated non-propagating logger for tests.
- `make_config(**overrides)`: constructs a valid in-memory `AppConfig` while allowing one field to be varied.
- `no_logging_context()`: creates a `RunContext` with file logging disabled.
- `write_executable(path, body)`: writes an executable temporary Python program used as a fake Syncoid child.

### `tests/test_config.py` — `ConfigTests`

`load_text()` writes and loads temporary INI content. The test methods cover the shipped example config, compatibility `option_is_enabled()`, strict Boolean spellings/typos, the enabled-by-default and explicitly-disabled success-notification controls, empty required values, Syncoid placeholder/shlex validation, enabled MQTT broker/port/topic requirements, Home Assistant availability requirements, and JSON topic separation.

### `tests/test_datasets.py` — `DatasetTests`

Covers blank/comment filtering, quoted `: ` inside extra arguments, malformed quoting, empty active lists, count mismatch, final-name mismatch, trailing-slash rejection, and preservation of per-destination argv.

### `tests/test_syncoid_runner.py` — `SyncoidRunnerTests`

`run_fake()` executes temporary fake Syncoid processes under the real Pexpect monitor. Tests cover command construction, private-agent-disabled behavior, secret no-echo refusal, missing-destroy status preservation, ignored warning lines, configurable resume-unavailable handling, streamed/unterminated warnings, preserved non-warning errors and signals, benign `password`/`WARNINGS` text, real passphrase and OpenSSH password prompts, repeated normal send progress, Broken Pipe retry and fatal exhaustion behavior, and repeated host-key prompts.

### `tests/test_notifications.py` — `NotificationTests`

Covers the runtime-aware email summary header, compatibility JSON warning-summary/skipped-pair payloads, failure payload contents, bounded MQTT stderr extraction, actual publish arguments for each MQTT mode, independent success switches, disabled channels, and verifies that `SendMailOnSuccess`/`SendMQTTOnSuccess` never suppress their corresponding configured error-notification paths.

### `tests/test_packaging.py` — `PackagingTests`

Static tests verify the checked-in spec is one-file, explicitly collects Pexpect/Paho MQTT, pins build inputs, and keeps the build wrapper's clean-build and frozen-CLI verification safeguards.

### `tests/test_system_actions.py`

- `ListHandler.__init__()` / `emit()`: tiny capture handler used to inspect action logs.
- `SystemActionTests.setUp()`: builds an isolated logger for each case.
- test methods verify disabled actions do not invoke a shell, nonzero actions are logged without becoming fatal, and the 120-second mail delay remains intact.

### `tests/test_app_and_logging.py` — `AppAndLoggingTests`

- `write_config()`: creates a temporary end-to-end config plus dataset lists.
- test methods verify success-mail exceptions remain best-effort while the system action continues, success mail and MQTT can each be disabled without affecting unrelated post-run behavior, startup log redaction excludes unrelated sections/secrets, multiline comments remain separate prefixed log records, runtime/transfer-size formatting and final-summary ordering are stable, unavailable transfer measurement is represented honestly, a real `main()` success emits the summary block, a fake Syncoid success reaches exit `0`, empty lists return code `1`, and invalid Boolean configuration returns code `2` before the child can run.

`tests/__init__.py` only marks the test package and intentionally contains no runtime logic.

## Bundled non-Python files

- `README.md`: current user-facing installation/configuration/operation guide only. Release history belongs in `VERSIONING.md`.
- `VERSIONING.md`: every created release and its code/behavior/documentation changes.
- `Syncerate.spec`, `build_pyinstaller.sh`, and `requirements-build.txt`: reproducible one-file standalone build definition, wrapper, and pinned build inputs.
- `dist/Syncerate`: release artifact when a PyInstaller build has been produced; it is platform-specific and is intentionally not imported by source-mode tests.
- `config/example-Syncerate.cfg`: complete option example kept synchronized with the loader.
- `config/example-source-file` / `config/example-dest-file`: list syntax examples.
- Home Assistant YAML examples: legacy availability and JSON-status consumption examples.
- `_layouts/default.html` / `_config.yaml`: GitHub Pages presentation files. Version 0.4.23 removed the unused jQuery 1.12.4 include because no project code uses it.
- `config/destlist-bck` and the two PNGs are preserved original reference/example assets even though the Python runtime does not import them.

## Exact test symbol index

Every test/helper function is listed here explicitly so the code map remains exhaustive as the regression suite grows. Each `test_*` method exists to lock the behavior described by its name and prevent that specific regression from returning.

### `tests/helpers.py`

- `make_logger()`: creates an isolated non-propagating logger.
- `make_config()`: creates a safe AppConfig with overridable fields.
- `no_logging_context()`: creates a terminal-only RunContext.
- `write_executable()`: writes an executable temporary Python child for process tests.

### `tests/test_app_and_logging.py`

- `AppAndLoggingTests`: groups the tests and their shared setup for this module.
- `test_cli_help_describes_every_application_flag()`: verifies `--help` exits successfully and documents `--conf`/`-c`, `--version`, the required-config semantics, and the examples footer.
- `test_runtime_duration_formats_hours_minutes_seconds_and_milliseconds()`: verifies the monotonic duration formatter, including hour rollover and negative-value clamping.
- `test_transfer_size_chooses_kb_mb_gb_or_tb_automatically()`: verifies 1024-based automatic unit selection and fractional-KB output.
- `test_final_summary_marks_transfer_size_unavailable_when_pv_measurement_is_incomplete()`: verifies incomplete `pv` measurement is shown as `Unavailable` rather than guessed.
- `test_final_summary_logs_title_multiline_comment_then_runtime()`: verifies heading/title/comment/transfer-total/runtime ordering, multiline rendering, the blank line after `Final run summary`, the required blank line between title and comment, and the blank line before run statistics, plus the blank line between `Data transferred` and `Total runtime`.
- `test_startup_multiline_comment_prefixes_every_physical_log_line()`: verifies multiline configuration/comment values cannot create unprefixed physical log lines and that startup metadata includes a blank line after `Backup information` plus the requested blank line between title and comment.
- `test_success_mail_exception_is_best_effort_and_system_action_still_runs()`: regression check that success mail exception is best effort and system action still runs.
- `test_success_mail_can_be_disabled_without_disabling_system_action()`: verifies `SendMailOnSuccess = No` suppresses only successful-run mail while the independent system action still executes.
- `test_success_mqtt_can_be_disabled()`: verifies `SendMQTTOnSuccess = No` prevents the success stage from calling the MQTT publisher even when legacy and JSON MQTT are configured.
- `test_success_mail_and_attached_log_include_runtime_before_mail_is_sent()`: end-to-end regression for the 0.4.24 ordering bug; verifies the email header and copied `.log` content already contain `Data transferred` and `Total runtime` when `send_mail()` is called.
- `test_logging_omits_unrelated_sections_and_secret_like_options()`: regression check that logging omits unrelated sections and secret like options.
- `write_config()`: builds temporary source/destination files plus a runnable end-to-end config.
- `test_main_success_path_with_fake_syncoid()`: regression check that main success path with fake syncoid.
- `test_main_emits_final_runtime_summary()`: end-to-end check that a real successful `main()` run prints backup metadata, `Data transferred`, and `Total runtime`.
- `test_main_rejects_empty_active_lists_with_code_1()`: regression check that main rejects empty active lists with code 1.
- `test_main_rejects_invalid_boolean_before_replication_with_code_2()`: regression check that main rejects invalid boolean before replication with code 2.

### `tests/test_config.py`

- `ConfigTests`: groups the tests and their shared setup for this module.
- `load_text()`: writes temporary INI text and returns the validated AppConfig.
- `test_shipped_example_config_loads()`: regression check that shipped example config loads.
- `test_valid_minimal_config_loads()`: regression check that valid minimal config loads.
- `test_success_notification_switches_default_to_enabled_when_omitted()`: verifies both new success-notification controls preserve legacy behavior by defaulting to true when absent.
- `test_success_notification_switches_can_be_disabled()`: verifies both new controls accept documented disabled Boolean spellings and normalize to false.
- `test_success_notification_switch_rejects_invalid_boolean()`: verifies typo/ambiguous values for the new controls fail startup validation instead of silently changing notification behavior.
- `test_multiline_backup_comment_uses_ini_continuation_lines()`: verifies indented INI continuation lines load into `backup_comment` as embedded newlines.
- `test_option_is_enabled_remains_compatibility_helper()`: regression check that option is enabled remains compatibility helper.
- `test_boolean_typo_is_rejected_by_loader()`: regression check that boolean typo is rejected by loader.
- `test_all_documented_boolean_spellings_are_accepted()`: regression check that all documented boolean spellings are accepted.
- `test_empty_password_option_is_rejected()`: regression check that empty password option is rejected.
- `test_empty_required_value_is_rejected()`: regression check that empty required value is rejected.
- `test_syncoid_command_requires_both_placeholders()`: regression check that syncoid command requires both placeholders.
- `test_syncoid_command_rejects_duplicate_placeholder()`: regression check that syncoid command rejects duplicate placeholder.
- `test_syncoid_command_reports_shlex_error()`: regression check that syncoid command reports shlex error.
- `test_enabled_mqtt_requires_broker_address()`: regression check that enabled mqtt requires broker address.
- `test_enabled_mqtt_requires_valid_port_range()`: regression check that enabled mqtt requires valid port range.
- `test_enabled_legacy_mqtt_requires_topic()`: regression check that enabled legacy mqtt requires topic.
- `test_enabled_home_assistant_requires_availability_topic()`: regression check that enabled home assistant requires availability topic.
- `test_enabled_json_mqtt_requires_dedicated_topic()`: regression check that enabled json mqtt requires dedicated topic.
- `test_json_topic_conflict_with_legacy_topic_is_rejected()`: regression check that json topic conflict with legacy topic is rejected.

### `tests/test_datasets.py`

- `DatasetTests`: groups the tests and their shared setup for this module.
- `test_read_dataset_list_ignores_blank_and_comment_lines()`: regression check that read dataset list ignores blank and comment lines.
- `test_destination_extra_args_preserve_quoted_colon_space()`: regression check that destination extra args preserve quoted colon space.
- `test_destination_extra_args_report_unclosed_quote()`: regression check that destination extra args report unclosed quote.
- `test_empty_active_lists_are_rejected()`: regression check that empty active lists are rejected.
- `test_mismatched_lengths_are_rejected()`: regression check that mismatched lengths are rejected.
- `test_mismatched_leaf_names_are_rejected()`: regression check that mismatched leaf names are rejected.
- `test_trailing_slash_does_not_accidentally_match_empty_leaf()`: regression check that trailing slash does not accidentally match empty leaf.
- `test_matching_pairs_preserve_per_destination_arguments()`: regression check that matching pairs preserve per destination arguments.

### `tests/test_notifications.py`

- `NotificationTests`: groups the tests and their shared setup for this module.
- `test_run_summary_email_header_matches_terminal_layout()`: verifies email uses the shared heading/blank-line/title/blank-line/comment/blank-line/runtime layout for legacy/runtime-only calls.
- `test_run_summary_email_header_includes_transferred_size()`: verifies successful mail receives the same formatted transfer total followed by runtime as terminal/`.log`.
- `test_json_success_payload_includes_warning_and_skipped_pairs()`: regression check that json success payload includes warning and skipped pairs.
- `test_json_failure_payload_contains_error_and_stderr()`: regression check that json failure payload contains error and stderr.
- `test_error_mail_ignores_success_mail_switch()`: verifies a configured error email is still attempted when `SendMailOnSuccess` is false.
- `test_mqtt_failure_status_ignores_success_mqtt_switch()`: verifies configured JSON MQTT failure publishing still runs when `SendMQTTOnSuccess` is false.
- `test_mqtt_error_output_is_bounded_from_the_end()`: regression check that mqtt error output is bounded from the end.

### `tests/test_syncoid_runner.py`

- `SyncoidRunnerTests`: groups the tests and their shared setup for this module.
- `test_pv_amount_to_bytes_handles_binary_decimal_and_comma_decimal()`: verifies transfer progress parsing accepts binary/decimal unit spellings and both period/comma decimals.
- `test_transfer_counter_sums_maximum_progress_per_syncoid_stream()`: verifies repeated progress refreshes are not double-counted and multiple send streams are summed.
- `test_transfer_counter_marks_started_stream_without_pv_bytes_incomplete()`: verifies a started stream with no usable `pv` counter marks measurement incomplete.
- `test_build_command_preserves_dataset_spaces_and_extra_args()`: regression check that build command preserves dataset spaces and extra args.
- `test_build_command_rejects_missing_placeholders()`: regression check that build command rejects missing placeholders.
- `test_send_secret_refuses_when_expected_noecho_never_activates()`: regression check that send secret refuses when expected noecho never activates.
- `Child`: local fake Pexpect child used to verify secret/no-echo safety without starting a real SSH process.
- `__init__()`: initializes the small test helper object/handler.
- `waitnoecho()`: simulates whether a fake child disabled terminal echo.
- `sendline()`: records whether the secret helper attempted to send data.
- `test_extract_ssh_key_path_supports_both_forms_and_last_value()`: regression check that extract ssh key path supports both forms and last value.
- `test_private_agent_disabled_yields_none()`: regression check that private agent disabled yields none.
- `run_fake()`: runs a temporary fake Syncoid executable through the real Pexpect replication path.
- `test_openssh_permanently_added_known_host_warning_is_nonfatal()`: verifies the general ignore policy includes OpenSSH known-hosts warnings.
- `test_missing_dataset_exit_two_is_recorded_and_list_continues()`: verifies documented `dataset does not exist` output with Syncoid exit `2` records the failed pair and still executes the next configured pair.
- `test_missing_pool_exit_two_is_recorded()`: verifies `cannot open 'pool': no such pool` uses the same deferred failure path.
- `test_missing_pool_import_message_is_recorded()`: verifies OpenZFS's `cannot import 'pool': no such pool available` form is recognized by the same missing-pool path.
- `test_skipping_dataset_warnings_are_ignored()`: verifies a generic skip warning is ignored; only the exact disappeared-dataset report is deferred as missing data.
- `test_missing_dataset_text_does_not_mask_unrelated_exit_code()`: verifies a later unrelated Syncoid exit code remains immediately fatal instead of being converted to deferred code `8`.
- `test_missing_destroy_message_does_not_mask_unrelated_nonzero_exit()`: regression check that missing destroy message does not mask unrelated nonzero exit.
- `test_missing_destroy_message_is_nonfatal_when_syncoid_exits_zero()`: regression check that missing destroy message is nonfatal when syncoid exits zero.
- `test_generic_warnings_are_ignored()`: verifies supported warning labels, case, and indentation do not cause failure.
- `test_repeated_normal_sending_progress_is_not_mistaken_for_a_loop()`: regression check that repeated normal sending progress is not mistaken for a loop.
- `test_run_replications_collects_actual_pv_bytes_across_streams()`: verifies the run-level summary accumulates actual byte counters from multiple Syncoid streams.
- `test_exact_resume_unavailable_warning_remains_nonfatal()`: regression check that exact resume unavailable warning remains nonfatal.
- `test_benign_password_word_in_output_does_not_trigger_secret_prompt()`: regression check that benign password word in output does not trigger secret prompt.
- `test_benign_warnings_word_is_not_treated_as_warn_line()`: regression check that benign warnings word is not treated as warn line.
- `test_actual_passphrase_prompt_with_password_disabled_fails_code_5()`: regression check that actual passphrase prompt with password disabled fails code 5.
- `test_typical_openssh_password_prompt_with_password_disabled_fails_code_5()`: regression check that typical openssh password prompt with password disabled fails code 5.
- `test_password_prompt_with_password_disabled_fails_code_5()`: regression check that password prompt with password disabled fails code 5.
- `test_broken_pipe_disabled_preserves_real_nonzero_exit()`: regression check that broken pipe disabled preserves real nonzero exit.
- `test_broken_pipe_exhaustion_stops_list_after_configured_retries()`: verifies the configured retry count is honored and exhaustion raises code 2 before later pairs start.
- `test_repeated_host_key_prompt_fails_code_9()`: regression check that repeated host key prompt fails code 9.

- `test_main_missing_dataset_continues_list_then_reports_failure_code_8()`: end-to-end check that `main()` continues later pairs, skips the success stage, forwards the completed missing-data summary to MQTT/mail failure handling, and returns exit code `8`.
- `test_json_failure_payload_lists_missing_dataset_failures()`: verifies MQTT JSON failure status contains structured source/destination/reason entries for missing-data failures.
- `test_missing_dataset_failure_mail_lists_failed_pair_and_reason()`: verifies the dedicated missing-data failure email names the affected pair, includes the matched ZFS reason, and states exit code `8`.

### `tests/test_packaging.py`

- `PackagingTests`: groups static regression checks for the standalone build recipe.
- `test_spec_builds_onefile_syncerate_and_collects_runtime_packages()`: verifies the spec builds a one-file `Syncerate` executable and explicitly collects Pexpect plus dynamically imported Paho MQTT modules.
- `test_build_requirements_pin_packager_and_runtime_dependencies()`: verifies the documented build inputs stay pinned.
- `test_build_script_cleans_generated_output_and_verifies_executable()`: verifies the build wrapper keeps strict shell failure handling, cleans generated output, invokes the spec, and validates the frozen CLI/version.

### `tests/test_system_actions.py`

- `ListHandler`: groups the tests and their shared setup for this module.
- `__init__()`: initializes the small test helper object/handler.
- `emit()`: collects one logging record for assertions.
- `SystemActionTests`: groups the tests and their shared setup for this module.
- `setUp()`: creates isolated per-test logging state.
- `test_disabled_action_returns_without_running_shell()`: regression check that disabled action returns without running shell.
- `test_nonzero_action_is_logged_but_does_not_raise()`: regression check that nonzero action is logged but does not raise.
- `test_mail_enabled_preserves_two_minute_delay()`: regression check that mail enabled preserves two minute delay.



### Notification test helpers and delivery checks

- `NotificationTests.setUp()`: installs a temporary in-memory Paho module with a mocked `publish.multiple` and registers cleanup. This lets tests inspect the real publisher's payload, routing, and retain settings without network access or the optional MQTT dependency.
- `NotificationTests.mqtt_config(**overrides)`: builds valid broker/topic settings around the shared `make_config()` helper so tests exercise realistic routing without duplicating application configuration logic.
- `test_error_publish_routing_ignores_success_switch()`: checks both switch values across legacy-only, JSON-only, and combined MQTT. Confirms exactly one failure event, the expected topic, error details, QoS 0, and retain disabled.
- `test_success_switches_are_independent_for_success_and_warning()`: checks every mail/MQTT success-switch combination for ordinary success and an externally supplied compatibility Broken Pipe warning summary. Verifies existing retained success/HA payloads and non-retained JSON behavior.
- `test_default_success_switches_send_enabled_channels()`: confirms enabled mail/MQTT send success messages when switch fields retain their default true values.
- `test_disabled_channels_remain_silent_on_success_and_failure()`: confirms true success switches do not activate disabled master channels or error reporting.
- `test_mqtt_errors_and_unavailable_config_do_not_republish()`: verifies the existing no-config and MQTT-recursion guards.
- `test_main_failure_still_sends_mail_when_error_mqtt_fails()`: runs the application error boundary with mocked replication and broker failures. Confirms one attempted MQTT error report, subsequent error email despite both success switches being false, and preservation of the original replication exit code.

The `tests/test_config.py` Boolean checks exercise both success switches with true/false, yes/no, on/off, numeric, and mixed-case spellings; invalid values for either switch must fail startup validation.


### Warning/resume regression checks

- `test_continue_without_resume_defaults_true_and_validates_booleans()`: verifies default continuation, each supported Boolean spelling, and rejection of invalid configuration values before runtime.
- `test_resume_unavailable_can_stop_or_continue()`: checks source, target, and combined-machine warnings with both policies; verifies the warning is registered and the stop policy raises code 4.
- `test_continue_without_resume_preserves_real_nonzero_exit()`: proves allowing missing resume support does not hide a later non-zero Syncoid exit.
- `test_warning_error_words_do_not_trigger_error_or_prompt_handlers()`: verifies warning bodies cannot trigger credential input, host-key answers, connection failures, missing-data recording, or Broken Pipe retries; ordinary warnings also produce no separate application warning logs.
- `test_warning_chunks_and_unterminated_warning_are_consumed()`: verifies a warning arriving in several writes remains ignored through EOF without a newline.
- `test_ignored_warnings_remain_in_raw_log_without_affecting_transfer_count()`: verifies raw `.out` retains warnings while a transfer-like warning does not create a false transfer or incomplete measurement.
- `test_resume_warning_chunks_are_checked_at_eof()`: verifies unavailable resume support is still detected when its warning arrives in chunks and ends at EOF.
- `test_nonwarning_errors_after_warning_still_fail()`: checks authentication and connection error codes after an ignored warning line.
- `test_ignored_warning_preserves_exit_and_signal_failures()`: verifies actual non-zero and signal-derived exit codes remain failures after a warning.
- `test_runtime_missing_dataset_warning_records_failure_on_zero_or_two()`: verifies the exact runtime disappeared-dataset warning creates a deferred failure even when Syncoid exits zero.
- `test_nonwarning_missing_dataset_after_warning_is_still_recorded()`: verifies a separate missing-data error retains deferred failure handling after a warning.
- `test_reset_warning_preserves_nonwarning_broken_pipe_recovery()`: verifies silent reset bookkeeping protects Syncoid's recovery-related Broken Pipe from ordinary retry handling.
- `test_fresh_send_restores_nonwarning_broken_pipe_retry_handling()`: verifies a fresh send clears recovery state so a later Broken Pipe follows retry/fatal-exhaustion handling.

`SyncoidRunnerTests.run_fake()` accepts an optional logger so log-capture assertions retain their handlers while fake processes exercise the real Pexpect monitor.

- `test_resume_required_stops_list_and_uses_error_notifications()`: runs a fake two-pair job through `main()` with continuation disabled. Verifies code 4, termination before the child/later pair writes its marker, no successful-run actions, and dispatch through both error-notification handlers despite disabled success switches.


### Runtime missing-data classification and source evidence

- `_SYNCOID_MISSING_DATASET_EXIT_CODES`: permits deferred handling for exits 0, 1, and 2 only when the attempt also contains recognized missing-data evidence. Syncoid's recursive disappeared-source path can leave exit zero; initial/property-query and transfer paths use 1 or 2. Every other exit and terminating signal remains fatal.
- `_ZFS_NAME`: matches a quoted dataset/pool name, excluding `@` and `#` so missing snapshots/bookmarks cannot activate the dataset/pool exception.
- `_ZFS_MISSING_DATASET_OR_POOL_TEXT`: defines bounded complete English diagnostic shapes, including optional Syncoid critical/property-query wrappers. It recognizes missing datasets/pools on open/import, missing parents/pools on create, and explicit missing receive destinations. It intentionally excludes generic “no datasets found”, debug output, and arbitrary missing-text fragments.
- `_ZFS_MISSING_DATASET_OR_POOL_RE`: applies the same expression to complete lines remaining at EOF; the live Pexpect matcher requires a physical line ending to avoid accepting an unfinished prefix of a different message.
- `_SYNCOID_MISSING_DATASET_WARNING_RE`: full-matches the exact disappeared-dataset skip report, accepting current `WARNING` and compatible `WARN` labels. It is the narrowly scoped missing-data exception to ignoring ordinary warnings.

Verified against [Syncoid revision d39b51a](https://github.com/jimsalterjrs/sanoid/blob/d39b51a013081e86bb26a6859866c34d98c39ea3/syncoid) (`syncdataset`, `getzfsvalue`, `writelog`, and transfer result handling), plus [OpenZFS dataset operations](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_dataset.c), [pool operations](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_pool.c), [error descriptions](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_util.c), and [receive operations](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_sendrecv.c). Source matching is based on English diagnostics; unrecognized/localized output falls back to normal process-exit handling.

### Preflight/runtime boundary regression checks

- `test_preflight_mismatch_stops_before_any_replication()`: checks mismatching final names after an initially valid pair, unequal list lengths, and trailing slashes. Confirms code 1 before credential resolution or replication and dispatch to the error-notification boundary.
- `test_upstream_missing_data_messages_continue_to_next_pair()`: exercises source/pool, property wrapper, destination parent, incremental/new-filesystem receive, and disappeared-child reports using local fake processes. Verifies the next pair actually executes and the complete reason is recorded.
- `test_only_specific_missing_data_messages_allow_continuation()`: rejects generic skips/no-datasets reports, snapshot/bookmark names, unrelated receive failures, debug echoes, arbitrary warning bodies, and extended text that only begins like a matching diagnostic.
- `test_missing_data_message_is_complete_across_chunks_and_eof()`: verifies complete capture and classification of a split, unterminated error line.
- `test_missing_data_does_not_hide_authentication_or_unrelated_exit()`: verifies authentication failures and exit 42 remain fatal after a missing-data report.
- `test_missing_data_precedes_secondary_broken_pipe()`: verifies a Broken Pipe after confirmed missing-data evidence waits for final status instead of activating retries.
- `test_completed_missing_data_run_sends_actual_error_mail_and_mqtt()`: executes three fake pairs through the real app/runner, including two missing-data failures and a later success. Captures actual generated email and MQTT JSON, verifying exit 8, both failed pairs, error delivery with success switches false, and no system action.
