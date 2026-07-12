# Syncerate commented code map

This document maps the current `Syncerate.py` implementation in version `0.4.6`. It explains what each class, function, command stage, and safety branch does and why it exists.

## Overall design

Version `0.4.6` remains a single Python file, but runtime state is no longer stored in module globals.

Importing `Syncerate.py` now only:

- imports required Python modules;
- defines constants;
- defines dataclasses and the application exception;
- defines functions.

Importing the file does **not**:

- parse command-line arguments;
- require `--conf`;
- read a configuration file;
- create log files;
- read dataset lists;
- ask for a password;
- import `paho-mqtt`;
- start Syncoid.

All runtime work begins inside `main()`.

## Program-level constants

### Exit codes

- `EXIT_OK = 0`: successful run.
- `EXIT_LIST_ERROR = 1`: source/destination list parsing or validation failed.
- `EXIT_SCRIPT_ERROR = 2`: unexpected Python or application error.
- `EXIT_WARNING = 4`: Syncoid produced a warning that remains fatal.
- `EXIT_PASSWORD_DENIED = 5`: SSH authentication, ZFS permission, password, or passphrase failure.
- `EXIT_CONNECTION_TIMEOUT = 6`: remote connection timed out.
- `EXIT_CONNECTION_REFUSED = 7`: remote connection was refused.
- `EXIT_DATASET_MISSING = 8`: Syncoid skipped a dataset.
- `EXIT_REPEATED_PATTERN = 9`: one `pexpect` pattern repeated too many times.
- `EXIT_MQTT_ERROR = 10`: optional MQTT dependency or publishing failure.
- `EXIT_SYSTEM_ACTION_ERROR = 11`: reserved for system-action failures; the current system-action behavior remains unchanged and logs exceptions without converting them to this code.

### `VERSION`

```python
VERSION = "0.4.6"
```

Provides the value returned by `--version` and the release version recorded in project documentation.

### `CONFIG_SECTION`

```python
CONFIG_SECTION = "Syncerate Config"
```

Keeps the INI section name in one place so configuration functions and optional MQTT handling use the same exact section.

## Runtime state classes

### `AppConfig`

`AppConfig` is an immutable dataclass containing settings read from the selected configuration file.

It replaces runtime globals such as:

- `config`;
- `MailOption`;
- `SystemOption`;
- `Use_MQTT`;
- `DateTime`;
- `LogDestination`;
- `BackupTitle`;
- `BackupComment`;
- `PassWordOption`;
- `SyncoidCommand`.

Important fields:

- `config_path`: selected config filename, used in startup logs;
- `raw_config`: the `RawConfigParser` object retained for lazy MQTT/HA reads;
- `mail_option`: recipient address or `No`;
- `system_option`: successful-run shell command or `No`;
- `use_mqtt`: normalized Boolean for the optional MQTT path;
- `datetime_format`: `strftime` format for run filenames;
- `log_destination`: normalized directory ending in `/`, or `None` when disabled;
- `backup_title` / `backup_comment`: optional descriptive metadata;
- `source_list_path` / `destination_list_path`: dataset-list paths;
- `password_option`: `No`, `Ask`, or a literal secret;
- `syncoid_command`: command template containing `SourceDataSet` and `DestDataSet`.

Properties:

- `mail_enabled`: true unless `Mail` is exactly `No`, ignoring case and surrounding whitespace;
- `system_action_enabled`: true unless `SystemAction` is `No`;
- `logging_enabled`: true when a log directory is configured.

The raw parser remains inside `AppConfig` so optional broker and Home Assistant options can stay unread until MQTT publishing is actually reached.

### `RunContext`

`RunContext` is an immutable dataclass containing values created for one invocation:

- `timestamp`;
- `log_destination`;
- `.log` path;
- `.err` path;
- `.out` path.

It replaces runtime globals such as `time_now` and derived log filenames. When logging is disabled, all paths are `None` and terminal logging remains active.

### `DatasetPair`

`DatasetPair` is an immutable dataclass containing:

- one source dataset;
- its matching destination dataset;
- that destination's optional Syncoid arguments.

It replaces three parallel runtime lists (`SourceLines`, `DestLines`, and `DestExtraArgs`). Keeping related values in one object prevents an argument list from becoming associated with the wrong destination.

### `SyncoidAttemptResult`

`SyncoidAttemptResult` is returned by `ssh_command()` after one monitored Syncoid attempt. It contains:

- `child`: the `pexpect` child process;
- `command`: the original or modified command used by the caller;
- `repeated_pattern`: whether the same output pattern exceeded its safety limit;
- `retry_without_resume`: whether one retry with `--no-resume` is requested;
- `ignored_missing_destroy_snapshot`: whether the known missing Syncoid-created snapshot condition was observed.

It replaces the former mutable globals:

- `ISREPEATED`;
- `CONTINUENORESUME`;
- `CONTINUENODESTROYSNAP`.

### `SyncerateError`

`SyncerateError` is the known application exception used instead of internal `sys.exit()` calls.

It carries:

- the human-readable message;
- the intended exit code;
- an error category (`list`, `known_child`, `syncoid`, `mqtt`, or `script`);
- captured Syncoid output when relevant.

Only the final executable boundary calls:

```python
sys.exit(main())
```

This allows lower-level functions to return results or raise an application error while `main()` remains responsible for logging, error mail, and the final process status.

## Functions

### `option_is_enabled(value)`

Normalizes optional Boolean-style configuration values. It returns true for:

```text
YES, TRUE, 1, ON
```

All other values are disabled. It is used for MQTT and Home Assistant options.

### `parse_arguments(argv=None)`

Builds the `argparse` parser and supports:

```bash
./Syncerate.py --conf /path/to/Syncerate.cfg
./Syncerate.py -c /path/to/Syncerate.cfg
./Syncerate.py --help
./Syncerate.py --version
```

The optional `argv` parameter lets tests supply an argument list directly. In normal execution, `None` makes `argparse` read the real command line.

The parser is created only when this function is called from `main()`, so importing the file never requires `--conf`.

### `load_app_config(config_path)`

Reads the selected INI file and returns `AppConfig`.

It:

- verifies that the file was readable;
- verifies the `[Syncerate Config]` section exists;
- loads required startup settings;
- applies safe fallbacks for optional backup metadata and `Use_MQTT`;
- converts `LogDestination = No` to `None`;
- appends `/` to an enabled log directory when needed;
- keeps broker and Home Assistant details lazy inside `raw_config`.

It does not create logs, read dataset files, or request a password.

### `create_run_context(app_config)`

Creates the timestamp using the configured `DateTime` format and derives the optional paths:

```text
Syncerate-<timestamp>.log
Syncerate-<timestamp>.err
Syncerate-<timestamp>.out
```

When logging is disabled, it returns a context with no file paths.

### `get_logger(run_context)`

Configures the named `syncerate` logger.

Always creates:

- one INFO-level terminal handler writing to standard output.

When file logging is enabled, it also creates:

- an INFO-level `.log` file containing normal and error messages;
- an ERROR-level `.err` file containing errors only.

It receives `RunContext` explicitly instead of reading global path variables.

### `get_console_logger()`

Creates a terminal-only logger for failures that occur before configuration and `RunContext` creation complete, such as an unreadable config file.

### `log_startup_configuration(app_config, run_context, logger)`

Writes startup information to the configured logger.

It logs:

- whether file logging is disabled;
- selected config path;
- optional backup title/comment;
- generated timestamp;
- non-secret configuration options;
- whether the command template begins with `syncoid`.

It deliberately omits:

- `PassWord`;
- MQTT username/password;
- Home Assistant options from general startup logging;
- broker/topic settings when MQTT is disabled.

### `backup_header_text(app_config)`

Builds the optional backup-title and backup-comment prefix used in mail bodies. Returning one reusable string keeps successful, Syncoid-error, script-error, and MQTT-error mail consistent.

### `send_mail(subject, body, recipient, attachment_files=None)`

Runs the local mail command:

```bash
mail -s <subject> <recipient> [--attach <file> ...]
```

The message body is sent through standard input. The function returns:

- the mail process exit code;
- decoded stderr text.

It does not exit the application.

### `WasMailSent(mail_exit_code, popen_stderr, logger)`

Logs whether the local mail process succeeded. It preserves the existing mail-result messages and does not change the main Syncerate exit code.

### `MailTo(app_config, run_context, logger, Exit_Code=None, SynCoidFail=None, MQTT_Fail=None)`

Builds and sends the existing mail variants:

- successful run;
- unknown Syncoid failure;
- general/script failure;
- MQTT failure.

When logs are enabled, it attaches the available `.log`, `.err`, and `.out` files and includes relevant contents in the body.

In version `0.4.6`, `MailTo()` no longer calls `sys.exit()`. It sends the notification and returns; `main()` owns the final exit code.

### `send_mqtt_messages(app_config, logger)`

Handles optional MQTT and Home Assistant publication.

Important lazy behavior:

1. The function is called only after all replications succeed and `Use_MQTT` is enabled.
2. `paho.mqtt.publish` is imported inside this function.
3. Broker settings are read only after the function is reached.
4. `Use_HomeAssistant` is read only inside this MQTT path.
5. `HomeAssistant_Available` is read only when HA integration is enabled.

Messages:

- optional HA availability message with payload `online`;
- configured normal Syncerate MQTT topic/message.

A missing `paho-mqtt` package or publish failure raises `SyncerateError` with exit code `10`; error mail is handled later by `main()`.

### `SystemAction(app_config, logger)`

Runs the optional successful-run shell command with:

```python
subprocess.run(command, shell=True, check=False)
```

If mail is enabled, it preserves the existing two-minute delay before running the action. If mail is disabled, it runs the action immediately. Exceptions are logged without changing the existing system-action exit behavior.

### `successfull_run(app_config, run_context, logger)`

Runs the post-replication success stage in the existing order:

1. writes the completion section to `.out` when enabled;
2. publishes MQTT/HA messages when enabled;
3. sends success mail when enabled;
4. runs the system action when enabled.

Because MQTT occurs first, an MQTT failure still prevents a success mail/system action and is converted to exit code `10`, matching the prior ordering.

### `missmatchinglists(Lenght, Names, logger)`

Logs either:

- unequal source/destination item counts; or
- mismatching final dataset names.

It raises `SyncerateError` with exit code `1` rather than sending mail and terminating internally. `main()` sends the matching general error mail and returns the exit code.

The historical parameter spellings are retained in this first refactor to avoid mixing naming cleanup with state-management changes.

### `read_dataset_list(path)`

Reads a list file as UTF-8 and returns active lines only.

It ignores:

- blank lines;
- lines whose trimmed form begins with `#`.

Each retained line is stripped of surrounding whitespace.

### `parse_destination_line(line)`

Parses one destination-list entry.

Supported forms:

```text
Pool/Dataset
Pool/Dataset: --recvoptions="o compression=zstd"
user@host:Pool/Dataset
user@host:Pool/Dataset: --recvoptions="o compression=zstd"
```

It uses `rsplit(": ", 1)` so the colon in `user@host:Pool/Dataset` is not mistaken for the optional-arguments separator. `shlex.split()` preserves quoted multi-word option values as single arguments.

### `parse_destination_list(destination_lines)`

Parses all destination lines and returns two matching lists:

- destination dataset strings;
- extra argument lists.

`load_dataset_pairs()` immediately combines those values with source entries into `DatasetPair` objects.

### `load_dataset_pairs(app_config, logger)`

Performs all source/destination loading and validation.

It:

1. reads both list files;
2. parses optional destination arguments;
3. logs raw and parsed values;
4. verifies equal item counts;
5. verifies each source/destination pair has the same final dataset component;
6. returns one `DatasetPair` per valid replication.

Example accepted pair:

```text
source:      user@host:Pool/Media
 destination: Backup/Media
```

The final component `Media` matches even though the parent paths and remote/local forms differ.

### `resolve_password(app_config, logger)`

Converts the configured password mode into a runtime value:

- `No`: returns `None`;
- `Ask`: calls `getpass()` and returns the hidden user input;
- any other text: returns that literal value.

The resolved secret is a local variable passed only to Syncoid monitoring. It is never stored as a module global or written to logs.

### `safe_text(value)`

Safely converts optional `pexpect` values (`before`, `after`, or `buffer`) to text. `None` becomes an empty string so error logging cannot fail while handling another failure.

### `close_child_logfile(child, logger=None)`

Flushes and closes the `.out` handle attached to `child.logfile`, then clears the reference. This ensures Syncoid output is available to mail and log readers before the process result is handled.

### `die(...)`

Retains the historical helper name but changes its behavior.

It now:

- determines the intended exit code;
- captures relevant child output;
- terminates a known failing child when necessary;
- closes the child logfile;
- raises `SyncerateError`.

It does **not**:

- send mail;
- call `sys.exit()`;
- modify runtime globals.

This keeps existing call sites readable while moving final error policy to `main()`.

### `log_syncerate_error(error, logger)`

Writes the detailed diagnostics formerly written directly by `die()`.

It distinguishes:

- known matched child errors;
- unknown nonzero Syncoid exits;
- MQTT failures;
- general script failures.

List-validation functions already write their specific messages, so `kind="list"` does not add duplicate generic diagnostics.

### `log_command_debug(command_list, logger)`

Logs the generated command in three forms:

1. shell-style rendering using `shlex.join()`;
2. raw Python argv list;
3. one indexed line per argument.

This is important for diagnosing quoting, remote endpoints, paths, and destination-specific arguments without executing through a shell.

### `build_syncoid_command(command_template, source_dataset, destination_dataset, extra_args=None)`

Builds the argv list passed to `pexpect.spawn()`.

Order is important:

1. `shlex.split()` separates the command template;
2. `SourceDataSet` and `DestDataSet` are replaced inside existing argv elements;
3. destination-specific arguments are appended.

Replacing after splitting keeps a dataset containing spaces as one argv element.

No shell is used for Syncoid execution.

### `effective_user_name()`

Resolves `os.geteuid()` through the local password database.

This documents the real local execution identity:

- local Syncoid/ZFS work runs as the effective user that started Syncerate;
- when started through `sudo`, this is normally `root`;
- remote work uses the SSH user embedded in the remote endpoint.

### `ssh_command(syncoid_command, password, run_context, logger)`

Starts one Syncoid process with:

```python
pexpect.spawn(
    syncoid_command[0],
    syncoid_command[1:],
    timeout=None,
    encoding="utf-8",
)
```

It receives all runtime dependencies explicitly and returns `SyncoidAttemptResult`.

#### Output patterns

The pattern order is intentional because specific safe/known messages must be matched before the generic warning expression.

1. `Are you sure you want to continue connecting`
   - sends `yes` for a first SSH host-key prompt.

2. `could not find any snapshots to destroy; check snapshot names.`
   - marks the known missing Syncoid-created snapshot condition;
   - allows monitoring to continue so the following destroy warning and final status can be interpreted together.

3. `Permission denied`
   - raises exit code `5`.

4. `Connection timed out`
   - raises exit code `6`.

5. `Connection refused`
   - raises exit code `7`.

6. `passphrase`
   - temporarily detaches `.out` logging so the secret is not recorded;
   - sends the resolved password/passphrase;
   - raises exit code `5` when `PassWord = No`.

7. `pexpect.EOF`
   - closes the output logfile and returns the attempt result for final exit-status handling.

8. `WARN Skipping dataset`
   - raises exit code `8` because a requested dataset was not replicated.

9. `used in the initial send no longer exists`
   - requests one retry with `--no-resume`;
   - returns a modified command instead of using a global retry flag.

10. Exact resume-capability warning:

```text
WARN: ZFS resume feature not available on ... - sync will continue without resume support.
```

   - logs a warning;
   - continues monitoring;
   - waits for Syncoid's real exit status;
   - does not add `--no-resume` because Syncoid explicitly says it is continuing.

11. Generic `WARN|WARNING`
   - remains fatal with exit code `4`;
   - exception: the known `zfs destroy ... failed: 256` continuation is allowed only after the matching missing-snapshot message was already seen.

12. `password`
   - handles a normal SSH password prompt using the same secret-protection behavior as `passphrase`.

#### Repetition limit

Each pattern may be handled at most five times. A sixth occurrence sets `repeated_pattern=True`, returns the result, and lets `run_replications()` raise exit code `9`. This prevents a prompt/output loop from running forever.

### `run_replications(app_config, run_context, dataset_pairs, password, logger)`

Runs each validated `DatasetPair` sequentially.

For every pair it:

1. builds the safe argv command;
2. logs extra destination arguments;
3. logs detailed command diagnostics;
4. runs `ssh_command()`;
5. performs one retry when `retry_without_resume` is true;
6. closes the child to obtain `exitstatus`/`signalstatus`;
7. handles repeated-pattern failure;
8. converts signal termination to `128 + signal number`;
9. preserves the known missing-destroy-snapshot nonfatal behavior;
10. raises an unknown Syncoid failure with the actual nonzero exit code otherwise.

The local process user is never replaced. Remote behavior remains determined by remote dataset endpoints in the command.

### `send_error_mail(error, app_config, run_context, logger)`

Maps a `SyncerateError` category to the existing mail type:

- MQTT error -> `MQTT_Fail` mail;
- unknown Syncoid exit -> `SynCoidFail` mail;
- all other known errors -> general `Exit_Code` mail.

Mail failure is caught and logged so it cannot replace the original application exit code.

### `main(argv=None)`

Owns the complete runtime sequence:

1. parse CLI arguments;
2. load `AppConfig`;
3. create `RunContext`;
4. configure logging;
5. log startup configuration;
6. load and validate `DatasetPair` entries;
7. resolve the optional password/passphrase;
8. run all replications;
9. run the success notification/action stage;
10. return exit code `0`.

Known `SyncerateError` exceptions are logged, optionally mailed, and returned using their specific exit code.

Unexpected exceptions are logged with a traceback, optionally mailed as a script error, and return exit code `2`.

### Executable boundary

```python
if __name__ == "__main__":
    sys.exit(main())
```

This is the only explicit `sys.exit()` call in the application. It converts the integer returned by `main()` into the shell-visible exit status while keeping all internal functions importable and testable.

## Command flow

For one dataset pair, the effective flow is:

```text
main
  -> load_dataset_pairs
  -> resolve_password
  -> run_replications
       -> build_syncoid_command
       -> log_command_debug
       -> ssh_command
            -> pexpect.spawn
            -> pattern handling
            -> SyncoidAttemptResult
       -> optional one-time --no-resume retry
       -> final Syncoid status evaluation
  -> successfull_run
       -> optional MQTT/HA
       -> optional mail
       -> optional SystemAction
```

## Configuration and command placeholders

The command template must contain the exact placeholders:

```text
SourceDataSet
DestDataSet
```

Example pull from a remote source to a local target:

```ini
SyncoidCommand = syncoid backupuser@server:SourceDataSet DestDataSet --sshkey /root/.ssh/syncerate --no-privilege-elevation
```

Runtime identity:

- the local side runs as the effective user executing `Syncerate.py`;
- the remote side runs as `backupuser` in this example;
- `--no-privilege-elevation` prevents Syncoid from invoking `sudo`; it does not switch the local process to a different user.
