# Syncerate

Syncerate runs one Syncoid command for each paired source and destination ZFS dataset in two list files.

Current version: `0.4.2`

## Requirements

Required:

- Python 3
- ZFS
- Sanoid/Syncoid
- Python `pexpect`
- SSH access when either side is remote

Optional:

- Python `paho-mqtt` only when MQTT is enabled
- a configured local `mail` command only when email is enabled
- Home Assistant only when using the optional MQTT availability integration

On Debian or Ubuntu, install the required packages:

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

## Project files

```text
Syncerate.py
README.md
VERSIONING.md
commented_code_map.md
config/example-Syncerate.cfg
config/example-source-file
config/example-dest-file
config/HomeAssistant-Configuration-For-MQTT.yaml
```

The Home Assistant YAML and screenshots are optional reference files. Syncerate itself does not load them.

## Prepare the script

Make it executable:

```bash
chmod +x Syncerate.py
```

Show help:

```bash
./Syncerate.py --help
```

Show the installed version:

```bash
./Syncerate.py --version
```

## Create the source list

Create one source dataset per active line:

```text
Storage/Home-Assistant
Storage/Media
Storage/DataSet With Spaces
```

Blank lines and lines beginning with `#` are ignored.

Do not manually escape spaces:

```text
Storage/DataSet With Spaces
```

## Create the destination list

Create one destination dataset for each source-line position:

```text
BackUp/Home-Assistant
BackUp/Media
BackUp/DataSet With Spaces
```

Line pairing is positional:

```text
source line 1 -> destination line 1
source line 2 -> destination line 2
source line 3 -> destination line 3
```

The two lists must contain the same number of active lines. The final dataset name in each pair must also match.

Valid pair:

```text
Storage/Home-Assistant
BackUp/Home-Assistant
```

Invalid pair:

```text
Storage/Home-Assistant
BackUp/Grafana
```

## Per-destination Syncoid arguments

A destination line can append extra Syncoid arguments after a colon followed by one space:

```text
BackUp/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
```

The required separator is:

```text
: 
```

Remote destination syntax remains supported because Syncerate splits only on the final colon-space sequence:

```text
root@192.0.2.20:BackUp/Media: --recvoptions="o compression=zstd"
```

## Create the configuration

Copy the supplied example:

```bash
cp config/example-Syncerate.cfg config/Syncerate.cfg
```

Edit `config/Syncerate.cfg`:

```ini
[Syncerate Config]

BackupTitle = Main ZFS backup
BackupComment = Replicate selected datasets to the backup pool

SourceListPath = /absolute/path/to/source-list
DestListPath = /absolute/path/to/destination-list

SyncoidCommand = syncoid username@192.0.2.10:SourceDataSet DestDataSet --compress none --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation

PassWord = No
Mail = No
DateTime = %Y-%m-%d_%H_%M_%S
LogDestination = No
SystemAction = No

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

| Option | Required | Purpose |
| --- | --- | --- |
| `BackupTitle` | No | Short job name written to logs and email bodies |
| `BackupComment` | No | Longer job description written to logs and email bodies |
| `SourceListPath` | Yes | Absolute or relative path to the source dataset list |
| `DestListPath` | Yes | Absolute or relative path to the destination dataset list |
| `SyncoidCommand` | Yes | Syncoid template containing `SourceDataSet` and `DestDataSet` |
| `PassWord` | No | `No`, `Ask`, or a literal password/passphrase |
| `Mail` | No | Recipient address, or `No` to disable email |
| `DateTime` | Yes | Python `strftime` format for log filenames |
| `LogDestination` | No | Log directory, or `No` for terminal-only output |
| `SystemAction` | No | Trusted shell command after success, or `No` |
| `Use_MQTT` | No | Enables optional MQTT success publishing |
| `broker_address` | With MQTT | MQTT broker hostname or address |
| `broker_port` | With MQTT | MQTT broker TCP port |
| `mqtt_username` | No | Optional MQTT username |
| `mqtt_password` | No | Optional MQTT password |
| `mqtt_topic` | With MQTT | Topic for the configured success payload |
| `mqtt_message` | With MQTT | Success payload |
| `Use_HomeAssistant` | No | Enables optional retained availability publishing |
| `HomeAssistant_Available` | With HA | Home Assistant availability topic |

## Syncoid command templates

Keep these placeholders exactly as written:

```text
SourceDataSet
DestDataSet
```

Local to local:

```ini
SyncoidCommand = syncoid SourceDataSet DestDataSet
```

Pull from a remote source:

```ini
SyncoidCommand = syncoid username@192.0.2.10:SourceDataSet DestDataSet --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation
```

Push to a remote destination:

```ini
SyncoidCommand = syncoid SourceDataSet username@192.0.2.20:DestDataSet --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation
```

Syncerate splits the template before replacing the placeholders, preserving dataset names containing spaces as single command arguments.

## Password and passphrase handling

Do not provide one:

```ini
PassWord = No
```

Prompt securely at startup:

```ini
PassWord = Ask
```

Use a literal configured value:

```ini
PassWord = your-secret
```

`Ask` is safer than storing a secret in the config. Password values are omitted from logs.

## Logging

Disable file logging:

```ini
LogDestination = No
```

Enable file logging:

```ini
LogDestination = /var/log/syncerate
```

Generated files can include:

```text
Syncerate-<timestamp>.log
Syncerate-<timestamp>.err
Syncerate-<timestamp>.out
```

- `.log`: main application messages.
- `.err`: ERROR-level messages only.
- `.out`: Syncoid process output.

## Email

Disable email:

```ini
Mail = No
```

Enable email:

```ini
Mail = user@example.com
```

Email requires a working local `mail` command. Syncerate can send successful-run, Syncoid-error, script-error, and MQTT-error notifications. Available logs are attached when file logging is enabled.

## MQTT

MQTT is disabled by default:

```ini
Use_MQTT = No
```

These values also disable it:

```text
False
0
Off
```

When MQTT is disabled:

- `paho-mqtt` is not imported;
- the package does not need to be installed;
- broker and topic values are not read by the MQTT publishing function;
- Home Assistant MQTT settings are not loaded.

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

These values also enable it:

```text
True
1
On
```

After all Syncoid jobs succeed, Syncerate publishes the configured retained message. When MQTT is enabled but `paho-mqtt` is not installed, Syncerate exits with code `10` and explains the missing optional dependency.

## Home Assistant MQTT availability

Home Assistant support is optional and disabled by default:

```ini
Use_HomeAssistant = No
```

The option may be omitted completely. It is read only when MQTT is enabled.

Enable availability publishing:

```ini
Use_MQTT = Yes
Use_HomeAssistant = Yes
HomeAssistant_Available = home-assistant/syncerate/available
```

Syncerate then publishes retained payload `online` to the availability topic before publishing the normal MQTT success payload.

An example binary sensor is supplied in:

```text
config/HomeAssistant-Configuration-For-MQTT.yaml
```

## Successful-run system action

Disable it:

```ini
SystemAction = No
```

Examples:

```ini
SystemAction = shutdown -P now
SystemAction = reboot
SystemAction = /path/to/trusted-script.sh
```

The command runs only after every dataset transfer succeeds. It is executed through a shell, so only configure trusted commands.

## Run Syncerate

Using the long option:

```bash
./Syncerate.py --conf ./config/Syncerate.cfg
```

Using the short option:

```bash
./Syncerate.py -c ./config/Syncerate.cfg
```

## Safe initial test

Create a small source dataset and test file:

```bash
sudo zfs create Storage/Syncerate-Test
sudo touch /Storage/Syncerate-Test/testfile
```

Use matching list entries:

```text
Storage/Syncerate-Test
```

```text
BackUp/Syncerate-Test
```

Run the job:

```bash
./Syncerate.py --conf ./config/Syncerate.cfg
```

Verify after the run:

```bash
sudo zfs list
sudo zfs list -t snapshot
```

## Handled Syncoid and SSH conditions

Syncerate watches for:

- first-time SSH host-key confirmation;
- password and passphrase prompts;
- permission denied;
- connection timeout;
- connection refused;
- skipped datasets;
- an unusable previous resume state, followed by one retry with `--no-resume`;
- repeated prompt patterns;
- general warnings;
- the specifically recognized nonfatal missing destroy-snapshot condition.

General Syncoid warnings remain fatal unless they match the explicitly handled nonfatal condition.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Success |
| `1` | Source/destination list validation error |
| `2` | Script error |
| `4` | Fatal warning detected |
| `5` | Password, authentication, or permission failure |
| `6` | Connection timeout |
| `7` | Connection refused |
| `8` | Dataset missing or skipped |
| `9` | Repeated matched pattern |
| `10` | MQTT dependency or publishing error |
| `11` | Reserved system-action error |
