# Syncerate commented code map

This document maps the modular Syncerate implementation in version `0.4.13`. It explains what every module, class, function, command stage, and safety branch does and why it exists.

## Application layout

```text
Syncerate.py
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
VERSION = "0.4.13"
__version__ = VERSION
```

This is the single authoritative application version. `cli.py` uses it for `--version`, and `Syncerate.py` re-exports it for compatibility.

## `syncerate/errors.py`

This module contains shared exit codes and the application exception. Keeping these values in a dependency-light module lets every other module use the same codes without circular imports.

### Exit-code constants

- `EXIT_OK = 0`: successful run.
- `EXIT_LIST_ERROR = 1`: source/destination parsing or validation failed.
- `EXIT_SCRIPT_ERROR = 2`: unexpected application/Python failure.
- `EXIT_WARNING = 4`: a Syncoid warning remains fatal.
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

It replaces internal `sys.exit()` calls. `app.main()` catches it, logs the correct diagnostics, optionally sends error mail, and returns its exit code.

## `syncerate/models.py`

This module contains data only. It does not start work or import higher-level modules.

### `AppConfig`

Immutable configuration state loaded from one INI file. It replaces former runtime globals such as:

- `config`;
- `MailOption`;
- `SystemOption`;
- `Use_MQTT`;
- `DateTime`;
- `LogDestination`;
- `BackupTitle`;
- `BackupComment`;
- `PassWordOption`;
- `SyncoidCommand`;
- `RetryBrokenPipe`;
- `BrokenPipeRetryCount`;
- `BrokenPipeRetryWaitSeconds`.

Fields:

- `config_path`: selected configuration path for logs;
- `raw_config`: retained `RawConfigParser` for lazy MQTT/HA option reads;
- `mail_option`: recipient or `No`;
- `system_option`: successful-run command or `No`;
- `use_mqtt`: normalized Boolean;
- `datetime_format`: filename timestamp format;
- `log_destination`: normalized directory or `None`;
- `backup_title` / `backup_comment`: optional descriptive text;
- `source_list_path` / `destination_list_path`: dataset-list files;
- `password_option`: `No`, `Ask`, or a literal credential;
- `syncoid_command`: command template;
- `retry_broken_pipe`: normalized Boolean controlling optional per-dataset retries;
- `broken_pipe_retry_count`: validated retries available to each individual dataset, defaulting to `1`;
- `broken_pipe_retry_wait_seconds`: validated whole seconds to wait before each retry, defaulting to `10`.

Properties:

- `mail_enabled`: mail is enabled unless the value is `No`;
- `system_action_enabled`: system action is enabled unless the value is `No`;
- `logging_enabled`: file logging is enabled when a log directory exists.

The raw parser remains available so optional MQTT and Home Assistant settings are not accessed until MQTT publishing actually runs.

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

### `ReplicationSummary`

Carries nonfatal conditions that apply to the completed dataset list. Its `broken_pipe_failed_datasets` list contains every `DatasetPair` skipped after exhausting its independently configured Broken Pipe retries. `has_broken_pipe_warning` provides the final notification stage with a simple Boolean check.

### `SyncoidAttemptResult`

Returned by one monitored Syncoid attempt. It contains:

- the `pexpect` child;
- original or modified command;
- repeated-pattern status;
- whether one retry with `--no-resume` is requested;
- whether the known missing-destroy-snapshot condition was observed;
- whether this attempt stopped after detecting Broken Pipe.

It replaces former mutable control globals.

## `syncerate/cli.py`

### `parse_arguments(argv=None)`

Creates the `argparse` parser only when called.

Supported commands:

```bash
./Syncerate.py --conf /path/to/config
./Syncerate.py -c /path/to/config
./Syncerate.py --help
./Syncerate.py --version
```

The optional `argv` parameter lets tests pass an explicit argument list without modifying process arguments.

## `syncerate/config.py`

### `CONFIG_SECTION`

```python
CONFIG_SECTION = "Syncerate Config"
```

Keeps the INI section name consistent between normal configuration loading and lazy notification settings.

### `option_is_enabled(value)`

Returns true for:

```text
YES, TRUE, 1, ON
```

Everything else is disabled. This allows `No`, `False`, `0`, and `Off` to safely disable MQTT, Home Assistant, or Broken Pipe retry handling.

### `load_app_config(config_path)`

Reads and validates the selected INI file, then returns `AppConfig`.

It:

- verifies the file can be read;
- verifies `[Syncerate Config]` exists;
- reads startup settings;
- applies fallbacks to optional metadata, `Use_MQTT`, `RetryBrokenPipe`, `BrokenPipeRetryCount`, and `BrokenPipeRetryWaitSeconds`;
- converts `LogDestination = No` into `None`;
- normalizes an enabled log directory to end with `/`;
- parses `BrokenPipeRetryCount` and `BrokenPipeRetryWaitSeconds` as integers and rejects negative values;
- deliberately leaves broker, MQTT credentials, MQTT payload, and HA topic inside `raw_config` for lazy reading.

It does not create logs, read datasets, resolve credentials, or load `paho-mqtt`.

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

### `log_startup_configuration(app_config, run_context, logger)`

Logs startup details while hiding secrets.

It omits:

- `PassWord`;
- MQTT username and password;
- Home Assistant settings from general startup logging;
- broker/topic options when MQTT is disabled.

This preserves useful diagnostics without exposing credentials or touching optional settings unnecessarily.

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

Splits optional destination-specific arguments from the final `: ` separator.

Example:

```text
backup@host:Pool/Data: --recvoptions="o compression=zstd"
```

becomes:

- destination: `backup@host:Pool/Data`;
- extra argv: `--recvoptions=o compression=zstd`.

Using the final colon-space sequence avoids confusing the SSH `host:dataset` separator with the extra-argument separator. `shlex.split()` preserves quoted argument grouping.

### `parse_destination_list(destination_lines)`

Runs `parse_destination_line()` for every destination and returns matching dataset and argument lists. It is retained as a separately testable parser helper.

### `load_dataset_pairs(app_config, logger)`

Loads, logs, validates, and combines both files.

It verifies:

1. source and destination counts match;
2. the final dataset component in each positional pair matches.

It then returns `list[DatasetPair]`, keeping each pair and its extra arguments together.

## `syncerate/notifications.py`

This module contains all optional email, MQTT, and Home Assistant behavior.

### `BROKEN_PIPE_SUCCESS_SUBJECT`

Stores the exact requested warning-success email subject: `Syncerate Succsful - WARNING BROKEN PIPE`. Keeping it in one constant prevents the logged/body wording and mail subject from drifting apart.

### `backup_header_text(app_config)`

Builds the optional backup-title/comment prefix reused by all email variants.

### `send_mail(subject, body, recipient, attachment_files=None)`

Runs the local command:

```bash
mail -s <subject> <recipient> --attach <file> ...
```

The email body is passed on standard input. The function returns the command exit code and stderr instead of terminating the application.

### `WasMailSent(mail_exit_code, popen_stderr, logger)`

Logs whether the local mail program accepted the message. It keeps the existing public function name for compatibility.

### `MailTo(app_config, run_context, logger, ...)`

Builds the current success and failure message variants:

- successful run;
- successful run with skipped datasets after exhausting their Broken Pipe retry allowance;
- script error;
- Syncoid error;
- MQTT error.

When a completed run carries a Broken Pipe warning, the subject is exactly `Syncerate Succsful - WARNING BROKEN PIPE`. The body reports the configured per-dataset retry count and wait time, then lists each skipped dataset pair. When logging is enabled it attaches available `.log`, `.err`, and `.out` files. When logging is disabled it sends a text-only message. It does not call `sys.exit()`.

### `send_mqtt_messages(app_config, logger)`

Handles both normal MQTT and optional Home Assistant availability messages.

Important lazy behavior:

1. The function is called only when `Use_MQTT` is enabled.
2. `paho.mqtt.publish` is imported inside this function.
3. Broker and MQTT settings are read only after MQTT is reached.
4. `Use_HomeAssistant` is read only inside this function.
5. `HomeAssistant_Available` is read only when HA is enabled.

If `paho-mqtt` is missing or publishing fails, it raises `SyncerateError` with exit code `10`.

MQTT messages are passed to `publish.multiple()` as a list. The HA availability message, when enabled, is sent before the normal Syncerate message.

### `send_error_mail(error, app_config, run_context, logger)`

Chooses the correct `MailTo()` variant from the error kind. Notification failure is caught and logged so it cannot replace the original application exit code.

## `syncerate/system_actions.py`

### `SystemAction(app_config, logger)`

Runs the configured successful-run shell command.

When mail is also enabled, the existing two-minute delay is preserved to allow the mail command time before a shutdown or similar action. Without mail, the command runs immediately.

It uses:

```python
subprocess.run(command, shell=True, check=False)
```

Current behavior logs execution exceptions instead of raising the reserved exit code `11`.

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

### `ssh_command(syncoid_command, password, run_context, logger, retry_broken_pipe=False)`

Starts one process with:

```python
pexpect.spawn(command[0], command[1:], timeout=None, encoding="utf-8")
```

Using an argv list avoids shell re-parsing.

It monitors these conditions:

1. **SSH host-key confirmation** — answers `yes`.
2. **Missing destroy snapshot** — records the known nonfatal shared-dataset condition.
3. **Permission denied** — exits through code `5`.
4. **Connection timeout** — code `6`.
5. **Connection refused** — code `7`.
6. **Passphrase prompt** — temporarily disables logfile echo, sends the configured credential, then restores logging.
7. **EOF** — returns the real child and current result flags.
8. **Skipped dataset warning** — code `8`.
9. **Stale resume state** — returns a request for one retry with `--no-resume`.
10. **Resume feature unavailable** — logs the exact nonfatal message and waits for Syncoid's real exit status.
11. **Broken Pipe** — when `RetryBrokenPipe` is enabled, terminates the current attempt and returns `broken_pipe_detected=True`; when disabled, logs the detection and waits for the real child exit status.
12. **Generic warning** — remains fatal with code `4`, except the separately recognized destroy warning.
13. **Password prompt** — handled like passphrase.

Each pattern is limited to five matches. Exceeding the limit sets `repeated_pattern` so the caller can fail safely with code `9`.

The exact unavailable-resume regular expression accepts source, target, or both machines while requiring Syncoid's explicit “will continue without resume support” wording.

### `run_replications(app_config, run_context, dataset_pairs, password, logger)`

Runs all validated pairs sequentially.

For each pair it:

1. builds the command;
2. logs extra arguments and argv details;
3. starts `ssh_command()`;
4. performs at most one stale-resume retry;
5. when enabled, gives each dataset its own `app_config.broken_pipe_retry_count` allowance and waits `app_config.broken_pipe_retry_wait_seconds` before every retry;
6. records and skips only that pair after its configured Broken Pipe retry allowance is exhausted;
7. closes the child;
8. converts signal termination to `128 + signal`;
9. preserves the real Syncoid exit code for other failures;
10. ignores a nonzero code only when the specific missing-destroy-snapshot condition was recognized.

The function returns `ReplicationSummary`. `broken_pipe_retries_used` is initialized inside the dataset loop, so every dataset pair receives the full configured retry count independently. No transfer is started in parallel, preserving sequential behavior.

## `syncerate/app.py`

### `log_syncerate_error(error, logger)`

Writes the appropriate final diagnostics for:

- known matched child errors;
- unknown Syncoid nonzero exits;
- MQTT failures;
- general script failures.

List validation already writes its detailed message in `datasets.py`, so it is not duplicated here.

### `successfull_run(app_config, run_context, logger, replication_summary=None)`

Runs the post-transfer order and uses `ReplicationSummary` to select normal success or warning-success logging and email:

1. append successful-run text to `.out` when enabled;
2. MQTT and optional HA notification;
3. success email;
4. system action.

This ordering is preserved so a notification error can still stop processing with its defined code before a later system action.

### `main(argv=None)`

Owns all startup and the final exception boundary.

Execution order:

1. parse arguments;
2. load `AppConfig`;
3. create `RunContext`;
4. configure logger;
5. log safe startup settings;
6. load and validate `DatasetPair` objects;
7. resolve the optional password/passphrase;
8. run all replications and collect `ReplicationSummary`;
9. run successful completion actions with the summary;
10. return `0`.

Known `SyncerateError` exceptions are logged, optionally mailed, and returned with their original code. Unexpected exceptions are logged with a traceback, optionally mailed as script errors, and return code `2`.

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

AppConfig + RunContext + DatasetPair + password
    -> syncoid_runner.run_replications()
    -> SyncoidAttemptResult per attempt
    -> ReplicationSummary for the full list

Successful completion
    -> notifications
    -> system_actions
```

This explicit flow is why modules do not need shared mutable runtime globals.
