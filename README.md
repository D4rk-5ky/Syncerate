# Syncerate

Syncerate processes each matching source and destination ZFS dataset pair listed in two text files. Dataset pairs run sequentially, and optional retry handling can repeat an individual pair when a Broken Pipe occurs.

Current version: `0.4.13`

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

- Python `paho-mqtt` when MQTT publishing is enabled
- a configured local `mail` command when email is enabled
- Home Assistant when using the supplied MQTT availability example

On Debian or Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-pexpect sanoid
```

Install MQTT support only when needed:

```bash
sudo apt install python3-paho-mqtt
```

Install local mail support only when needed:

```bash
sudo apt install postfix mailutils
```

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

| Option | Required | What it does |
| --- | --- | --- |
| `-c FILE`, `--conf FILE` | Yes | Loads the specified Syncerate configuration file. |
| `-h`, `--help` | No | Shows command usage and exits. |
| `--version` | No | Shows the installed Syncerate version and exits. |

Run Syncerate with the long option:

```bash
./Syncerate.py --conf ./config/Syncerate.cfg
```

Or with the short option:

```bash
./Syncerate.py -c ./config/Syncerate.cfg
```

## Source dataset list

Put one source dataset on each active line:

```text
Storage/Home-Assistant
Storage/Media
Storage/DataSet With Spaces
```

Blank lines and lines beginning with `#` are ignored.

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

Remote destinations remain supported because Syncerate splits on the final colon-space sequence:

```text
backupuser@192.0.2.20:BackUp/Media: --recvoptions="o compression=zstd"
```

The text after the separator is parsed as command arguments and appended to the Syncoid command for that dataset pair only.

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

SourceListPath = /absolute/path/to/source-list
DestListPath = /absolute/path/to/destination-list

SyncoidCommand = syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --compress none --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation

PassWord = No
Mail = No
DateTime = %Y-%m-%d_%H_%M_%S
LogDestination = No
SystemAction = No

RetryBrokenPipe = No
BrokenPipeRetryCount = 1
BrokenPipeRetryWaitSeconds = 10

Use_MQTT = No
broker_address = mqtt.example.com
broker_port = 1883
mqtt_username =
mqtt_password =
mqtt_topic = home-assistant/syncerate/command
mqtt_message = ON

Use_HomeAssistant = No
HomeAssistant_Available = home-assistant/syncerate/available
```

## Configuration options

| Option | Required | Accepted value or purpose |
| --- | --- | --- |
| `BackupTitle` | No | Optional short name included in logs and email content. |
| `BackupComment` | No | Optional description included in logs and email content. |
| `SourceListPath` | Yes | Path to the source dataset list. Relative paths are resolved from the current working directory. |
| `DestListPath` | Yes | Path to the destination dataset list. Relative paths are resolved from the current working directory. |
| `SyncoidCommand` | Yes | Syncoid command template containing the exact placeholders `SourceDataSet` and `DestDataSet`. |
| `PassWord` | Yes | `No`, `Ask`, or a literal SSH password/key passphrase. |
| `Mail` | Yes | Recipient address, or `No` to disable email. |
| `DateTime` | Yes | Python `strftime` pattern used in log filenames. |
| `LogDestination` | Yes | Directory for `.log`, `.err`, and `.out` files, or `No` for terminal-only logging. |
| `SystemAction` | Yes | Trusted shell command executed after a successful run, or `No` to disable it. |
| `RetryBrokenPipe` | No | Enables dataset-level Broken Pipe retry handling. Each dataset receives its own retry allowance. When that allowance is exhausted, only that dataset is skipped, the remaining list continues, and the completed run records a successful warning. Missing or disabled values preserve normal Syncoid failure handling. |
| `BrokenPipeRetryCount` | No | Number of retries allowed for each individual dataset after its initial attempt. Defaults to `1` when omitted. The count resets for every dataset pair. Use `0` to skip an affected dataset immediately after its first Broken Pipe. Negative values and non-integers are rejected. |
| `BrokenPipeRetryWaitSeconds` | No | Whole number of seconds to wait before each Broken Pipe retry. Defaults to `10` when omitted. Use `0` to retry immediately. Negative values and non-integers are rejected as configuration errors. |
| `Use_MQTT` | No | Enables MQTT with `Yes`, `True`, `1`, or `On`. Missing, `No`, `False`, `0`, or `Off` disables it. |
| `broker_address` | When MQTT is enabled | MQTT broker hostname or IP address. |
| `broker_port` | When MQTT is enabled | MQTT broker TCP port as an integer, commonly `1883`. |
| `mqtt_username` | No | MQTT username. Leave empty when authentication is not used. |
| `mqtt_password` | No | MQTT password. Leave empty when authentication is not used. |
| `mqtt_topic` | When MQTT is enabled | Topic that receives the success payload. |
| `mqtt_message` | When MQTT is enabled | Payload published after all transfers succeed. |
| `Use_HomeAssistant` | No | Enables the optional HA availability message with `Yes`, `True`, `1`, or `On`. It is checked only when MQTT is enabled. |
| `HomeAssistant_Available` | When MQTT and HA are enabled | Topic that receives retained payload `online`. |

Although some integrations are disabled with `No`, the required keys should remain in the configuration so startup validation succeeds.

## Syncoid command templates

The template must contain these case-sensitive placeholders:

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

Do not answer password or key-passphrase prompts:

```ini
PassWord = No
```

Use this when SSH keys are unencrypted or authentication is already handled without an interactive prompt. If a prompt appears while this is set to `No`, Syncerate stops with an authentication error instead of waiting indefinitely.

Prompt once when Syncerate starts:

```ini
PassWord = Ask
```

Store a literal value in the configuration:

```ini
PassWord = your-secret
```

`Ask` avoids storing the secret in the file. Password and MQTT credential values are omitted from normal configuration logging.

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

## Email notifications

Disable email:

```ini
Mail = No
```

Enable email:

```ini
Mail = user@example.com
```

A working local `mail` command is required. Syncerate can send success, warning-success, Syncoid-error, script-error, and MQTT-error messages. Log files are attached when file logging is enabled and the relevant files are available.

When `RetryBrokenPipe` is enabled and a dataset is skipped after exhausting its configured retry count, the run still returns success when no other failure occurs. The success email subject is exactly:

```text
Syncerate Succsful - WARNING BROKEN PIPE
```

The email body lists the skipped source and destination dataset pairs.

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

When enabled, Syncerate watches Syncoid output case-insensitively for the text `Broken pipe` and applies this policy independently to every dataset pair:

1. Broken Pipe stops only the current Syncoid attempt.
2. If that dataset still has retries available, Syncerate waits for `BrokenPipeRetryWaitSeconds` and retries the same dataset with the same command.
3. If Broken Pipe continues after all `BrokenPipeRetryCount` retries are used, Syncerate skips only that dataset and continues with the next source/destination pair.
4. The next dataset starts with a fresh retry counter and receives its full configured retry allowance.
5. After the remaining list finishes, Syncerate returns exit code `0` when no other fatal error occurred.
6. Logs and the success email identify every dataset pair skipped after exhausting its retries.

The retry count is never shared between datasets. This option does not retry authentication failures, missing datasets, generic warnings, connection failures, or other nonzero Syncoid exits. When the option is disabled or omitted, Broken Pipe is not given special retry handling; Syncerate waits for Syncoid's real exit status and applies the normal failure behavior.

## MQTT success notification

Disable MQTT:

```ini
Use_MQTT = No
```

When disabled, `paho-mqtt` is not imported and MQTT or Home Assistant settings are not used by the publisher.

Enable MQTT:

```ini
Use_MQTT = Yes
broker_address = 192.0.2.30
broker_port = 1883
mqtt_username = syncerate
mqtt_password = secret
mqtt_topic = home-assistant/syncerate/command
mqtt_message = ON
```

After every dataset transfer succeeds, Syncerate publishes the configured retained message. If MQTT is enabled and `paho-mqtt` is unavailable or publishing fails, Syncerate returns exit code `10`.

For a broker without username authentication, leave both credential fields empty:

```ini
mqtt_username =
mqtt_password =
```

## Home Assistant availability message

Home Assistant publishing requires MQTT to be enabled.

Disable it:

```ini
Use_HomeAssistant = No
```

Enable it:

```ini
Use_MQTT = Yes
Use_HomeAssistant = Yes
HomeAssistant_Available = home-assistant/syncerate/available
```

Syncerate first publishes retained payload `online` to `HomeAssistant_Available`, then publishes the normal MQTT success message.

A matching example entity configuration is supplied in:

```text
config/HomeAssistant-Configuration-For-MQTT.yaml
```

The PNG files in `config/` are optional Home Assistant setup references and are not loaded by Syncerate.

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

The command is executed through a shell only after all dataset transfers succeed, MQTT publishing succeeds when enabled, and email sending has been attempted when enabled. Configure only trusted commands.

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

Syncerate monitors Syncoid and SSH output for:

- first-time SSH host-key confirmation;
- password and key-passphrase prompts;
- authentication or permission failure;
- connection timeout;
- connection refusal;
- skipped datasets;
- an unusable interrupted-transfer resume state, followed by one retry using `--no-resume`;
- unavailable ZFS resume support where Syncoid continues without it;
- repeated matched prompts or messages;
- optional per-dataset retries, up to `BrokenPipeRetryCount`, after the configured `BrokenPipeRetryWaitSeconds`, when `Broken pipe` appears;
- retry exhaustion that skips only the affected dataset, resets the counter, and continues the list;
- generic warnings;
- the recognized missing destroy-snapshot condition.

Generic warnings remain fatal. The exact unavailable-resume message is logged while Syncerate waits for Syncoid's real final status because the transfer continues without resumable receive support. Broken Pipe retry behavior is used only when `RetryBrokenPipe` is enabled.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | The dataset list completed and no fatal handled error was returned. This also includes runs where one or more datasets were skipped after exhausting their per-dataset Broken Pipe retries while `RetryBrokenPipe` was enabled. Mail-command and system-action failures are currently logged rather than changing this code. |
| `1` | Source/destination list validation failed. |
| `2` | Syncerate encountered a script or configuration error. |
| `4` | A fatal Syncoid warning was detected. |
| `5` | Password, authentication, or permission failure. |
| `6` | Connection timed out. |
| `7` | Connection was refused. |
| `8` | Syncoid skipped or could not find a dataset. |
| `9` | The same monitored output pattern repeated too many times. |
| `10` | MQTT dependency or publishing failure. |
| `11` | Reserved for system-action failures; the current system-action runner logs failures without returning this code. |
