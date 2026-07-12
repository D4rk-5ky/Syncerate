# Syncerate commented code map

This document maps the current `Syncerate.py` implementation. It explains what each function, command, configuration stage, and important safety branch does and why it exists.

## Program entry and global setup

### Shebang

```python
#!/usr/bin/python3
```

Allows the script to be executed directly when it has executable permission.

### Standard-library imports

- `argparse`: parses `--conf`, `-c`, and `--version`.
- `configparser`: reads the INI-style Syncerate configuration file.
- `sys`: supplies exit handling and terminal streams.
- `getpass.getpass`: securely asks for a password or SSH-key passphrase without echoing it.
- `logging`: writes terminal, `.log`, and `.err` output.
- `datetime`: creates timestamps for log filenames.
- `os`: handles paths, directories, file existence checks, and the effective UID inherited by local Syncoid processes.
- `pwd`: resolves the effective UID to the actual local username, including when Syncerate is started through `sudo`.
- `traceback`: retained for unexpected-error support.
- `subprocess`: runs the local `mail` command and the optional successful-run system action.
- `time`: waits before a system action when email is enabled.
- `shlex`: safely splits command templates and renders commands for logs.

### Required third-party import

- `pexpect`: starts Syncoid and reacts to SSH prompts, password prompts, warnings, failures, and end-of-process events.

### Optional third-party import

`paho-mqtt` is deliberately not imported at program startup. `send_mqtt_messages()` imports it only when MQTT is enabled and a successful run reaches the MQTT publishing stage. This lets non-MQTT installations run without the package.

### Global logger

```python
logger = logging.getLogger("syncerate")
```

Creates the named logger used by all functions. `get_logger()` later assigns its handlers.

### Exit-code constants

- `EXIT_OK = 0`: successful run.
- `EXIT_LIST_ERROR = 1`: source/destination list validation failed.
- `EXIT_SCRIPT_ERROR = 2`: unexpected Python or application error.
- `EXIT_WARNING = 4`: Syncoid produced a warning treated as fatal.
- `EXIT_PASSWORD_DENIED = 5`: authentication or permission failure.
- `EXIT_CONNECTION_TIMEOUT = 6`: remote connection timed out.
- `EXIT_CONNECTION_REFUSED = 7`: remote connection was refused.
- `EXIT_DATASET_MISSING = 8`: Syncoid skipped or could not use a dataset.
- `EXIT_REPEATED_PATTERN = 9`: the same `pexpect` pattern repeated too many times.
- `EXIT_MQTT_ERROR = 10`: MQTT dependency or publish failure.
- `EXIT_SYSTEM_ACTION_ERROR = 11`: reserved for system-action failures.

### Version constant

```python
VERSION = "0.4.3"
```

Provides one authoritative application version for `--version` and release tracking.

## Functions

### `option_is_enabled(value)`

Converts a configuration value to text, trims it, uppercases it, and returns `True` for:

```text
YES, TRUE, 1, ON
```

All other values, including `No`, `False`, `0`, `Off`, an empty value, or a missing option fallback, are disabled. This helper keeps MQTT and Home Assistant option handling consistent.

### `send_mail(subject, body, recipient, attachment_files=None)`

Builds and runs the local command:

```text
mail -s <subject> [--attach <file> ...] <recipient>
```

The email body is sent to the command through standard input. The function returns the command exit code and decoded standard-error text so the caller can report success or failure.

### `send_mqtt_messages()`

Runs only after a successful Syncerate operation when MQTT is enabled.

Execution order:

1. Imports `paho.mqtt.publish` locally.
2. Exits with MQTT error code `10` if the optional dependency is unavailable.
3. Reads broker address, port, optional username, optional password, topic, and payload.
4. Creates authentication data only when a username is present.
5. Lazily reads `Use_HomeAssistant` only after MQTT publishing is reached.
6. Adds a retained Home Assistant `online` availability message only when that option is enabled.
7. Always adds the configured retained Syncerate status message.
8. Publishes all messages with `publish.multiple()`.
9. Logs and exits with code `10` if publishing fails.

The Home Assistant availability topic is not read unless Home Assistant support is enabled.

### `MailTo(Exit_Code=None, SynCoidFail=None, MQTT_Fail=None)`

Central email-notification dispatcher.

It selects the email subject, body, and attachments for:

- successful completion;
- a Syncoid failure;
- a general script failure;
- an MQTT failure.

When file logging is enabled, it includes the available `.log`, `.err`, and `.out` files. It calls `send_mail()` and then `WasMailSent()`.

For error paths, it exits using the supplied failure code after attempting notification.

### `WasMailSent(MailExitCode, popenstderr)`

Logs whether the `mail` command succeeded. When it fails, the function records the command’s standard-error output for diagnosis.

### `SystemAction()`

Runs the configured `SystemAction` shell command after a successful Syncerate run.

- When email is enabled, it waits 120 seconds first so the mail process has time to complete.
- When email is disabled, it runs the command immediately.
- It uses `subprocess.run(..., shell=True, check=False)` because the configuration can contain a complete shell command.

This function is only called from the successful-run path.

### `successfull_run(MQTT=None, SendMail=None, PerformSystemAction=None)`

Final successful-completion coordinator.

It:

1. logs that all dataset transfers completed;
2. appends the completion text to the `.out` file when logging is enabled;
3. publishes MQTT messages only when normalized `Use_MQTT` is `YES`;
4. sends success email when configured;
5. runs the configured system action when configured.

The order is MQTT, mail, then system action.

### `missmatchinglists(Lenght, Names)`

Handles dataset-list validation failures.

- `Lenght=True` reports unequal source and destination item counts.
- `Names=True` reports source and destination pairs whose final dataset names differ.

It attempts email notification when enabled and exits with code `1`.

### `backup_header_text()`

Builds the optional backup title and comment section used at the start of email bodies. Empty or omitted values are skipped.

### `get_logger(enable_file_logging=True)`

Configures the named Syncerate logger.

Always creates:

- an INFO-level terminal handler writing to standard output.

When file logging is enabled, it also creates:

- `Syncerate-<timestamp>.log` for INFO and ERROR messages;
- `Syncerate-<timestamp>.err` for ERROR messages only.

Existing handlers are cleared first to avoid duplicate output if the logger is configured more than once.

### `read_dataset_list(path)`

Reads a source or destination list as UTF-8 and returns active entries only.

It removes surrounding whitespace and ignores:

- blank lines;
- lines whose trimmed text begins with `#`.

Dataset names containing internal spaces remain intact.

### `parse_destination_line(line)`

Parses one destination-list entry.

Supported forms:

```text
BackUp/Dataset
BackUp/Dataset: --recvoptions="o compression=zstd"
```

It uses `rsplit(": ", 1)` so a remote dataset prefix such as `user@host:pool/dataset` is not broken. Extra arguments are parsed with `shlex.split()` so quoted values remain one argument.

A malformed quoted argument raises `ValueError`, which becomes a list error before Syncoid starts.

### `parse_destination_list(destination_lines)`

Calls `parse_destination_line()` for every destination entry and returns two parallel lists:

1. destination dataset names;
2. per-destination extra argument lists.

Keeping these lists parallel lets `main()` append the correct extra arguments to each paired command.

### `die(child=None, errstr=None, error_code=None, SynCoidFail=None, MQTT_Fail=None, SynCoidFailChild=None)`

Central fatal-error handler.

It determines the exit code, records the relevant context, attempts to terminate an active child process, optionally sends email, and exits.

It has separate reporting branches for:

- a known active-child error;
- an unknown Syncoid nonzero exit;
- an MQTT error;
- a general script error.

### `log_command_debug(command_list)`

Logs a generated command in three diagnostic forms:

- shell-style text from `shlex.join()`;
- the raw Python argument list;
- every individual argument and index.

This is useful for verifying that spaces, SSH options, placeholders, and per-destination arguments are preserved correctly.

### `build_syncoid_command(command_template, source_dataset, dest_dataset, extra_args=None)`

Safely builds the argument list passed to `pexpect.spawn()`.

Important order:

1. split the command template with `shlex.split()`;
2. replace `SourceDataSet` and `DestDataSet` inside each already-separated argument;
3. append per-destination extra arguments.

Splitting before replacement keeps a dataset such as `Storage/DataSet With Spaces` as one argument rather than three.

### `close_child_logfile(child)`

Flushes and closes the file attached to `child.logfile`, then sets the attribute to `None`. This prevents leaked file handles and duplicate close attempts.

### `safe_text(value)`

Returns an empty string for `None`; otherwise returns `str(value)`. Error logging uses this helper because some `pexpect` fields may be unset.

### `effective_user_name()`

Resolves `os.geteuid()` through the local password database. This reports the real effective account inherited by Syncoid and local ZFS commands. When a UID has no local name, it returns the numeric UID instead of failing.

### `ssh_command(SynCoid_Command)`

Starts one Syncoid command with `pexpect.spawn()` and watches its output until completion or a handled failure.

Despite the function name, it also runs local-to-local Syncoid commands. `pexpect.spawn()` does not switch users: the child inherits Syncerate's effective local UID. Remote endpoints are left unchanged, so Syncoid uses the SSH username written in the source or destination argument. The function logs this local identity before starting each child.

It initializes three transfer-state flags:

- `ISREPEATED`: the same matched pattern exceeded the safety limit;
- `CONTINUENODESTROYSNAP`: the known missing Syncoid-created snapshot warning was seen;
- `CONTINUENORESUME`: the previous resume state is unusable and the command must be retried with `--no-resume`.

Recognized patterns and actions:

- SSH host-key confirmation: sends `yes`.
- Missing snapshot-to-destroy message: records the known nonfatal condition and continues.
- Permission denied: exits with code `5`.
- Connection timed out: exits with code `6`.
- Connection refused: exits with code `7`.
- Passphrase or password prompt: sends the configured value, or fails safely when `PassWord=No`.
- End of file: closes output logging and returns the child process.
- `WARN Skipping dataset`: exits with code `8`.
- Missing resume snapshot: returns a modified command containing `--no-resume`.
- Resume capability unavailable: logs Syncoid's exact message as nonfatal and continues because Syncoid explicitly says the transfer will proceed without resume support.
- Generic warning: treats it as fatal except for the specifically recognized nonfatal destroy warning.

Each pattern may match at most five times. More matches trigger the repeated-pattern safety exit instead of allowing an endless prompt loop.

### `main()`

Runs all paired dataset transfers.

For each source, destination, and destination-extra-argument set, it:

1. builds the complete Syncoid argument list;
2. logs the command and its arguments;
3. logs the effective local user and executes it through `ssh_command()`;
4. allows only the exact nonfatal resume-capability message to continue to Syncoid's real exit status;
5. retries once with `--no-resume` when an old resume state is unusable;
6. detects signal termination;
7. handles nonzero Syncoid exit codes;
8. permits only the specifically recognized nonfatal destroy-snapshot condition.

After every pair succeeds, it calls `successfull_run()`.

## Module-level configuration and validation flow

The current script performs configuration preparation before `main()` starts:

1. Creates the argument parser.
2. Reads `--conf` / `-c`.
3. Supports `--version` without requiring a config file.
4. Loads the INI configuration.
5. Reads mail and system-action options.
6. Normalizes `Use_MQTT` with a default of disabled.
7. Leaves Home Assistant options untouched until successful MQTT publishing is reached.
8. Creates the timestamp and logger.
9. Logs non-secret configuration values while omitting password, MQTT credentials, and lazy Home Assistant settings; disabled MQTT settings are skipped.
10. Reads and parses both dataset lists.
11. Verifies equal active-line counts.
12. Verifies each source and destination pair has the same final dataset name.
13. Resolves password handling.
14. Reads the Syncoid command template.

## CLI commands

### Show help

```bash
./Syncerate.py --help
```

Displays the available command-line options and exits without loading a config file or MQTT dependency.

### Show version

```bash
./Syncerate.py --version
```

Prints the current application version and exits.

### Run a configured backup

```bash
./Syncerate.py --conf /path/to/Syncerate.cfg
```

Equivalent short form:

```bash
./Syncerate.py -c /path/to/Syncerate.cfg
```

## External commands

### `syncoid`

Built from `SyncoidCommand`, source-list entries, destination-list entries, and optional per-destination arguments. It performs the actual ZFS replication.

### `mail`

Used only when `Mail` is not `No`. It sends success or failure notifications and optional log attachments.

### Configured `SystemAction`

Used only after all transfers and enabled notifications complete successfully. Because it is passed to a shell, the config owner must treat this option as trusted command execution.

## Home Assistant support file

`config/HomeAssistant-Configuration-For-MQTT.yaml` is an optional example MQTT binary sensor. The Python program does not load this YAML file. Home Assistant reads it only when the user installs it in Home Assistant configuration.

The two PNG files in `config/` are retained reference screenshots and are not loaded by Syncerate.
