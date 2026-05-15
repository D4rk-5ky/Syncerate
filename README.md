# Syncerate

Syncerate is a Python 3 wrapper script for [Syncoid](https://github.com/jimsalterjrs/sanoid), from the [Sanoid](https://github.com/jimsalterjrs/sanoid) project.

It lets you run Syncoid against many ZFS datasets by using two simple text files:

- one source dataset list
- one destination dataset list

The script reads both lists line by line and runs one Syncoid command for each source/destination pair.

It can also optionally:

- write log files
- send mail on success or failure
- publish MQTT messages
- publish a Home Assistant MQTT availability topic
- run a system command after a successful run
- pass extra Syncoid arguments per destination dataset

---

## Disclaimer

Use this at your own risk.

This script runs ZFS/Syncoid commands and may affect your datasets, snapshots, or backup targets.  
Always test with non-critical datasets first.

I am not responsible for data loss, damaged pools, deleted snapshots, broken backups, or anything else that happens while using this script.

---

## Why I made this

A friend and I started using ZFS around 2020 on Raspberry Pis and homemade servers built from older hardware.

We quickly found [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid), which is a great tool for handling ZFS snapshots and replication.

Syncoid worked well, but we wanted an easy way to transfer many datasets in sequence without manually writing the same command over and over again.

That idea became Syncerate.

This is my first open source GitHub project.  
I am not a professional programmer, and this has been a learning project for me.

The script currently works for our own use case, but I would be happy if others fork it, improve it, or use parts of it for their own setup.

---

## Features

Syncerate can:

1. Iterate through a list of source ZFS datasets.
2. Iterate through a matching list of destination ZFS datasets.
3. Run Syncoid once for each source/destination pair.
4. Check that the number of source and destination entries match.
5. Check that the final dataset names match.
6. Support dataset names with spaces.
7. Add extra Syncoid arguments per destination line.
8. Write `.log`, `.err`, and `.out` files.
9. Send mail on success or error.
10. Send MQTT messages.
11. Send Home Assistant MQTT availability messages.
12. Run a system action after successful completion.

---

## Requirements

You need:

- Python 3
- ZFS
- Syncoid / Sanoid
- SSH access between source and destination systems
- `pexpect`
- `paho-mqtt`, if MQTT is enabled
- `mail`, if mail notifications are enabled

Example package installation on Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-pexpect python3-paho-mqtt sanoid mailutils
```

Depending on your distro, the package names may be different.

---

## Installation

Clone the repository:

```bash
cd /your/script/location
git clone https://github.com/D4rk-5ky/Syncerate Syncerate
cd Syncerate
```

Make the script executable:

```bash
chmod +x Syncerate.py
```

---

## Basic usage

Run the script with a config file:

```bash
./Syncerate.py -c ./config/Syncerate.cfg
```

or:

```bash
python3 Syncerate.py -c ./config/Syncerate.cfg
```

---

## How Syncerate works

Syncerate uses three main files:

```text
Syncerate.py
Syncerate.cfg
source-list.txt
destination-list.txt
```

The source list and destination list must have the same number of lines.

Example:

```text
source-list.txt line 1       -> destination-list.txt line 1
source-list.txt line 2       -> destination-list.txt line 2
source-list.txt line 3       -> destination-list.txt line 3
```

For every matching pair, Syncerate builds and runs a Syncoid command.

---

## Source list

The source list contains the datasets you want to send or pull from.

Example:

```text
Storage/Archivy
Storage/DataSet With Spaces
Storage/Grafana
Storage/HedgeDoc
Storage/Heimdall
Storage/Home-Assistant
Storage/Joplin
Storage/Kavita
Storage/Media
Storage/Mosquitto
Storage/NextCloud
Storage/Podcasts
Storage/Portainer
Storage/SyncThing
Storage/Vikunja
Storage/WallaBag
Storage/WatchTower
```

You can create a list from existing datasets with:

```bash
zfs list -o name
```

Then copy the wanted dataset names into your source list file.

Blank lines and lines starting with `#` are ignored.

Example:

```text
# Docker services
Storage/Grafana
Storage/Home-Assistant

# Media
Storage/Media
```

---

## Destination list

The destination list contains where each source dataset should be replicated to.

Example:

```text
BackUp/Docker-Syncerate-Test/Archivy
BackUp/Docker-Syncerate-Test/DataSet With Spaces
BackUp/Docker-Syncerate-Test/Grafana
BackUp/Docker-Syncerate-Test/HedgeDoc
BackUp/Docker-Syncerate-Test/Heimdall
BackUp/Docker-Syncerate-Test/Home-Assistant
BackUp/Docker-Syncerate-Test/Joplin
BackUp/Docker-Syncerate-Test/Kavita
BackUp/Docker-Syncerate-Test/Media
BackUp/Docker-Syncerate-Test/Mosquitto
BackUp/Docker-Syncerate-Test/NextCloud
BackUp/Docker-Syncerate-Test/Podcasts
BackUp/Docker-Syncerate-Test/Portainer
BackUp/Docker-Syncerate-Test/SyncThing
BackUp/Docker-Syncerate-Test/Vikunja
BackUp/Docker-Syncerate-Test/WallaBag
BackUp/Docker-Syncerate-Test/WatchTower
```

Before running Syncerate, create the parent dataset on the receiving side.

Example:

```bash
zfs create BackUp/Docker-Syncerate-Test
```

Syncoid can create the final child dataset, but the parent path should already exist.

---

## Dataset name safety check

Syncerate checks that the final part of each source and destination dataset name matches.

Example accepted pair:

```text
Source:
Storage/Home-Assistant

Destination:
BackUp/Docker-Syncerate-Test/Home-Assistant
```

Both end with:

```text
Home-Assistant
```

Example rejected pair:

```text
Source:
Storage/Home-Assistant

Destination:
BackUp/Docker-Syncerate-Test/Grafana
```

These do not match, so Syncerate stops with an error.

This helps avoid accidentally sending a dataset to the wrong destination.

---

# Per-destination extra arguments

Syncerate supports adding extra Syncoid arguments to individual lines in the destination list.

This is useful when only some destination datasets need special receive options.

For example, you may want one destination dataset to be created with:

```text
recordsize=1M
compression=zstd-9
```

while other datasets use normal Syncoid behavior.

---

## Destination list syntax with extra arguments

The format is:

```text
DestinationDataset: extra syncoid arguments
```

Important:

```text
colon + space
```

Syncerate splits the destination line on:

```text
: 
```

That means a remote destination like this is still safe:

```text
root@10.0.0.2:BackUp/Docker/Home-Assistant
```

because it does not contain `colon + space`.

---

## Example destination list with extra arguments

```text
BackUp/Docker-Syncerate-Test/Archivy
BackUp/Docker-Syncerate-Test/DataSet With Spaces
BackUp/Docker-Syncerate-Test/Grafana
BackUp/Docker-Syncerate-Test/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
BackUp/Docker-Syncerate-Test/NextCloud: --recvoptions="o recordsize=1M o compression=zstd-9"
BackUp/Docker-Syncerate-Test/Portainer
```

In this example:

- `Archivy` uses the normal Syncoid command
- `DataSet With Spaces` uses the normal Syncoid command
- `Grafana` uses the normal Syncoid command
- `Media` gets extra receive options
- `NextCloud` gets extra receive options
- `Portainer` uses the normal Syncoid command

---

## Example generated command

If your config contains:

```ini
SyncoidCommand=syncoid SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation
```

And your source list contains:

```text
Storage/Media
```

And your destination list contains:

```text
BackUp/Docker-Syncerate-Test/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
```

Syncerate will run something like:

```bash
syncoid Storage/Media BackUp/Docker-Syncerate-Test/Media --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation --recvoptions="o recordsize=1M o compression=zstd-9"
```

---

## Important note about `--recvoptions`

`--recvoptions` are only used by Syncoid when the destination dataset is created during receive.

If the destination dataset already exists, changing `recordsize` or `compression` this way may not change existing dataset properties.

To set properties manually on an existing destination dataset, use ZFS directly.

Example:

```bash
zfs set recordsize=1M BackUp/Docker-Syncerate-Test/Media
zfs set compression=zstd-9 BackUp/Docker-Syncerate-Test/Media
```

Future writes to that dataset will then use the new properties.

Existing blocks are not automatically rewritten.

---

## Repeated transfers after setting properties

If a destination dataset has already been created with:

```bash
recordsize=1M
compression=zstd-9
```

then later Syncoid runs do not need to repeat the same `--recvoptions`.

The dataset keeps its ZFS properties until you change them.

So this is valid:

First run:

```text
BackUp/Docker-Syncerate-Test/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
```

Later runs:

```text
BackUp/Docker-Syncerate-Test/Media
```

The destination dataset keeps its existing ZFS properties.

---

## Config file

The config file controls the script behavior.

Example:

```ini
[Syncerate Config]

SourceListPath=/path/to/source-list.txt
DestListPath=/path/to/destination-list.txt

SyncoidCommand=syncoid SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation

PassWord=No

DateTime=%Y-%m-%d_%H-%M-%S
LogDestination=/var/log/syncerate

Mail=No
SystemAction=No

Use_MQTT=No
broker_address=10.0.0.10
broker_port=1883
mqtt_username=
mqtt_password=
mqtt_topic=home-assistant/syncerate/command
mqtt_message=ON

Use_HomeAssistant=No
HomeAssistant_Available=home-assistant/syncerate/available

EscapeSpacesForSyncoid=False
```

---

## Config options

| Option                    | Required                                   | Description                                                           |
| ------------------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| `SourceListPath`          | Yes                                        | Path to the source dataset list                                       |
| `DestListPath`            | Yes                                        | Path to the destination dataset list                                  |
| `SyncoidCommand`          | Yes                                        | Syncoid command template containing `SourceDataSet` and `DestDataSet` |
| `PassWord`                | Optional                                   | `No`, `Ask`, or a password/passphrase                                 |
| `DateTime`                | Yes                                        | Date/time format used for log filenames                               |
| `LogDestination`          | Optional                                   | Log folder path, or `No` to disable file logging                      |
| `Mail`                    | Optional                                   | Recipient email address, or `No`                                      |
| `SystemAction`            | Optional                                   | Command to run after successful completion, or `No`                   |
| `Use_MQTT`                | Optional                                   | `Yes` or `No`                                                         |
| `broker_address`          | Required if MQTT is enabled                | MQTT broker hostname or IP                                            |
| `broker_port`             | Required if MQTT is enabled                | MQTT broker port                                                      |
| `mqtt_username`           | Optional                                   | MQTT username                                                         |
| `mqtt_password`           | Optional                                   | MQTT password                                                         |
| `mqtt_topic`              | Required if MQTT is enabled                | MQTT topic to publish to                                              |
| `mqtt_message`            | Required if MQTT is enabled                | MQTT message payload                                                  |
| `Use_HomeAssistant`       | Optional                                   | `Yes` or `No`                                                         |
| `HomeAssistant_Available` | Required if Home Assistant MQTT is enabled | MQTT availability topic                                               |


---

## Syncoid command template

The Syncoid command must contain these two placeholders:

```text
SourceDataSet
DestDataSet
```

Syncerate replaces them with the current source and destination dataset from the list files.

Example pull command:

```ini
SyncoidCommand=syncoid username@10.0.0.50:SourceDataSet DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation
```

Example push command:

```ini
SyncoidCommand=syncoid SourceDataSet username@10.0.0.60:DestDataSet --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation
```

Do not rename these placeholders:

```text
SourceDataSet
DestDataSet
```

They are required by the script.

---

## Password / passphrase handling

The `PassWord` option supports three modes.

No password:

```ini
PassWord=No
```

Ask in terminal:

```ini
PassWord=Ask
```

Store password in config:

```ini
PassWord=your-password-here
```

Using `Ask` is safer than storing the password in the config file.

The password is not written to the log files.

---

## Logging

Enable logging by setting:

```ini
LogDestination=/path/to/log/folder
```

Disable file logging with:

```ini
LogDestination=No
```

When logging is enabled, Syncerate can create:

```text
Syncerate-YYYY-MM-DD_HH-MM-SS.log
Syncerate-YYYY-MM-DD_HH-MM-SS.err
Syncerate-YYYY-MM-DD_HH-MM-SS.out
```

File meaning:

| File | Description |
| --- | --- |
| `.log` | Main script log |
| `.err` | Error-only log |
| `.out` | Syncoid output |

---

## Mail notifications

To disable mail:

```ini
Mail=No
```

To enable mail:

```ini
Mail=you@example.com
```

This requires a working local mail setup, such as Postfix and the `mail` command.

Example packages on Debian/Ubuntu:

```bash
sudo apt install postfix mailutils
```

Mail can be sent on:

- successful run
- Syncoid error
- script error
- MQTT error

If logging is enabled, logs are attached to the mail.

---

## MQTT

To disable MQTT:

```ini
Use_MQTT=No
```

To enable MQTT:

```ini
Use_MQTT=Yes
broker_address=10.0.0.10
broker_port=1883
mqtt_username=myuser
mqtt_password=mypassword
mqtt_topic=home-assistant/syncerate/command
mqtt_message=ON
```

Syncerate publishes the configured message to the configured topic after a successful run.

---

## Home Assistant MQTT availability

If you use Home Assistant MQTT availability, enable:

```ini
Use_HomeAssistant=Yes
HomeAssistant_Available=home-assistant/syncerate/available
```

Syncerate will publish:

```text
online
```

to the availability topic.

Example Home Assistant MQTT binary sensor:

```yaml
mqtt:
  binary_sensor:
    - name: "Syncerate"
      state_topic: "home-assistant/syncerate/command"
      payload_on: "ON"
      availability:
        - topic: "home-assistant/syncerate/available"
          payload_available: "online"
          payload_not_available: "offline"
      qos: 0
```

Note:

If you use retained MQTT messages, remember to reset the Home Assistant entity or automation state after it has triggered, otherwise automations may repeat unexpectedly.

---

## System action after successful run

To disable:

```ini
SystemAction=No
```

To shut down after a successful run:

```ini
SystemAction=shutdown -P now
```

To reboot:

```ini
SystemAction=reboot
```

To run your own script:

```ini
SystemAction=/path/to/my-script.sh
```

The system action only runs after a successful Syncerate run.

If a Syncoid or script error happens, the system action is not executed.

---

## Dataset names with spaces

Syncerate supports dataset names with spaces.

Example:

```text
Storage/DataSet With Spaces
```

The script builds the Syncoid command as an argument list instead of one large shell string.

This helps keep dataset names with spaces as one argument.

```

---

## Example source and destination pair

Source list:

```text
Storage/Home-Assistant
Storage/Media
Storage/NextCloud
```

Destination list:

```text
BackUp/Docker-Syncerate-Test/Home-Assistant
BackUp/Docker-Syncerate-Test/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
BackUp/Docker-Syncerate-Test/NextCloud: --recvoptions="o recordsize=1M o compression=zstd-9"
```

Generated commands will be similar to:

```bash
syncoid Storage/Home-Assistant BackUp/Docker-Syncerate-Test/Home-Assistant --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation
```

```bash
syncoid Storage/Media BackUp/Docker-Syncerate-Test/Media --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation --recvoptions="o recordsize=1M o compression=zstd-9"
```

```bash
syncoid Storage/NextCloud BackUp/Docker-Syncerate-Test/NextCloud --compress none --sshcipher chacha20-poly1305@openssh.com --sshport 22 --sshkey /root/.ssh/mykey --no-privilege-elevation --recvoptions="o recordsize=1M o compression=zstd-9"
```

---

## Testing safely

Before using Syncerate on important data, test with a small dataset.

Example:

```bash
zfs create Storage/Syncerate-Test
touch /Storage/Syncerate-Test/testfile
```

Add it to your source list:

```text
Storage/Syncerate-Test
```

Add a matching destination:

```text
BackUp/Syncerate-Test
```

Run Syncerate:

```bash
./Syncerate.py -c ./config/Syncerate.cfg
```

Then verify the destination:

```bash
zfs list
zfs list -t snapshot
```

---

## Exit codes

Syncerate uses different exit codes for different error types.

| Exit code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Source/destination list error |
| `2` | Script error |
| `4` | Warning detected |
| `5` | Password denied / permission denied |
| `6` | Connection timeout |
| `7` | Connection refused |
| `8` | Dataset missing or skipped |
| `9` | Repeated pattern detected |
| `10` | MQTT error |
| `11` | System action error |

---

## Common mistakes

### Wrong number of source and destination lines

The source and destination lists must have the same number of active lines.

Blank lines and lines starting with `#` are ignored.

---

### Final dataset names do not match

This will fail:

```text
Source:
Storage/Home-Assistant

Destination:
BackUp/Docker-Syncerate-Test/Grafana
```

This will work:

```text
Source:
Storage/Home-Assistant

Destination:
BackUp/Docker-Syncerate-Test/Home-Assistant
```

---

### Wrong placeholder names

Use exactly:

```text
SourceDataSet
DestDataSet
```

Do not use:

```text
SourceDataset
DestinationDataSet
Source
Destination
```

---

### Wrong destination extra argument separator

Correct:

```text
BackUp/Media: --recvoptions="o recordsize=1M o compression=zstd-9"
```

Wrong:

```text
BackUp/Media:--recvoptions="o recordsize=1M o compression=zstd-9"
```

The separator must be:

```text
: 
```

That means colon followed by a space.

---

## Contributing

If you want to improve Syncerate, please fork the repository and make a pull request.

The project branch intended for future work is:

```text
Syncerate-Next
```

Ideas for improvement are welcome.

---

## Credits

Thanks to:

- [Jim Salter](https://github.com/jimsalterjrs)
- [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid)
- [2.5 Admins](https://2.5admins.com/)
- [Late Night Linux Family](https://latenightlinux.com/)

---

## Author

Made by Darkyere & Skynet.