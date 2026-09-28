# SnapBeforeWatchTower

SnapBeforeWatchTower creates ZFS snapshots for datasets listed in a text file, records Docker image digests during `create` runs, and removes old matching snapshots and log groups according to an age/count retention policy. Configuration is supplied through one TOML file.

The application does **not** start Watchtower, update containers, restore data, stop services, or create application-consistent snapshots.

## Requirements

- Linux with Python **3.11 or newer**. Python 3.11 is required because TOML is read with the standard-library `tomllib` module.
- ZFS tools available in `PATH` and permission to operate on the configured datasets.
- Root privileges for normal operation, including dry-run.
- Docker CLI/daemon for image-digest capture during a real `create` run. Docker is not invoked for `delete` or dry-run.
- Optional mail notifications require a local `mail` program that supports `-s` and `--attach`.
- Optional MQTT reporting requires `paho-mqtt` from `requirements-mqtt.txt`.

## Setup

Copy the example configuration and edit it:

```bash
cp config-example.toml config.toml
cp datasets.example.txt datasets
nano config.toml
nano datasets
```

`config.toml` is ignored by `.gitignore` because it can contain an MQTT password.

The supplied configuration example starts with `dry_run = true`, mail disabled, and MQTT disabled. The supplied `datasets.example.txt` is a harmless format example and should be copied/edited into the `dataset_file` named by your TOML. These defaults are intentional so a copied example does not immediately destroy snapshots or send notifications.

## Run command

The application has one public command-line option:

```bash
sudo python3 SnapBeforeWatchTower.py -c config.toml
```

`-c CONFIG` is required and points to the TOML configuration file. There are no separate command, dataset, retention, mail, MQTT, dry-run, help, or version flags; those operational settings are in TOML.

Relative paths in the TOML file are resolved relative to the TOML file itself. This makes cron/systemd execution independent of the shell's working directory.

## Configuration

The complete commented configuration is in `config-example.toml`. Every supported setting is shown there.

`config.example.md` is a supplemental human-readable reference for the same current TOML settings and the single `-c CONFIG` option; it is not loaded by the application.

### `[application]`

```toml
[application]
command = "create"
dataset_file = "datasets"
older_than = "7d"
retain_count = 10
dry_run = true
```

`command` must be `"create"` or `"delete"`. `create` captures Docker image digests, creates one managed snapshot per dataset, immediately applies snapshot retention to that dataset, and then cleans old log groups. `delete` only applies snapshot retention and log cleanup; it does not create snapshots or invoke Docker.

`dataset_file` points to the UTF-8 dataset-list file. Each non-empty line is treated as one complete ZFS dataset name. Blank lines are ignored. Dataset lines are not deduplicated and there is no comment syntax. A relative path is resolved relative to the TOML file. If ZFS reports that one configured dataset does not exist, that dataset is recorded as failed and the script continues with the remaining datasets; after normal remaining-dataset processing and log cleanup, the overall run still exits as failure.

`older_than` controls the age cutoff for managed snapshots and log groups. It must be a nonnegative integer followed by `d`, `w`, or `m`: for example `7d`, `2w`, or `1m`. Months are treated as 30 days. Deletion uses a strict older-than comparison.

`retain_count` protects at least that many newest matching snapshots per dataset and newest log timestamp groups. Zero or a negative value disables the count floor; the age cutoff still applies.

`dry_run = true` previews ZFS snapshot creation/destruction and old-log deletion. Dry-run still lists existing ZFS snapshots, creates run logs, and can send configured email. Docker digest collection is skipped. MQTT settings are validated when MQTT is enabled, but the final MQTT publish is suppressed so a preview cannot advance an automation.

### `[mail]` — optional

```toml
[mail]
enabled = false
recipient = "you@example.com"
on_success = false
```

When `enabled = false`, mail is disabled regardless of the other mail values.

When `enabled = true`, `recipient` must be non-empty. Failure mail is enabled. `on_success = true` additionally sends a success report; it does not disable failure mail. A run that encountered one or more missing ZFS datasets still sends failure mail after the remaining datasets have been processed; its subject and introductory text identify the missing-dataset reason. The report uses the newest `.log` and newest non-empty `.err` files and attaches them where available. Mail delivery failure is logged but does not reliably replace the snapshot job exit result.

### `[mqtt]` — optional

Install the optional dependency with the same Python interpreter used to run the application:

```bash
python3 -m pip install -r requirements-mqtt.txt
```

Configuration example:

```toml
[mqtt]
enabled = false
host = "mqtt.example.local"
port = 1883
topic = "homeassistant/SnapBeforeWatchTower/Zotac-RI531/status"
title = "Zotac RI531 - SnapBeforeWatchTower"
username = "your-mqtt-user"
password = "<String>"
qos = 0
tls = false
ca_file = ""
cert_file = ""
key_file = ""
timeout = 15
```

When `enabled = false`, MQTT reporting is disabled and `paho-mqtt` is not required. Unsupported MQTT keys are still rejected.

When `enabled = true`, `host` and `topic` are required non-empty strings. `topic` cannot contain `+` or `#`. `port` must be 1–65535, `qos` must be 0, 1, or 2, and `timeout` must be 1–120 seconds. Reports are always published with `retain = false`.

`username` and `password` are plain TOML strings. An empty string disables that optional value. A non-empty password requires a non-empty username. Because the password is stored directly in the TOML file, protect the operational config with restrictive filesystem permissions and do not commit or share it.

`tls = true` enables certificate and hostname verification. `ca_file` is optional; an empty string uses system trust. `cert_file` and `key_file` must either both be empty or both point to files. Relative certificate/key paths are resolved relative to the TOML file.

The final MQTT payload contains `status`, `title`, `name`, `job`, `exit_code`, `warning`, `error`, `stderr`, `command`, `version`, `run_id`, and `finished_at`. Exit code 0 reports `status: success`; nonzero outcomes report `status: failure`. Missing datasets do not introduce a new status value: after the script continues through the remaining datasets, the final report is still `status: failure` with `exit_code: 1`, and `error` explicitly identifies the missing dataset name(s) and the `dataset does not exist` reason. This keeps the supplied Home Assistant success/failure branching unchanged. Nonfatal messages captured by the error logger can produce `warning: true` while the overall status remains success. Error fields are bounded to 4096 characters.

MQTT runs in a separate child process so its total operation can be timed out. Broker credentials are passed to that child over stdin rather than on its process command line. MQTT publish failures are sanitized in application logs and do not replace the underlying snapshot operation result.

## Dataset file

Example:

```text
tank/docker
tank/appdata
```

The release includes `datasets.example.txt` as the dataset-list format example. Copy it to the filename configured by `dataset_file` (the default example uses `datasets`) and replace the example dataset names before use. Dataset names are passed literally to ZFS after surrounding whitespace is stripped.

## Snapshot naming and retention

New snapshots are named:

```text
DATASET@SnapBeforeWatchTower-Date-YYYY-MM-DD_HH_MM_SS
```

Only snapshots matching the SnapBeforeWatchTower naming pattern participate in managed retention. Snapshots are sorted by the timestamp embedded in the name. The newest `retain_count` are protected, then older unprotected snapshots are destroyed only when their embedded timestamp is older than the configured cutoff.

Snapshot listing is non-recursive for each configured dataset. A malformed managed timestamp is skipped rather than destroyed. If `zfs snapshot` or the non-recursive `zfs list` fails specifically because ZFS says the configured dataset does not exist, that dataset is skipped and processing continues with later datasets. The missing dataset is still an overall run failure after the remaining work and log cleanup finish. Any other ZFS snapshot/list error, including permission or command failures, remains immediately fatal and prevents destructive retention from continuing for that failing path.

Each dataset is processed separately and a new timestamp is generated for each snapshot. A later failure does not roll back earlier successful snapshots or deletions.

## Log and digest files

Logs are normally written under `./logs` beside the script when running as root. If that location is not writable, or when the script is run without root, the application uses a temporary fallback directory.

A run can create:

```text
SnapBeforeWatchTower-Date-YYYY-MM-DD_HH_MM_SS.log
SnapBeforeWatchTower-Date-YYYY-MM-DD_HH_MM_SS.err
SnapBeforeWatchTower-Date-YYYY-MM-DD_HH_MM_SS.digest
```

An empty current `.err` is removed at the end of the run. Managed old log/digest files are grouped by timestamp and use the same `older_than`/`retain_count` policy as snapshots.

During a real `create` run, Docker digests are collected with:

```bash
docker images --digests
```

A Docker digest failure is logged and the snapshot run continues. No empty/partial digest file is intentionally kept after a failed capture.

## External commands used

For real operations, SnapBeforeWatchTower can invoke:

```text
zfs snapshot DATASET@SNAPSHOT
zfs list -H -t snapshot -o name DATASET
zfs destroy SNAPSHOT

docker images --digests

mail -s SUBJECT [--attach FILE ...] RECIPIENT
```

The application does not use shell interpolation for these commands; arguments are passed as separate subprocess arguments.

## Home Assistant MQTT automation

`homeassistant/SnapBeforeWatchtower-mqtt-persistent-notification.yaml` contains a compatible Home Assistant automation. Its MQTT trigger topic must exactly match `[mqtt].topic` in your TOML configuration. No automation branch change is required for missing datasets: the report still uses `status: failure`, and the automation already includes the payload `error` field in its failure notification, so the missing-dataset reason and dataset name(s) appear in the existing failure path.

## Safety

This program performs destructive ZFS snapshot deletion and log deletion. Review `SAFETY.md`, start with `dry_run = true`, verify the resulting plan/logs, and keep independent backups before using real deletion.
