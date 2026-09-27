# Syncerate

Syncerate processes each matching source and destination ZFS dataset pair listed in two text files. Dataset pairs run sequentially, and optional retry handling can repeat an individual pair when a Broken Pipe occurs.

Current version: `0.4.34`

## Disclaimer and liability notice

> **AI-assisted / vibe-coded experimental hobby software. Use at your own risk.**

Syncerate is provided **“as is”**, without warranty of any kind. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss risks, security problems, or incorrect assumptions.

### Data-loss warning

Syncerate starts Syncoid and ZFS-related operations that can affect source datasets, destination datasets, snapshots, and backup targets. Depending on the configured Syncoid options and available permissions, a run may:

- create snapshots and destination datasets;
- receive replicated data into a target dataset;
- resume or retry an interrupted receive;
- roll back or replace target state when required by Syncoid/ZFS;
- delete target snapshots when destructive Syncoid options are configured;
- execute the configured `SystemAction` as a shell command after a successful run.

Syncerate does **not** provide an application-level dry-run mode. Before using it with important data:

- read and understand the configured `SyncoidCommand`;
- review every source/destination pair and per-destination argument;
- test first with non-critical datasets on a non-production system;
- keep a separate, verified backup that Syncerate cannot modify;
- grant only the ZFS and system permissions that are actually required;
- review the logs and verify the destination before relying on the backup.

By using this software, you accept responsibility for reviewing, configuring, testing, and operating it. The author is not responsible for data loss, damaged pools, deleted snapshots, broken backups, system damage, service interruption, security issues, or any other problem caused by using this project.

## Requirements

Required:

- Python 3
- ZFS
- Sanoid/Syncoid
- Python `pexpect`
- SSH access when a source or destination is remote

Optional:

- OpenSSH `ssh-agent` and `ssh-add` when `UseSSHAgent = Yes`
- Python `paho-mqtt` when MQTT publishing is enabled
- a configured local `mail` command when email is enabled
- Home Assistant when using the supplied MQTT availability example

On Debian or Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-pexpect sanoid openssh-client
```

Install MQTT support only when needed:

```bash
sudo apt install python3-paho-mqtt
```

Install local mail support only when needed:

```bash
sudo apt install postfix mailutils
```

## Standalone PyInstaller executable

Release builds can include a single-file executable at `dist/Syncerate`. The executable is built with PyInstaller in one-file/console mode and contains the Python interpreter plus the Python packages Syncerate needs, including `pexpect` and `paho-mqtt`. A machine running that executable therefore does **not** need Python, `pexpect`, or `paho-mqtt` installed separately.

The executable does not bundle external operating-system programs. `syncoid`/Sanoid, OpenSSH, ZFS commands, and the optional local `mail` command must still exist on the target system when the corresponding Syncerate features use them. Configuration files and source/destination list files also remain external so they can be edited normally.

PyInstaller output is platform-specific. A Linux x86-64 build is for compatible Linux x86-64 systems; build separately on Linux ARM/Raspberry Pi, Windows, or macOS for those platforms. PyInstaller is not a cross-compiler.

Run the packaged executable exactly like the Python entry point:

```bash
./dist/Syncerate --version
./dist/Syncerate --help
./dist/Syncerate --conf /path/to/Syncerate.cfg
```

### Rebuilding the executable

`requirements-build.txt`, `Syncerate.spec`, and `build_pyinstaller.sh` define the reproducible build path. Create a clean virtual environment, install the pinned build/runtime dependencies, then run the build script:

```bash
python3 -m venv .venv-build
. .venv-build/bin/activate
python -m pip install -r requirements-build.txt
./build_pyinstaller.sh
```

`build_pyinstaller.sh` removes previous `build/` and `dist/` output, runs the checked-in PyInstaller spec, verifies that `dist/Syncerate` exists and is executable, and checks its `--version` and `--help` commands. The spec explicitly collects both `pexpect` and the dynamically imported `paho.mqtt` package so MQTT support is present even though `paho-mqtt` is imported only when MQTT is enabled.

## Prepare the application

Make the entry point executable:

```bash
chmod +x Syncerate.py
```

Copy the example configuration:

```bash
cp config/example-Syncerate.cfg config/Syncerate.cfg
```

Create source and destination list files, then edit `config/Syncerate.cfg` with their paths and the Syncoid command to run.

## Command-line options

Syncerate has three application flags. `--conf`/`-c` is required for a normal replication run; `--help` and `--version` exit directly from the argument parser and therefore do not require a configuration file or start runtime work.

| Option | Required | What it does |
| --- | --- | --- |
| `-c FILE`, `--conf FILE` | Yes for a normal run | Selects the required Syncerate INI configuration file. There is no implicit/default config path. Relative paths are resolved from the current working directory. The selected file must contain the `[Syncerate Config]` section. |
| `-h`, `--help` | No | Prints the complete command syntax, flag descriptions, and examples, then exits with argparse's normal success status. It does not load the configuration, create logs, read dataset lists, request credentials, or start Syncoid. |
| `--version` | No | Prints `<program-name> 0.4.34` and exits. The program name reflects the entry point used, for example `Syncerate.py 0.4.34` from the Python script or `Syncerate 0.4.34` from `dist/Syncerate`. It does not start a replication run. |

### `--conf FILE` / `-c FILE`

The long and short forms are identical. Supply exactly one configuration path for every normal run:

```bash
./Syncerate.py --conf ./config/Syncerate.cfg
./Syncerate.py -c ./config/Syncerate.cfg
```

An absolute path is also valid:

```bash
./Syncerate.py --conf /etc/syncerate/Syncerate.cfg
```

If the file cannot be read, its required section/options are missing, or a documented value fails validation, Syncerate reports a configuration error and returns exit code `2` before replication begins.

### `--help` / `-h`

```bash
./Syncerate.py --help
```

Use this to see the executable's current syntax and examples. No `--conf` argument is needed when requesting help.

### `--version`

```bash
./Syncerate.py --version
./dist/Syncerate --version
```

No `--conf` argument is needed when requesting the version. The displayed executable name intentionally follows the actual entry point, so source and PyInstaller builds do not have to pretend to have the same filename.

Run the packaged regression suite after installation or modification with:

```bash
python3 -m unittest discover -s tests -v
```

The suite uses Python's standard `unittest` framework and the same `pexpect` dependency required by Syncerate. It uses fake child processes and does not run real ZFS replication.

## Source dataset list

Put one source dataset on each active line:

```text
Storage/Home-Assistant
Storage/Media
Storage/DataSet With Spaces
```

Blank lines and lines beginning with `#` are ignored. Each source and destination file must contain at least one active dataset. Dataset names must not end with `/`; a trailing slash is rejected so two malformed names cannot accidentally match on an empty final component.

Write dataset names containing spaces normally. Do not add shell escape characters:

```text
Storage/DataSet With Spaces
```

## Destination dataset list

Put one destination dataset on each active line in the same order as the source list:

```text
BackUp/Home-Assistant
BackUp/Media
BackUp/DataSet With Spaces
```

Pairing is positional:

```text
source line 1 -> destination line 1
source line 2 -> destination line 2
source line 3 -> destination line 3
```

The two files must contain the same number of active lines. The final dataset component in each pair must also match.

Valid:

```text
Storage/Home-Assistant
BackUp/Home-Assistant
```

Invalid:

```text
Storage/Home-Assistant
BackUp/Grafana
```

The matching final name protects against accidentally pairing unrelated datasets.

### Per-destination Syncoid arguments

Add arguments that apply to only one destination after a colon followed by one space:

```text
BackUp/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
```

The separator must be exactly:

```text
: 
```

Remote destinations remain supported because the SSH `host:dataset` colon has no following space, while Syncerate splits only on the **first** exact colon-space separator:

```text
backupuser@192.0.2.20:BackUp/Media: --recvoptions="o compression=zstd"
```

The text after the separator is parsed with `shlex` as command arguments and appended to the Syncoid command for that dataset pair only. Because only the first `: ` separator is consumed, quoted argument values may themselves contain `: ` text without changing the destination dataset.

## Configuration file

The file must contain this section:

```ini
[Syncerate Config]
```

A complete example:

```ini
[Syncerate Config]

BackupTitle = Main ZFS backup
BackupComment = Replicate selected datasets to the backup pool
    This is a second line in the same backup comment.

SourceListPath = /absolute/path/to/source-list
DestListPath = /absolute/path/to/destination-list

SyncoidCommand = syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --compress none --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation

PassWord = No
UseSSHAgent = No
SSHAgentKeyLifetimeSeconds = 3600
Mail = No
SendMailOnSuccess = True
DateTime = %Y-%m-%d_%H_%M_%S
LogDestination = No
SystemAction = No

ContinueWithoutResume = True
RetryBrokenPipe = No
BrokenPipeRetryCount = 1
BrokenPipeRetryWaitSeconds = 10

Use_MQTT = No
SendMQTTOnSuccess = True
broker_address = mqtt.example.com
broker_port = 1883
mqtt_username =
mqtt_password =
mqtt_topic = home-assistant/syncerate/command
mqtt_message = ON

Use_HomeAssistant = No
HomeAssistant_Available = home-assistant/syncerate/available

MQTT_JSON_Status = No
mqtt_json_topic = homeassistant/syncerate/status
```

## Configuration options

| Option | Required | Accepted value or purpose |
| --- | --- | --- |
| `BackupTitle` | No | Optional short name included in logs, email content, and JSON MQTT `title`/compatibility `name` fields. |
| `BackupComment` | No | Optional description included in logs and email content. It may span multiple lines by indenting every continuation line in the INI file. |
| `SourceListPath` | Yes | Path to the source dataset list. Relative paths are resolved from the current working directory. |
| `DestListPath` | Yes | Path to the destination dataset list. Relative paths are resolved from the current working directory. |
| `SyncoidCommand` | Yes | Non-empty Syncoid command template containing exactly one `SourceDataSet` placeholder and exactly one `DestDataSet` placeholder. The command must also be valid `shlex` syntax. |
| `PassWord` | Yes | Non-empty value: `No`, `Ask`, or a literal SSH password/key passphrase. With private-agent mode, `Ask` is recommended for encrypted keys so the passphrase is not stored in the configuration. |
| `UseSSHAgent` | No | Enables an isolated per-run OpenSSH agent with `Yes`, `True`, `1`, or `On`. Requires `--sshkey` in `SyncoidCommand`. Disabled values preserve the legacy Pexpect-through-Syncoid authentication path. |
| `SSHAgentKeyLifetimeSeconds` | No | Positive whole-number lifetime for the identity loaded into the private agent. Defaults to `3600`. If it expires during a long run, Syncerate reloads it before the next dataset. |
| `Mail` | Yes | Recipient address, or `No` to disable email completely. |
| `SendMailOnSuccess` | No | Boolean controlling only success/warning-success email. Defaults to `True` when omitted. Setting it to `No` does **not** suppress error email; errors still send whenever `Mail` contains a recipient. |
| `DateTime` | Yes | Python `strftime` pattern used in log filenames. |
| `LogDestination` | Yes | Directory for `.log`, `.err`, and `.out` files, or `No` for terminal-only logging. |
| `SystemAction` | Yes | Trusted shell command executed after a successful run, or `No` to disable it. |
| `ContinueWithoutResume` | No | Boolean; defaults to `True`. Logs Syncoid’s resume-unavailable warning and continues when true. `False` stops the run with exit code `4` and uses the normal error-notification path. Other warnings do not cause failures. |
| `RetryBrokenPipe` | No | Enables dataset-level Broken Pipe retry handling. Each dataset receives its own retry allowance. When that allowance is exhausted, only that dataset is skipped, the remaining list continues, and the completed run records a successful warning. Missing or disabled values preserve normal Syncoid failure handling. |
| `BrokenPipeRetryCount` | No | Number of retries allowed for each individual dataset after its initial attempt. Defaults to `1` when omitted. The count resets for every dataset pair. Use `0` to skip an affected dataset immediately after its first Broken Pipe. Negative values and non-integers are rejected. |
| `BrokenPipeRetryWaitSeconds` | No | Whole number of seconds to wait before each Broken Pipe retry. Defaults to `10` when omitted. Use `0` to retry immediately. Negative values and non-integers are rejected as configuration errors. |
| `Use_MQTT` | No | Enables MQTT with `Yes`, `True`, `1`, or `On`. Success publishes retained `mqtt_message` to `mqtt_topic` when `SendMQTTOnSuccess` is true. Failures publish non-retained JSON to `<mqtt_topic>/error`, or to `mqtt_json_topic` when JSON status is enabled. |
| `SendMQTTOnSuccess` | No | Boolean controlling MQTT publishing only for successful/warning-success runs. Defaults to `True` when omitted. `False` suppresses MQTT/HA success signals and JSON success events. Errors still publish whenever `Use_MQTT` or `MQTT_JSON_Status` is enabled. |
| `broker_address` | When `Use_MQTT` or `MQTT_JSON_Status` is enabled | MQTT broker hostname or IP address shared by the enabled MQTT outputs. |
| `broker_port` | When `Use_MQTT` or `MQTT_JSON_Status` is enabled | MQTT broker TCP port as an integer from `1` through `65535`, commonly `1883`. |
| `mqtt_username` | No | MQTT username shared by the enabled MQTT outputs. Leave empty when authentication is not used. |
| `mqtt_password` | No | MQTT password shared by the enabled MQTT outputs. Leave empty when authentication is not used. |
| `mqtt_topic` | When `Use_MQTT = Yes` | Topic for retained success messages. When only `Use_MQTT` is enabled, failure JSON goes to this exact topic plus `/error`; for example, `syncerate/result/error`. |
| `mqtt_message` | When `Use_MQTT = Yes` | Original retained success-only payload. Fatal run failures do not publish this legacy message. |
| `Use_HomeAssistant` | No | Preserves the original Home Assistant availability integration. When both this and `Use_MQTT` are enabled, retained payload `online` is additionally published to `HomeAssistant_Available`. |
| `HomeAssistant_Available` | When `Use_MQTT = Yes` and HA integration is enabled | Original Home Assistant availability topic. Payload `online` remains retained. |
| `MQTT_JSON_Status` | No | Independently enables structured success/failure JSON status. It may run together with the old MQTT/HA outputs or by itself while `Use_MQTT = No`. JSON is always non-retained. |
| `mqtt_json_topic` | When `MQTT_JSON_Status = Yes` | Dedicated JSON-only topic. It must differ from an enabled `mqtt_topic` and `HomeAssistant_Available`; every JSON publish hard-codes `retain = false`. |

Boolean options (`UseSSHAgent`, `ContinueWithoutResume`, `RetryBrokenPipe`, `Use_MQTT`, `SendMailOnSuccess`, `SendMQTTOnSuccess`, `Use_HomeAssistant`, and `MQTT_JSON_Status`) accept `Yes`/`No`, `True`/`False`, `1`/`0`, or `On`/`Off` case-insensitively. Other spellings are rejected at startup instead of being silently treated as disabled. `SendMailOnSuccess`, `SendMQTTOnSuccess`, and `ContinueWithoutResume` default to enabled when omitted. Other Boolean options default to disabled.

When MQTT is enabled, the broker address, valid port, and the topics required by the enabled channel are validated before replication starts. Although some integrations are disabled with `No`, the required keys should remain in the configuration so startup validation succeeds. Required text options may not be empty; use the documented `No` value to disable mail, logging, or the system action.

## Syncoid command templates

The template must contain exactly one occurrence of each of these case-sensitive placeholders:

```text
SourceDataSet
DestDataSet
```

Syncerate replaces them separately for every dataset pair and starts Syncoid with an argument list rather than one shell command string. This preserves dataset names containing spaces.

### Local source to local destination

```ini
SyncoidCommand = syncoid SourceDataSet DestDataSet
```

The local Syncoid process and local ZFS commands run as the effective user that started `Syncerate.py`.

### Remote source to local destination

```ini
SyncoidCommand = syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation
```

### Local source to remote destination

```ini
SyncoidCommand = syncoid SourceDataSet backupuser@192.0.2.20:DestDataSet --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation
```

A remote endpoint uses the SSH user written before `@`. `--sshport` selects a non-default SSH port, and `--sshkey` selects the key used for authentication.

Use Syncoid's `--no-privilege-elevation` when the local and remote users already have the required ZFS permissions and Syncoid should not invoke `sudo`. When Syncerate itself is run as root, local ZFS commands already run as root; a non-root remote SSH user still needs appropriate delegated ZFS permissions.

Any other Syncoid options can be included in `SyncoidCommand` or added to individual destination lines.

## Password and passphrase handling

`PassWord` still supports three modes:

```ini
PassWord = No
PassWord = Ask
PassWord = your-secret
```

`Ask` prompts once with `getpass()` when Syncerate starts and is recommended for an encrypted SSH key because the passphrase is not stored in the configuration. Password, MQTT credentials, and other secret-like option names are omitted from normal configuration logging. Only the `[Syncerate Config]` section is logged; unrelated INI sections are not echoed.

### Recommended encrypted-key mode: private ssh-agent

Enable the isolated agent path with:

```ini
UseSSHAgent = Yes
SSHAgentKeyLifetimeSeconds = 3600
PassWord = Ask
```

The `SyncoidCommand` must contain the identity explicitly, for example:

```ini
SyncoidCommand = syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --sshkey /root/.ssh/syncerate --no-privilege-elevation
```

Private-agent mode uses this process model: **Pexpect starts Syncoid, and Syncoid remains responsible for starting and controlling SSH, mbuffer, pv, ZFS send/receive, and its own SSH control connections.** Syncerate does not replace Syncoid's SSH process and does not rewrite the configured Syncoid command with hidden SSH options.

When enabled, Syncerate:

1. creates a random per-run temporary directory with mode `0700`;
2. starts a new foreground `ssh-agent` bound to a socket inside that directory;
3. ignores any pre-existing `SSH_AUTH_SOCK` / `SSH_AGENT_PID`;
4. removes inherited `SSH_ASKPASS` use for the private-agent path;
5. runs `ssh-add` under Pexpect directly and sends the configured key passphrase to that direct prompt;
6. loads the identity selected by the existing `--sshkey` option with the configured bounded lifetime;
7. exposes the isolated agent to Syncoid only through the child environment (`SSH_AUTH_SOCK` / `SSH_AGENT_PID`);
8. starts the **original configured Syncoid argv under Pexpect unchanged**; Syncoid then creates SSH/mbuffer/ZFS processes exactly as it normally does;
9. keeps the original Pexpect-through-Syncoid password/passphrase prompt handling available if Syncoid's nested SSH still asks interactively;
10. checks that the agent still contains an identity before each dataset and reloads it if the configured lifetime expired;
11. removes agent identities, terminates the agent, and removes its temporary socket directory when the run exits normally or raises an application error.

The one-hour default limits the usefulness of an orphaned agent if the Python process is terminated in a way that prevents cleanup. A transfer already authenticated through Syncoid's SSH control connection can continue if the identity lifetime expires; Syncerate reloads the key before the next dataset.

Syncerate does not prepend `ForwardAgent`, `StrictHostKeyChecking`, `IdentitiesOnly`, `IdentityAgent`, `AddKeysToAgent`, `BatchMode`, or `PreferredAuthentications` settings to the Syncoid command. SSH behavior therefore comes from the configured `SyncoidCommand`, Syncoid itself, and the executing user's normal SSH configuration.

The private agent is still isolated and contains only the configured Syncerate identity. If your own SSH configuration enables agent forwarding, Syncerate does not override that policy; disable forwarding in your SSH/Syncoid configuration if you do not want the agent exposed to a remote host.

### Legacy authentication mode

With:

```ini
UseSSHAgent = No
```

Syncerate uses the original Pexpect-through-Syncoid model. Pexpect starts Syncoid and watches the output produced by Syncoid and its nested SSH process. If an SSH account-password or private-key-passphrase prompt appears, Syncerate temporarily disables the `.out` logfile, sends `PassWord` directly to the Syncoid Pexpect child, then restores logging. The nested Syncoid prompt path deliberately does not wait for a separate no-echo transition before sending, preserving the established behavior. If `PassWord = No`, an observed credential prompt remains a fatal authentication error. Prompt matching is shaped like a real password/passphrase prompt, so ordinary output containing words such as `password` is not treated as a request for a secret.

## Multiline backup comments

`BackupComment` uses normal INI continuation lines. Put the first line after `BackupComment =` and indent every following line with spaces or a tab:

```ini
BackupTitle = Main ZFS backup
BackupComment = Replicate selected datasets to the backup pool
    This line explains why the backup is running.
    This line can contain another useful note.
```

Do not wrap the whole multiline value in quotes. Quotes would become part of the value, and an unindented second physical line is not a continuation. Syncerate preserves the embedded newlines for email content and logs each comment line separately so terminal and `.log` output keep their normal timestamp/level prefix.

## Logging

Terminal-only logging:

```ini
LogDestination = No
```

Write files to a directory:

```ini
LogDestination = /var/log/syncerate
```

Syncerate creates the directory when necessary and can write:

```text
Syncerate-<timestamp>.log
Syncerate-<timestamp>.err
Syncerate-<timestamp>.out
```

- `.log` contains normal application messages.
- `.err` contains ERROR-level application messages.
- `.out` contains Syncoid process output.

The timestamp is generated from `DateTime`, for example:

```ini
DateTime = %Y-%m-%d_%H_%M_%S
```

For every normal invocation, Syncerate starts a monotonic runtime timer before configuration/runtime work. The reported `Total runtime` is captured when the replication run has reached its success/failure result, immediately before post-run email and `SystemAction` handling. This fixed cut-off is intentional: it allows the **same runtime value** to be written to terminal, `.log`, and the email that is about to be sent. Time spent sending that same email, waiting the optional two minutes before a system action, or executing the system action cannot be included in an email that has already been constructed.

For successful and warning-success runs, Syncerate also reports `Data transferred`. It reads the byte counter emitted by Syncoid's normal `pv` progress stream, keeps the highest observed byte count for each individual Syncoid send stream, and sums those completed/attempted streams across all dataset pairs. This avoids counting repeated progress refreshes more than once while still including bytes that were actually retransmitted during a Broken Pipe retry. The displayed unit is chosen automatically using 1024-based thresholds: `KB`, `MB`, `GB`, or `TB`. Values smaller than 1 KB are shown as a fractional KB.

Syncerate deliberately does **not** guess a transfer size from Syncoid's rounded `(~ size)` estimates. If a transfer starts but a usable `pv` byte counter cannot be observed—for example because `--quiet` suppresses progress, `pv` is unavailable, or custom `--pv-options` replace the normal byte-counter output—the final success summary reports `Data transferred :   Unavailable`.

The final run summary writes `Final run summary`, inserts one blank line, repeats `BackupTitle` and `BackupComment` when configured with another blank line between the title and comment for readability, inserts another blank line after the comment, then prints the transfer total (for completed replication summaries), inserts one blank line, and prints elapsed time as `HH:MM:SS.mmm`. It is written to the normal logger **before the success email is built**, so the `.log` file attached/copied into the email already contains the transfer total and timer. Success/warning-success email bodies use the same summary. Ordinary interrupted error paths include metadata/runtime but do not claim a complete transfer total. The special missing-dataset/pool failure path is different because Syncerate deliberately completes the remaining configured list first; that completed-list failure may therefore include the measured transfer total together with exit code `8`. `--help` and `--version` do not produce a runtime summary.

Example:

```text
Final run summary

Backup title    :   Main ZFS backup

Backup comment  :   Replicate selected datasets to the backup pool
                    Second comment line

Data transferred :   18.47 GB

Total runtime   :   01:23:45.678
```

## Email notifications

Disable email:

```ini
Mail = No
```

Enable email:

```ini
Mail = user@example.com
SendMailOnSuccess = True
```

`SendMailOnSuccess` defaults to `True` when omitted. Set it to `False` when you want email only for failures. This switch is checked only on the successful/warning-success path; it does not suppress error mail. As long as `Mail` contains a recipient, handled Syncerate errors still attempt to send their normal error email.

A working local `mail` command is required for delivery. Syncerate can send success, warning-success, Syncoid-error, script-error, and MQTT-error messages. Success and warning-success email bodies begin with the same final run summary used in terminal/file logging: `Final run summary`, a blank line, backup title, a blank line, multiline backup comment, another blank line, `Data transferred`, another blank line, and `Total runtime`. Ordinary interrupted error emails include the same metadata/runtime but omit transfer totals because the replication list did not complete. Missing-dataset/pool failures are reported separately: Syncerate first continues through the remaining configured pairs, then sends an exit-code-`8` failure mail that lists every failed pair plus the matched ZFS/Syncoid message and may include the completed-list transfer total. When file logging is enabled, relevant `.log`, `.err`, and `.out` files are attached when available. Mail delivery is best-effort: a missing `mail` executable, attachment/read failure, or non-zero mail-command result is logged and does not replace the replication result.

When `RetryBrokenPipe` is enabled and a dataset is skipped after exhausting its configured retry count, the run still returns success when no other failure occurs. The success email subject is exactly:

```text
Syncerate Succsful - WARNING BROKEN PIPE
```

The email body lists the skipped source and destination dataset pairs.

## Syncoid warnings and resume support

Syncoid `WARN` and `WARNING` lines are ignored for failure detection, including skipped-dataset, missing-snapshot cleanup, and known-host warnings. Matching is case-insensitive and accepts leading indentation. Ordinary warnings are not separately logged or added to the failure summary; their original text remains in `.out` when file logging is enabled.

A warning alone does not make the run fail. Syncoid's real exit status remains authoritative: a warning followed by exit `0` is successful; a non-zero exit still fails. Warning text containing words such as `Permission denied` or `Broken pipe` is treated as part of that warning. A separate non-warning error line still receives its normal handling.

The exception is Syncoid's `ZFS resume feature not available` warning:

```ini
ContinueWithoutResume = True
```

This optional Boolean defaults to `True` and accepts the same true/false spellings as the other Boolean settings. Syncerate logs the resume-unavailable warning and waits for Syncoid to finish. A later error or non-zero exit still fails.

To require resume support:

```ini
ContinueWithoutResume = False
```

Syncerate stops the current child process and returns exit code `4` when that warning is observed. The remaining dataset pairs and successful-run actions are not started. Enabled error notifications are attempted, even when success notifications are disabled. This reacts to Syncoid's output; it does not perform a separate capability check before Syncoid starts.

## Interrupted receive recovery

Syncoid owns resumable-receive recovery. When the source snapshot for an interrupted receive no longer exists, Syncerate lets Syncoid reset the stale receive state and start a replacement send without modifying the configured command.

Syncerate retains internal recovery tracking for the non-warning stale-source message and the receive-reset announcement. The reset warning itself is ignored without separate warning logging; it only supplies context so a following non-warning Broken Pipe during that reset does not consume the ordinary retry allowance. A new `INFO: Sending incremental` or `INFO: Sending full` clears that recovery state.

`ContinueWithoutResume` controls unavailable resume support, not stale-state recovery. Real process failures still fail, including a non-zero exit after a missing destroy-snapshot message.

## Optional Broken Pipe retry

The feature is disabled by default:

```ini
RetryBrokenPipe = No
```

Enable it and select the retry count and wait time with:

```ini
RetryBrokenPipe = Yes
BrokenPipeRetryCount = 1
BrokenPipeRetryWaitSeconds = 10
```

`BrokenPipeRetryCount` is the number of retries allowed **after the initial attempt for each individual dataset pair**. It defaults to `1` when omitted. A value of `3` permits up to four total attempts for a dataset: the initial attempt plus three retries. A value of `0` skips an affected dataset immediately after its first detected Broken Pipe.

`BrokenPipeRetryWaitSeconds` is the number of whole seconds to wait before each retry. It defaults to `10` when omitted, and `0` retries immediately.

When enabled, Syncerate watches Syncoid output case-insensitively for the text `Broken pipe` and applies this policy independently to every dataset pair. The exception is a Broken Pipe emitted while Syncoid is actively resetting a stale interrupted receive; that expected recovery symptom is logged and ignored until Syncoid starts the replacement send. For ordinary Broken Pipe events:

1. Broken Pipe stops only the current Syncoid attempt.
2. If that dataset still has retries available, Syncerate waits for `BrokenPipeRetryWaitSeconds` and retries the same dataset with the same command.
3. If Broken Pipe continues after all `BrokenPipeRetryCount` retries are used, Syncerate skips only that dataset and continues with the next source/destination pair.
4. The next dataset starts with a fresh retry counter and receives its full configured retry allowance.
5. After the remaining list finishes, Syncerate returns exit code `0` when no other fatal error occurred.
6. Logs and the success email identify every dataset pair skipped after exhausting its retries.

The retry count is never shared between datasets. This option does not retry authentication failures, non-warning missing-dataset errors, connection failures, or other nonzero Syncoid exits. Warning lines do not trigger retries. When the option is disabled or omitted, Broken Pipe is not given special retry handling; Syncerate waits for Syncoid's real exit status and applies the normal failure behavior.

## MQTT notifications

`SendMQTTOnSuccess` is optional and defaults to `True`. Setting it to `False` suppresses successful and warning-success MQTT messages, including Home Assistant availability and JSON success events. It does not disable error reporting.

| Enabled MQTT options | Success, when `SendMQTTOnSuccess = True` | Handled error, regardless of the success switch |
| --- | --- | --- |
| `Use_MQTT` only | Retained `mqtt_message` on `mqtt_topic`, plus configured HA availability | Non-retained JSON on `<mqtt_topic>/error` |
| `MQTT_JSON_Status` only | Non-retained JSON on `mqtt_json_topic` | Non-retained JSON on `mqtt_json_topic` |
| Both | Both success outputs | One non-retained JSON event on `mqtt_json_topic` |
| Neither | No MQTT publishing | No MQTT publishing |

The error topic for `Use_MQTT` alone is derived by appending `/error` to the exact configured `mqtt_topic`; there is no extra configuration key. Subscribe your error handler to that topic. Error events use the JSON schema below and contain `status`, `exit_code`, `error`, and captured output in `stderr`. They never publish the success payload or availability `online`, and never replace a retained success message.

For email and MQTT only on errors, configure:

```ini
Mail = user@example.com
SendMailOnSuccess = False
Use_MQTT = True
SendMQTTOnSuccess = False
broker_address = mqtt.example.com
broker_port = 1883
mqtt_topic = syncerate/result
mqtt_message = ON
MQTT_JSON_Status = False
```

This sends error email and publishes failure JSON on `syncerate/result/error`. Keep the other required application settings in your configuration. Enable `MQTT_JSON_Status` and set `mqtt_json_topic` to route errors to a dedicated status topic instead.

### Original retained MQTT behavior

Enable retained success messages and non-retained error reports:

```ini
Use_MQTT = Yes
SendMQTTOnSuccess = True
broker_address = 192.0.2.30
broker_port = 1883
mqtt_username = syncerate
mqtt_password = secret
mqtt_topic = home-assistant/syncerate/command
mqtt_message = ON
```

After replication completes successfully, Syncerate publishes `mqtt_message` to `mqtt_topic` with **retain enabled** when `SendMQTTOnSuccess` is true. Handled failures publish JSON on `<mqtt_topic>/error` when JSON status is disabled, or on `mqtt_json_topic` when enabled.

To add the original Home Assistant availability integration:

```ini
Use_MQTT = Yes
Use_HomeAssistant = Yes
HomeAssistant_Available = home-assistant/syncerate/available
```

On a successful run with `SendMQTTOnSuccess = True`, Syncerate additionally publishes retained payload `online` to `HomeAssistant_Available`. This old HA behavior remains tied to `Use_MQTT` and is unchanged.

A matching example entity configuration is supplied in:

```text
config/HomeAssistant-Configuration-For-MQTT.yaml
```

### Independent JSON success/failure status

JSON can be enabled **in addition to** the old outputs:

```ini
Use_MQTT = Yes
MQTT_JSON_Status = Yes

mqtt_topic = home-assistant/syncerate/command
mqtt_message = ON
mqtt_json_topic = homeassistant/syncerate/status
```

Or JSON can run by itself while the old MQTT output is disabled:

```ini
Use_MQTT = No
MQTT_JSON_Status = Yes
broker_address = 192.0.2.30
broker_port = 1883
mqtt_json_topic = homeassistant/syncerate/status
```

The JSON topic is deliberately separate from the retained legacy topics. When both old MQTT and JSON are enabled, `mqtt_json_topic` must differ from `mqtt_topic`; when the old Home Assistant availability integration is also enabled, it must differ from `HomeAssistant_Available` as well.

**Every JSON publish uses `retain = false`. There is no configuration option that can enable retain for JSON.** This prevents Syncerate from creating a retained JSON success/failure event that Home Assistant could replay on reconnect. Use a new dedicated topic such as `homeassistant/syncerate/status` so it also does not inherit the meaning of an older retained legacy topic.

Successful JSON example:

```json
{
  "status": "success",
  "success": true,
  "title": "Main ZFS backup",
  "name": "Main ZFS backup",
  "job": "syncerate",
  "exit_code": 0,
  "error": "",
  "stderr": "",
  "warning": false,
  "skipped_datasets": [],
  "failed_datasets": []
}
```

Failure JSON example for a missing ZFS dataset:

```json
{
  "status": "failure",
  "success": false,
  "title": "Main ZFS backup",
  "name": "Main ZFS backup",
  "job": "syncerate",
  "exit_code": 8,
  "error": "1 dataset pair(s) failed because a ZFS dataset or pool was missing.",
  "stderr": "- Storage/Missing -> Backup/Missing\n  cannot open 'Storage/Missing': dataset does not exist",
  "warning": false,
  "skipped_datasets": [],
  "failed_datasets": [
    {
      "source": "Storage/Missing",
      "destination": "Backup/Missing",
      "reason": "cannot open 'Storage/Missing': dataset does not exist"
    }
  ]
}
```

`title` comes from `BackupTitle`; `name` carries the same value as a compatibility alias. The configured `SyncoidCommand` is deliberately excluded from JSON so SSH endpoints, key paths, and command options are not exposed through the status event.

The `stderr` field is bounded to the last 4000 characters of relevant captured child/Syncoid output. A Broken Pipe warning-success remains `status: success` and sets `warning: true` with affected source/destination pairs in `skipped_datasets`. A missing dataset/pool run is a real failure with exit code `8`; after Syncerate finishes the remaining configured pairs, the JSON failure event includes each affected source/destination pair and the matched ZFS/Syncoid text in `failed_datasets`.

Failure JSON is best-effort and never replaces the original Syncerate exit code. `SendMQTTOnSuccess = No` does not affect this path. If MQTT itself is the failing component, Syncerate does not recursively try to report that MQTT failure over MQTT. Errors before configuration is loaded cannot be published.

For a broker without username authentication, leave both credential fields empty:

```ini
mqtt_username =
mqtt_password =
```

A matching automation with explicit **success**, **failure**, and default **unknown** branches is supplied in:

```text
config/HomeAssistant-Automation-For-MQTT-JSON.yaml
```

The automation example listens to `homeassistant/syncerate/status`. When using `Use_MQTT` without JSON status, change its trigger topic to your derived error topic, such as `syncerate/result/error`; that subscription receives failures only.

## Successful-run system action

Disable the action:

```ini
SystemAction = No
```

Examples:

```ini
SystemAction = shutdown -P now
SystemAction = reboot
SystemAction = /path/to/trusted-script.sh
```

The command is executed through a shell only after all dataset transfers succeed, configured success MQTT publishing has completed when `SendMQTTOnSuccess` allows it, and configured success email has been attempted when `SendMailOnSuccess` allows it. Configure only trusted commands. A system-action exception or non-zero shell return code is logged explicitly, but it remains a best-effort post-run action and does not change an otherwise successful Syncerate exit code.

When email and a system action are both enabled, Syncerate waits two minutes before executing the action so the local mail command has time to finish before a shutdown or reboot.

## Safe first test

Create a small source dataset and file:

```bash
sudo zfs create Storage/Syncerate-Test
sudo touch /Storage/Syncerate-Test/testfile
```

Use this source-list entry:

```text
Storage/Syncerate-Test
```

Use a destination entry with the same final dataset name:

```text
BackUp/Syncerate-Test
```

Use a local test command:

```ini
SyncoidCommand = syncoid SourceDataSet DestDataSet
```

Run Syncerate:

```bash
./Syncerate.py --conf ./config/Syncerate.cfg
```

Verify the destination and snapshots:

```bash
sudo zfs list
sudo zfs list -t snapshot
```

## Runtime safety behavior

Syncerate keeps these checks for non-warning output and process results:

- source/destination list validation before replication;
- SSH host-key and password/passphrase prompt handling, including the repeated-prompt limit;
- authentication/permission failures, connection timeouts, and connection refusals;
- missing dataset/pool errors, including `cannot open '...': dataset does not exist`, `cannot open '...': no such pool`, and `cannot import '...': no such pool available`, optionally prefixed by `CRITICAL ERROR:`;
- stale interrupted-receive recovery and configured Broken Pipe retry handling;
- the actual Syncoid exit code and terminating signal.

When SSH presents its standard first-connection host-key confirmation prompt, Syncerate automatically answers `yes`. The following known-hosts warning is ignored under the general warning policy. For important systems, populate `known_hosts` ahead of time or enforce the desired `StrictHostKeyChecking` policy through SSH/Syncoid configuration.

Recognized **non-warning** missing dataset/pool errors retain the continue-but-fail behavior. If Syncoid finishes that pair with exit `0` or `2`, Syncerate records it as failed and processes the remaining pairs. The overall result is exit code `8`, with configured error notifications and no successful-run system action. Any other non-zero exit fails immediately with Syncoid's actual code.

A `WARNING: Skipping dataset ...` line alone is ignored and is not recorded as a missing-data failure. If Syncoid then exits non-zero, that exit still fails the run. This distinction also applies when warning text contains error-like phrases.

Normal repeated transfer progress and ignored warnings do not trigger the interactive-prompt repetition guard. `ContinueWithoutResume = False` is the only policy that turns a recognized Syncoid warning into a failure.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | The dataset list completed and no fatal handled error was returned. This also includes runs where one or more datasets were skipped after exhausting their per-dataset Broken Pipe retries while `RetryBrokenPipe` was enabled. Mail-command and system-action failures are currently logged rather than changing this code. |
| `1` | Source/destination list validation failed. |
| `2` | Syncerate encountered a script or configuration error. |
| `4` | Syncoid reported unavailable resume support while `ContinueWithoutResume = False`. Other warning lines do not cause this exit. |
| `5` | Password, authentication, or permission failure. |
| `6` | Connection timed out. |
| `7` | Connection was refused. |
| `8` | One or more configured pairs encountered a missing ZFS dataset or pool. Syncerate continues the remaining list for the recognized missing-data cases, then reports the completed run as failed with code `8`. |
| `9` | The same monitored output pattern repeated too many times. |
| `10` | MQTT dependency or publishing failure. |
| `11` | Reserved for system-action failures; the current system-action runner logs failures without returning this code. |

Non-zero Syncoid exit codes not handled by a specific rule are returned unchanged and may overlap the application codes above. Signal termination is reported as `128 + signal number`.
