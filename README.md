# Syncerate

Syncerate processes each matching source and destination ZFS dataset pair listed in two text files. Dataset pairs run sequentially, and optional retry handling can repeat an individual pair when a Broken Pipe occurs.

Current version: `0.4.52`

## ⚠️ Disclaimer / Liability

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does *not* do)
- Review and adapt it to your own environment
- Test it carefully in a non-production setup

By using this script, **you accept full responsibility** for its effects.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

## Disclaimer

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.

---

### Data-loss warning

Syncerate starts Syncoid and ZFS-related operations that can affect source datasets, destination datasets, snapshots, and backup targets. Depending on the configured Syncoid options and available permissions, a run may:

- create snapshots and destination datasets;
- receive replicated data into a target dataset;
- resume or retry an interrupted receive;
- roll back or replace target state when required by Syncoid/ZFS;
- delete target snapshots when destructive Syncoid options are configured;
- execute the configured `SystemAction` as a shell command after a successful run.

Syncerate provides an application-level dry-run mode controlled primarily by `DryRun = true` in the `[runtime]` TOML table. The optional `--dry-run` command-line flag can temporarily force the same mode on. Dry run validates the configuration and dataset-list pairing, builds the exact Syncoid argv that would be used for every pair, and prints/logs a dry-run report. It **does not** start Syncoid, request credentials, start the private ssh-agent, transfer data, or execute `SystemAction`.

A dry run is a planning/validation tool, not proof that a real replication will succeed. It cannot verify live ZFS dataset existence, remote SSH reachability, permissions, Syncoid/ZFS runtime behavior, available space, or destructive effects of the configured Syncoid options. Before using Syncerate with important data:

- set `[runtime].DryRun = true` and review every planned command before changing it back to `false` for a real run;
- read and understand the configured `SyncoidCommand`;
- test first with non-critical datasets on a non-production system;
- keep a separate, verified backup that Syncerate cannot modify;
- grant only the ZFS and system permissions that are actually required;
- review the logs and verify the destination before relying on the backup.

By using this software, you accept responsibility for reviewing, configuring, testing, and operating it. The author is not responsible for data loss, damaged pools, deleted snapshots, broken backups, system damage, service interruption, security issues, or any other problem caused by using this project.

## Requirements

Required:

- Python 3.11 or newer (uses the standard-library `tomllib` TOML parser)
- ZFS
- Sanoid/Syncoid
- Python `pexpect`
- SSH access when a source or destination is remote

Optional:

- OpenSSH `ssh-agent` and `ssh-add` when `UseSSHAgent = true`
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

The included `dist/Syncerate` is built from this release and reports `Syncerate 0.4.52`. It is a Linux x86-64 build; use the Python source or rebuild locally if your system is incompatible. Verify its version with `./dist/Syncerate --version` before scheduling it.

PyInstaller output is platform-specific. A Linux x86-64 build is for compatible Linux x86-64 systems; build separately on Linux ARM/Raspberry Pi, Windows, or macOS for those platforms. PyInstaller is not a cross-compiler.

Run the packaged executable exactly like the Python entry point:

```bash
./dist/Syncerate --version
./dist/Syncerate --help
./dist/Syncerate --conf /path/to/Syncerate.toml
```

### Rebuilding the executable

`requirements-build.txt`, `Syncerate.spec`, and `build-pyinstaller.sh` define the reproducible build path. Create a clean virtual environment, install the pinned build/runtime dependencies, then run the build script:

```bash
python3 -m venv .venv-build
. .venv-build/bin/activate
python -m pip install -r requirements-build.txt
./build-pyinstaller.sh
```

`build-pyinstaller.sh` guarantees a clean final `dist/`. It removes any previous generated output, places all PyInstaller work/staging material under the ignored `.build/` directory, recreates `dist/`, and publishes only two delivery files: the verified `dist/Syncerate` executable and `dist/README.md`. The build fails unless those are the only two top-level entries. The generated `.build/` directory is removed automatically on success or failure. The executable is checked with `--version` and `--help`. The spec explicitly collects both `pexpect` and the dynamically imported `paho.mqtt` package so MQTT support is present even though `paho-mqtt` is imported only when MQTT is enabled.

`dist/README.md` explains that `dist/` is the standalone-delivery directory, the expected executable is `dist/Syncerate`, it is created by running `./build-pyinstaller.sh`, and generated binaries should not be confused with source files. Git ignores generated files under `dist/` while explicitly allowing `dist/README.md` to remain tracked.

## Prepare the application

Make the entry point executable:

```bash
chmod +x Syncerate.py
```

Copy the example configuration:

```bash
cp config/example-Syncerate.toml config/Syncerate.toml
```

Create source and destination list files, then edit `config/Syncerate.toml` with their paths and the Syncoid command to run.

## Per-TOML safe lock (prevents overlapping backups)

Syncerate automatically prevents two copies using the **same resolved TOML file** from running simultaneously. This is always enabled for both normal and `--dry-run` executions; no new TOML option or command-line flag is required.

For a configuration file at `/srv/syncerate/config/nightly.toml`, Syncerate creates/reuses:

```text
/srv/syncerate/config/nightly.toml.lock
```

The identity is the **filename and full canonical directory path** of the `.toml` file, not its `BackupTitle`, list contents, ZFS destination, or the command line's spelling of the path. Relative paths, absolute paths and symlinks resolving to the same TOML share a lock. Different TOML files (including identically named files in different directories) have independent locks and can run at the same time, **even if they point at the same ZFS destination**. Do not deliberately run different configs targeting the same writable destination unless you have checked that this is safe; this is **per-config** protection, not a global ZFS-pool or dataset lock. For simultaneous configurations, also set **different `LogDestination` directories** (or ensure log filenames cannot collide); the existing timestamp-only log naming can otherwise overlap when two different configs share a directory and time format.

A run must be able to **create/read/write the `.toml.lock` file in the TOML directory**. Keep the TOML and its directory in a secure, writable location for the Syncerate service account. When the TOML directory is read-only, inaccessible, or contains an unsafe lock-file symlink, the backup stops *without* running unlocked (exit **14**). In multi-user setups, ensure accounts can safely access the same lock file; permissions may require an agreed service account. This uses Linux/POSIX `fcntl.flock` and is designed for processes sharing the **same host and lock filesystem**; locks on shared network filesystems or across different hosts/containers without a common compatible flock implementation are not guaranteed.

If another process already holds that lock, the second process:

1. **Immediately returns failure exit code `13`**, without attempting credentials, dataset lists, Syncoid, ZFS changes, or a system action. It does not terminate or release the first process's lock.
2. Attempts the normal non-retained failure MQTT status when `Use_MQTT` or `MQTT_JSON_Status` is enabled (using the existing configured JSON or `/error` topic).
3. Attempts an error email when `[mail].Mail` specifies a recipient, **even if** `SendMailOnSuccess` or `SendMQTTOnSuccess` are disabled. Failure mail starts with the final run summary, then states the lock error, and embeds/attaches the duplicate run's separate `.err`/`.log` files when file logging is enabled.

The failure notification includes the TOML path and the lock filename. The rejection's log filenames have a unique `-lock-rejected-...` suffix so a second launch **cannot truncate the active run's log files**, even when the normal log timestamp format is only accurate to a minute/day. A lock-rejection run reports zero completed/failed datasets and `Total datasets: Unavailable` because it never reads the dataset list.

**Do not delete a `.toml.lock` file while a backup might be running.** The file intentionally remains on disk, including after successful completion; the **kernel lock**, not the existence of the file or a PID written inside it, indicates that a run is active. The OS automatically releases it when Syncerate exits, crashes or is killed, and the next run safely reuses the same inode. The `.lock` file is ignored by Git. External cleanup scripts must not remove it during execution.

## Command-line options

Syncerate has four application flags. `--conf`/`-c` selects the required settings file. Normal versus dry-run behavior is normally selected by `DryRun` inside that file; `--dry-run` is an optional one-way override that forces dry-run on. `--help` and `--version` exit directly from the argument parser and therefore do not start runtime work.

| Option | Required | What it does |
| --- | --- | --- |
| `-c FILE`, `--conf FILE` | Yes for normal and dry runs | Selects the required Syncerate TOML configuration file. There is no implicit/default config path. Relative paths are resolved from the current working directory. Every run takes a non-blocking, exclusive per-file `flock` before starting work. |
| `--dry-run` | No | Still acquires the same per-TOML lock as a real run. Forces dry-run on even when `[runtime].DryRun = false` in the selected settings file. It never forces a configured dry run off. The dry-run behavior validates configuration/dataset pairing, reports every exact planned Syncoid command, follows the normal success-notification controls, and does not start Syncoid, request credentials, start the private ssh-agent, or execute `SystemAction`. |
| `-h`, `--help` | No | Prints the complete command syntax, flag descriptions, and examples, then exits with argparse's normal success status. It does not load the configuration, create logs, read dataset lists, request credentials, or start Syncoid. |
| `--version` | No | Prints `<program-name> 0.4.52` for the 0.4.52 source entry point and for a standalone executable rebuilt from this release. The program name reflects the entry point used. The bundled Linux x86-64 `dist/Syncerate` reports 0.4.52. The flag exits without starting a replication run. |

### `--conf FILE` / `-c FILE`

The long and short forms are identical. Supply exactly one configuration path for every normal run:

```bash
./Syncerate.py --conf ./config/Syncerate.toml
./Syncerate.py -c ./config/Syncerate.toml
```

An absolute path is also valid:

```bash
./Syncerate.py --conf /etc/syncerate/Syncerate.toml
```

If the file cannot be read, its required tables/options are missing, or a documented value fails validation, Syncerate reports a configuration error and returns exit code `2` before replication begins.

### Dry run (`[runtime].DryRun` setting)

Dry-run is normally selected in the TOML settings file:

```toml
[runtime]
DryRun = true
```

Then start Syncerate with the normal command:

```bash
./Syncerate.py --conf ./config/Syncerate.toml
```

Set `DryRun = false` for a real replication run. As a convenience, `--dry-run` can temporarily force dry-run on even when the settings file says `false`:

```bash
./Syncerate.py --conf ./config/Syncerate.toml --dry-run
```

There is deliberately no CLI option that forces a configured `DryRun = true` back to a real run. This keeps the persistent safety setting authoritative.

The dry-run report includes the number of planned pairs and the exact shell-style Syncoid command that would be built for each source/destination pair. No credentials are requested, no private ssh-agent is started, Syncoid is never executed, no data is transferred, and `SystemAction` is skipped.

Success notification behavior is identical to a real run: `[mail].SendMailOnSuccess` controls successful dry-run email and `[mqtt].SendMQTTOnSuccess` controls successful dry-run MQTT. Failure notifications are independent of those success switches. Successful dry-run MQTT never publishes the normal retained legacy success payload or Home Assistant `online` availability; it uses a non-retained JSON report instead.

### `--help` / `-h`

```bash
./Syncerate.py --help
```

Use this to see the executable's current syntax and examples. No `--conf` argument is needed when requesting help.

### `--version`

```bash
./Syncerate.py --version
# After rebuilding the standalone executable for this release:
./dist/Syncerate --version
```

No `--conf` argument is needed when requesting the version. The displayed executable name intentionally follows the actual entry point, so source and PyInstaller builds do not have to pretend to have the same filename. The preserved pre-existing binary in this package is not a 0.4.52 build.

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

The matching final name protects against accidentally pairing unrelated datasets. Syncerate checks **all pairs, including the final list entry, before starting any Syncoid command**. Comparison is positional and case-sensitive. Source and destination prefixes may differ, but their final dataset components after `/` must be identical. Extra Syncoid arguments following the destination's first `: ` separator do not affect the comparison.

Unequal list lengths, mismatching final names, empty lists, and trailing slashes are **hard preflight failures (exit `1`)**. If just one pair is wrong, **no datasets are transferred**, even when earlier entries match. This applies to real replication **and** `--dry-run`/`DryRun = true`. A preflight mismatch never prompts for credentials, runs Syncoid, or executes `SystemAction`.

On failure, Syncerate reports **every mismatching pair first** (line number, full source and destination, and reason), followed by **every matching pair**. Missing source/destination entries are explicitly displayed as `(missing)`. That complete report:

- appears at the **very top of the failure email**, before the final run summary; normal failure reason, embedded `.err`/available `.out` logs and file attachments are retained below the summary;
- appears as structured `mismatching_datasets` and `matching_datasets` entries in failure MQTT JSON, with mismatches also included in `failed_datasets` for existing automations;
- is written to `.log` and `.err` (if logging is enabled) and repeated at the **very bottom of terminal output**, after any mail/MQTT activity.

Mail/MQTT failure notifications are attempted when enabled even if `SendMailOnSuccess`/`SendMQTTOnSuccess` are `false`. This does not mean that an unattempted dataset transfer failed: the final run summary counts **zero completed and zero failed transfers** for a pure preflight mismatch, while the mismatch report separately identifies invalid pairings. `Total datasets` uses the count of active source list entries. No new TOML setting is needed.

For example, if source lists `pool/one`, `pool/two` and destination lists `backup/one`, `backup/other`, the failure identifies line 2 as mismatched and line 1 as matching; neither pair transfers.

The runtime missing-dataset/pool exception described below never bypasses this preflight check.

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

Syncerate uses TOML. The shipped complete example is:

```text
config/example-Syncerate.toml
```

Copy it and edit the copy:

```bash
cp config/example-Syncerate.toml config/Syncerate.toml
```

The configuration is divided by responsibility:

- `[backup]` — descriptive metadata only.
- `[syncoid]` — dataset-list paths and the Syncoid command template.
- `[runtime]` — application safety/runtime controls including dry-run, post-success action, missing-dataset continuation, resume policy, and Broken Pipe retry policy.
- `[ssh]` — password/passphrase handling and private ssh-agent settings.
- `[mail]` — email recipient and email success-notification policy.
- `[mqtt]` — broker, legacy MQTT, JSON MQTT, and MQTT success-notification policy.
- `[home_assistant]` — legacy Home Assistant availability integration.
- `[logging]` — log filename format and log destination.

TOML Boolean values are native `true`/`false` values and must **not** be quoted. String-valued disable controls such as `Mail = "No"`, `PassWord = "No"`, `LogDestination = "No"`, and `SystemAction = "No"` remain strings because those options can also contain an address, passphrase, directory, or command.

A compact example:

```toml
[backup]
BackupTitle = "Main ZFS backup"
BackupComment = "Replicate selected datasets to the backup pool"

[syncoid]
SourceListPath = "/absolute/path/to/source-list"
DestListPath = "/absolute/path/to/destination-list"
SyncoidCommand = "syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --compress none --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation"

[ssh]
PassWord = "No"
UseSSHAgent = false
SSHAgentKeyLifetimeSeconds = 3600

[mail]
Mail = "No"
SendMailOnSuccess = true

[mqtt]
Use_MQTT = false
SendMQTTOnSuccess = true
broker_address = "mqtt.example.com"
broker_port = 1883
mqtt_username = ""
mqtt_password = ""
mqtt_topic = "home-assistant/syncerate/command"
mqtt_message = "ON"
MQTT_JSON_Status = false
mqtt_json_topic = "homeassistant/syncerate/status"

[home_assistant]
Use_HomeAssistant = false
HomeAssistant_Available = "home-assistant/syncerate/available"

[logging]
DateTime = "%Y-%m-%d_%H_%M_%S"
LogDestination = "No"

[runtime]
DryRun = false
SystemAction = "No"
ContinueOnMissingDataset = false
ContinueWithoutResume = false
RetryBrokenPipe = true
BrokenPipeRetryCount = 1
BrokenPipeRetryWaitSeconds = 10
```

## Configuration options

| TOML table | Option | Required | Accepted value or purpose |
| --- | --- | --- | --- |
| `[backup]` | `BackupTitle` | No | Optional short name included in logs, email content, and JSON MQTT `title`/compatibility `name` fields. |
| `[backup]` | `BackupComment` | No | Optional description included in logs and email. TOML basic or multiline strings are supported. |
| `[syncoid]` | `SourceListPath` | Yes | Path to the source dataset list. Relative paths are resolved from the current working directory. |
| `[syncoid]` | `DestListPath` | Yes | Path to the destination dataset list. |
| `[syncoid]` | `SyncoidCommand` | Yes | Non-empty Syncoid command template containing exactly one `SourceDataSet` and one `DestDataSet` placeholder. |
| `[runtime]` | `ContinueWithoutResume` | No | Boolean; defaults to `true`. Logs Syncoid's specific resume-unavailable warning and continues; `false` stops with exit `4`. |
| `[runtime]` | `RetryBrokenPipe` | No | Boolean; defaults to `false`. Enables dataset-level ordinary Broken Pipe retries. |
| `[runtime]` | `BrokenPipeRetryCount` | No | Non-negative integer; defaults to `1`. Number of retries after the initial affected attempt. |
| `[runtime]` | `BrokenPipeRetryWaitSeconds` | No | Non-negative integer; defaults to `10`. Wait before each ordinary Broken Pipe retry. |
| `[ssh]` | `PassWord` | Yes | String: `"No"`, `"Ask"`, or a literal SSH password/key passphrase. |
| `[ssh]` | `UseSSHAgent` | No | Boolean; defaults to `false`. Enables an isolated per-run OpenSSH agent. |
| `[ssh]` | `SSHAgentKeyLifetimeSeconds` | No | Positive integer; defaults to `3600`. |
| `[mail]` | `Mail` | Yes | Recipient address, or string `"No"` to disable email completely. |
| `[mail]` | `SendMailOnSuccess` | No | Boolean; defaults to `true`. Controls success email for real and dry runs. Failure email is not suppressed by this switch. |
| `[mqtt]` | `Use_MQTT` | No | Boolean; defaults to `false`. Enables retained legacy MQTT success publishing and non-retained failure/dry-run event routing. |
| `[mqtt]` | `SendMQTTOnSuccess` | No | Boolean; defaults to `true`. Controls success MQTT/HA/JSON publishing. Failure MQTT is not suppressed by this switch. |
| `[mqtt]` | `broker_address` | When either MQTT output is enabled | Broker hostname/IP. |
| `[mqtt]` | `broker_port` | When either MQTT output is enabled | Integer `1..65535`; commonly `1883`. |
| `[mqtt]` | `mqtt_username` | No | Broker username, or empty string. |
| `[mqtt]` | `mqtt_password` | No | Broker password, or empty string. |
| `[mqtt]` | `mqtt_topic` | When `Use_MQTT = true` | Legacy retained success topic. Legacy-only failure uses `<mqtt_topic>/error`; dry-run success uses `<mqtt_topic>/dry-run`. |
| `[mqtt]` | `mqtt_message` | When `Use_MQTT = true` | Legacy retained success payload. The key must exist; an empty payload is allowed. |
| `[mqtt]` | `MQTT_JSON_Status` | No | Boolean; defaults to `false`. Independently enables structured non-retained success/failure JSON. |
| `[mqtt]` | `mqtt_json_topic` | When `MQTT_JSON_Status = true` | Dedicated JSON topic, distinct from enabled legacy/availability topics. |
| `[mqtt]` | `LiveMQTTEnabled` | No | Boolean, default `false`. Enables independent best-effort live MQTT, per-TOML status and last-result channels; does not depend on `Use_MQTT` or `MQTT_JSON_Status`. Requires broker address/valid port when enabled. |
| `[mqtt]` | `LiveMQTTDiscovery` | No | Boolean, default `true`. Publishes retained Home Assistant MQTT Discovery configs for one device per backup. |
| `[mqtt]` | `LiveBackupName` | No | Optional friendly name; falls back to `BackupTitle`, then TOML file stem. Never used as the unique identity or safety lock key. |
| `[mqtt]` | `LiveHeartbeatSeconds` | No | Integer `10..3600`, default `60`; HA live sensors become unavailable after three missed intervals (180 seconds by default). |
| `[mqtt]` | `LiveNotifyStart` | No | Boolean, default `false`; enable an optional non-retained `started` MQTT event. |
| `[mqtt]` | `LiveNotifySuccess` | No | Boolean, default `true`; send a non-retained `completed` event on success. Retained last result is always published while live monitoring is enabled. |
| `[mqtt]` | `LiveNotifyFailure` | No | Boolean, default `true`; send non-retained `failed` and `duplicate_rejected` events. Retained last result is always published by the lock-owning run. |
| `[home_assistant]` | `Use_HomeAssistant` | No | Boolean; defaults to `false`. Enables the legacy retained `online` availability publication when legacy MQTT is also enabled. |
| `[home_assistant]` | `HomeAssistant_Available` | When HA integration is enabled | Availability topic. |
| `[logging]` | `DateTime` | Yes | Python `strftime` pattern used in log filenames. |
| `[logging]` | `LogDestination` | Yes | Directory for `.log`, `.err`, and `.out`, or string `"No"` for terminal-only logging. |
| `[runtime]` | `DryRun` | No | Boolean; defaults to `false`. Safe planning/report mode. `--dry-run` can force it on. |
| `[runtime]` | `SystemAction` | Yes | Trusted shell command run only after successful real replication, or string `"No"` to disable. Always skipped in dry-run. |
| `[runtime]` | `ContinueOnMissingDataset` | No | Boolean; defaults to `false`. `false` records the first recognized missing dataset/pool and stops before the next pair. `true` records the failure and continues later pairs. **Either mode still ends in failure with exit `8` and failure reporting.** |

The loader has a regression-audited schema containing exactly these 38 supported options. Tests compare the loader's actual option accesses to that schema and compare the shipped `example-Syncerate.toml` to the same schema, so a script option cannot be added without also being represented in the TOML example. Unknown extra TOML tables are ignored by startup-configuration logging; only known Syncerate tables are logged, and credential-like keys are suppressed.

`ContinueWithoutResume`, `RetryBrokenPipe`, `BrokenPipeRetryCount`, and `BrokenPipeRetryWaitSeconds` are runtime policy settings and must be placed under `[runtime]`. Syncerate rejects these names when they are left under `[syncoid]`, preventing a misplaced setting from being silently ignored and replaced by its fallback value.

When any MQTT feature is enabled (including independent live status), broker address, broker port, and the topics required by the enabled legacy channels are validated before replication starts. Required text settings may not be empty; use the documented string `"No"` value where that is the supported disable control.

## Optional live status, MQTT heartbeats and automatic Home Assistant Discovery

Enable this independently for each `.toml` configuration using the same `[mqtt]`
broker details already used by Syncerate. **It is disabled by default.**

```toml
[backup]
BackupTitle = "NUC Docker Backup"

[mqtt]
Use_MQTT = false
MQTT_JSON_Status = false
broker_address = "192.0.2.5"
broker_port = 1883
mqtt_username = ""
mqtt_password = ""
LiveMQTTEnabled = true
LiveMQTTDiscovery = true
LiveBackupName = ""           # optional override of BackupTitle
LiveHeartbeatSeconds = 60      # 10..3600 seconds
LiveNotifyStart = false        # optional event: started
LiveNotifySuccess = true       # optional event: completed
LiveNotifyFailure = true       # optional events: failed, duplicate_rejected
```

Live MQTT is **separate from** `Use_MQTT`, `MQTT_JSON_Status`, `SendMQTTOnSuccess`,
and the old `[home_assistant].Use_HomeAssistant` retained availability signal.
Existing mail and MQTT success/failure reporting remains unchanged. Live MQTT
uses a separate Paho client and a background heartbeat thread; broker outage,
missing optional `paho-mqtt`, or a live-status publishing exception only causes
a warning. It does **not** fail, delay a dataset, or skip replication. A short
best-effort delivery window at shutdown helps fast runs publish their result;
network failure may still cause monitoring gaps. A `SIGKILL` or power failure
cannot publish a final result; use heartbeat expiry to detect it.

Each backup gets a stable ID derived from **hostname + full resolved TOML path**.
Config aliases pointing to the same TOML share its ID. A different TOML or host
uses a different ID even if its friendly `BackupTitle` matches. Names do not
control locking. Topic paths are:

| Topic | Retained? | Content |
|---|---|---|
| `syncerate/<backup_id>/status` | **No** | JSON running heartbeat every N seconds; immediate dataset starts and completion/progress and final `success`/`failed` (then expires). Includes `run_id`, backup name, current source → destination pair, total/completed/failed counts, transferred bytes from finished attempts, runtime, and current stream estimate/bytes/percentage/speed. |
| `syncerate/<backup_id>/last_result` | **Yes** | Last completed **owner** run's final JSON result, success/failure, exit code, error, counters and end time. Safe to read after restart; **not** overwritten when a duplicate start is rejected. |
| `syncerate/<backup_id>/events` | **No** | Optional `started`, `completed`, `failed`, or `duplicate_rejected` event (configured independently). |
| `homeassistant/sensor/syncerate_<backup_id>/<entity>/config` | **Yes** | Automatic MQTT Discovery for twelve live sensors plus the separate last-result sensor. |

The initial live status is `running`; `current_dataset` identifies the configured
source → destination pair. Run-wide `data_transferred_bytes` remains the total
from finished attempts. Failed counts reflect attempted but not completed
pairs; untouched entries never count as failed.

### Live dataset transfer progress

When live monitoring is enabled, four additional sensors appear automatically
under the same backup device. No additional TOML settings are needed.

| Home Assistant sensor | MQTT JSON field | Meaning |
| --- | --- | --- |
| Dataset estimated size | `current_dataset_estimated_bytes` | Rounded `(~ size)` estimate for the current Syncoid send stream, in bytes. |
| Dataset transferred | `current_dataset_transferred_bytes` | Highest observed byte counter for that stream. |
| Dataset progress | `current_dataset_progress_percent` | Transferred / estimated bytes × 100; may exceed 100%. |
| Dataset transfer speed | `current_dataset_bytes_per_second` | Latest parseable rate reported by the progress output, in bytes/second. |

Readings are parsed as Syncoid output arrives, including during a long transfer,
and included in the **same non-retained status message as each heartbeat**.
The normal interval is 60 seconds; set `LiveHeartbeatSeconds = 10` under `[mqtt]`
for more frequent updates (valid range 10–3600). Configured pair boundaries and final
results still publish immediately. Output lines update an in-memory cache;
they do not cause an MQTT publication for every progress refresh.

For your example, `(~ 3.3 GB)` and `3,34GiB ... [23,3MiB/s]` produce an estimate
of about 3.3 GiB, 3.34 GiB transferred, **101.21%**, and 23.3 MiB/s. Syncoid's
`readablebytes` formatter uses powers of 1024 despite labelling its estimates
KB/MB/GB, so those labels are converted accordingly. Explicit `pv` GiB/MiB units
are binary; `pv` GB/MB units are decimal. Period and comma decimals are accepted.
The displayed `99%` from the progress bar is not used: Syncerate calculates its
own approximate percentage from the two byte amounts. See
[Syncoid readablebytes](https://github.com/jimsalterjrs/sanoid/blob/master/syncoid)
for the estimate formatting and
[Home Assistant MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/)
for unknown numeric states and expiry behavior.

A configured pair may send multiple snapshots or recursive child datasets.
These four readings describe the **current send stream**, not an estimate of
all remaining work for that pair or the entire backup. Each new stream,
configured pair or retry resets the estimate, transferred amount and speed.
The progress sensor's attributes include `current_transfer` (the complete
recognized Syncoid heading, identifying recursive child/snapshot paths) and
`progress_observed_at` (UTC time of the most recent byte-counter observation).
The same fields are available in the MQTT payload. Heartbeats repeat the last
observation when output stalls; a heartbeat proves the script is alive, not
that data is still moving. The speed is the last reported rate, not an
independently measured current rate.

Missing estimates, missing counters, unavailable rates and percentages without
a positive estimate are JSON `null` (Home Assistant `unknown`), rather than
invented zeroes. This can occur with resumed transfers, `--quiet`, or custom
`--pv-options` that hide normal byte/rate output. A confirmed zero-byte counter
or rate remains zero. A missing estimate does not prevent publishing observed
bytes or speed. Final results preserve the latest readings without forcing
100%; success still requires the existing exit-status and safety checks.

Home Assistant MQTT Discovery creates one device per backup with live status,
current dataset, total/completed/failed dataset counts, bytes, elapsed runtime,
heartbeat timestamp, the four dataset transfer measurements, and retained last result. Live sensors use
`expire_after = LiveHeartbeatSeconds * 3`; the retained last-result sensor has
**no expiry**. A stale heartbeat makes live sensors unavailable (unknown
interruption), not conclusively `failed`. Stale live status is expected a few
minutes *after* a normal completion; use last result for historical outcome.

**Home Assistant/Pushover alert examples:** `config/HomeAssistant-Live-Backup-Alerts.yaml`
includes optional failure/duplicate alerts, heartbeat-missing-while-running
and long-runtime alerts. Change the example `notify.pushover` service and the
example status entity IDs to your own discovered device/entity IDs. A Pushover
notification requires Home Assistant's notification integration; Syncerate
itself does not directly call Pushover. To avoid false alarms, the stale alert
triggers only on a live status transition **from `running` to `unavailable`**;
`success`/`failed` subsequently expiring is normal. MQTT Discovery and
notifications require working MQTT integration in Home Assistant.

**Safelock behavior:** only the successful TOML lock owner publishes `status`
and `last_result`. A duplicate launch exits with existing failure code 13,
attempts the existing configured mail/legacy failure MQTT and can publish an
extra non-retained `duplicate_rejected` event. It never changes the owner's
RUNNING state, last successful result, or lock. A failure establishing the lock
(exit 14) similarly never claims the owner topics.

**Operational limits:** Per-host MQTT IDs assume stable hostnames and canonical
TOML paths. Renaming/moving the TOML or changing host name changes HA device
identity (previous Discovery entries must be removed manually). A broker
restart/network failure can cause missed events; retained last results are
republished on MQTT reconnect while the running process is alive. There is no
cross-host lock or real-time MQTT guarantee.

## Syncoid command templates

The template must contain exactly one occurrence of each of these case-sensitive placeholders:

```text
SourceDataSet
DestDataSet
```

Syncerate replaces them separately for every dataset pair and starts Syncoid with an argument list rather than one shell command string. This preserves dataset names containing spaces.

### Local source to local destination

```toml
[syncoid]
SyncoidCommand = "syncoid SourceDataSet DestDataSet"
```

The local Syncoid process and local ZFS commands run as the effective user that started `Syncerate.py`.

### Remote source to local destination

```toml
[syncoid]
SyncoidCommand = "syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation"
```

### Local source to remote destination

```toml
[syncoid]
SyncoidCommand = "syncoid SourceDataSet backupuser@192.0.2.20:DestDataSet --sshport 22 --sshkey /root/.ssh/syncerate --no-privilege-elevation"
```

A remote endpoint uses the SSH user written before `@`. `--sshport` selects a non-default SSH port, and `--sshkey` selects the key used for authentication.

Use Syncoid's `--no-privilege-elevation` when the local and remote users already have the required ZFS permissions and Syncoid should not invoke `sudo`. When Syncerate itself is run as root, local ZFS commands already run as root; a non-root remote SSH user still needs appropriate delegated ZFS permissions.

Any other Syncoid options can be included in `SyncoidCommand` or added to individual destination lines.

## Password and passphrase handling

`PassWord` still supports three modes: string `"No"`, string `"Ask"`, or a literal password/passphrase. For example:

```toml
[ssh]
PassWord = "Ask"
```

`Ask` prompts once with `getpass()` when Syncerate starts and is recommended for an encrypted SSH key because the passphrase is not stored in the configuration. Password, MQTT credentials, and other secret-like option names are omitted from normal configuration logging. Only known Syncerate TOML tables are logged; unrelated TOML tables are not echoed.

### Recommended encrypted-key mode: private ssh-agent

Enable the isolated agent path with:

```toml
[ssh]
UseSSHAgent = true
SSHAgentKeyLifetimeSeconds = 3600
PassWord = "Ask"
```

The `SyncoidCommand` must contain the identity explicitly, for example:

```toml
[syncoid]
SyncoidCommand = "syncoid backupuser@192.0.2.10:SourceDataSet DestDataSet --sshkey /root/.ssh/syncerate --no-privilege-elevation"
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

```toml
[ssh]
UseSSHAgent = false
```

Syncerate uses the original Pexpect-through-Syncoid model. Pexpect starts Syncoid and watches the output produced by Syncoid and its nested SSH process. If an SSH account-password or private-key-passphrase prompt appears, Syncerate temporarily disables the `.out` logfile, sends `PassWord` directly to the Syncoid Pexpect child, then restores logging. The nested Syncoid prompt path deliberately does not wait for a separate no-echo transition before sending, preserving the established behavior. If `PassWord = "No"`, an observed credential prompt remains a fatal authentication error. Prompt matching is shaped like a real password/passphrase prompt, so ordinary output containing words such as `password` is not treated as a request for a secret.

## Multiline backup comments

`BackupComment` lives under `[backup]`. A normal one-line TOML string works, or use a TOML multiline basic string for several lines:

```toml
[backup]
BackupComment = """First line
Second line
Third line"""
```

The embedded newlines are preserved in terminal/file summaries and email reports, while each physical log line is still prefixed safely by the logger.

## Logging

Terminal-only logging:

```toml
[logging]
LogDestination = "No"
```

Write files to a directory:

```toml
[logging]
LogDestination = "/var/log/syncerate"
```

Syncerate creates the directory when necessary and can write:

```text
Syncerate-<timestamp>.log
Syncerate-<timestamp>.err
Syncerate-<timestamp>.out
```

- `.log` contains normal application messages.
- `.err` contains ERROR-level application messages. For handled Syncoid/ZFS failures, Syncerate also copies a bounded tail of the relevant raw child output into `.err`, so the failure reason and nearby `mbuffer`/Syncoid/ZFS diagnostics are visible without opening `.out`.
- `.out` contains the complete raw Syncoid process output captured by Pexpect.

The timestamp is generated from `DateTime`, for example:

```toml
[logging]
DateTime = "%Y-%m-%d_%H_%M_%S"
```

For every normal invocation, Syncerate starts a monotonic runtime timer before configuration/runtime work. The reported `Total runtime` is captured when the replication run has reached its success/failure result, immediately before post-run email and `SystemAction` handling. This fixed cut-off is intentional: it allows the **same runtime value** to be written to terminal, `.log`, and the email that is about to be sent. Time spent sending that same email, waiting the optional two minutes before a system action, or executing the system action cannot be included in an email that has already been constructed.

For successful runs, Syncerate also reports `Data transferred`. It reads the byte counter emitted by Syncoid's normal `pv` progress stream, keeps the highest observed byte count for each individual Syncoid send stream, and sums those completed/attempted streams across all dataset pairs. This avoids counting repeated progress refreshes more than once while still including bytes that were actually retransmitted during a Broken Pipe retry. The displayed unit is chosen automatically using 1024-based thresholds: `KB`, `MB`, `GB`, or `TB`. Values smaller than 1 KB are shown as a fractional KB.

Syncerate deliberately does **not** guess a transfer size from Syncoid's rounded `(~ size)` estimates. If a transfer starts but a usable `pv` byte counter cannot be observed—for example because `--quiet` suppresses progress, `pv` is unavailable, or custom `--pv-options` replace the normal byte-counter output—the final success summary reports `Data transferred :   Unavailable`.

The final run summary is the **same layout in terminal logging and both success/failure email bodies**. **Every populated summary line has an empty line after it before the next populated line**, including each physical line of a multiline backup comment, the dry-run mode/planned-pair fields, and the real-run statistics. Real-run fields appear in this order: `Data transferred`, `Total datasets`, `Completed datasets`, `Failed datasets`, `Total runtime` (`HH:MM:SS.mmm`). The summary is written to `.log` before either email is constructed; success mail also embeds its `.log` and attaches `.log`/`.out` when enabled. In failure mail, the failure reason and embedded logs still appear **after** the summary and the existing separator; available log files remain attached.

Each source/destination **pair counts as one dataset** in these statistics. `Total datasets` is the number of validated configured pairs, not the number of Syncoid attempts or ZFS child datasets. `Completed datasets` counts pairs that actually finished with Syncoid exit status `0`; a Broken Pipe retry still counts the same pair at most once. `Failed datasets` counts attempted pairs that did not finish successfully, including recognized missing-dataset skips and a current pair that aborted because of ENOSPC or another fatal error. Pairs not yet started are **not** counted as failed. Thus `completed + failed` may be less than `total` if the run stops early. Failures before dataset-list validation show `Total datasets : Unavailable` rather than inventing a count. Errors before any replication begins show zero completed and zero failed datasets.

When a fatal replication error interrupts an in-progress stream, `Data transferred` is marked `Unavailable` because the final byte measurement may not have reached the application. Missing-dataset failures that complete their processing can retain the observed transfer total; the usual incomplete-measurement rule still applies. A successful dry run instead labels itself `DRY RUN`, prints the planned-pair count plus total/completed/failed statistics (zero completed/failed), and omits `Data transferred` because **no data is sent**. Error notifications in dry-run mode are still marked as dry run. The missing-dataset/pool failure path continues or stops as directed by `[runtime].ContinueOnMissingDataset`, always preserving exit code `8`. `--help` and `--version` do not run a backup and have no final summary.

Example:

```text
Final run summary

Backup title    :   Main ZFS backup

Backup comment  :   Replicate selected datasets to the backup pool

                    Second comment line

Data transferred :   18.47 GB

Total datasets   :   12

Completed datasets :   12

Failed datasets  :   0

Total runtime   :   01:23:45.678
```

## Email notifications

Disable email:

```toml
[mail]
Mail = "No"
```

Enable email:

```toml
[mail]
Mail = "user@example.com"
SendMailOnSuccess = true
```

`SendMailOnSuccess` defaults to `true` when omitted. Set it to `false` when you want email only for failures. The switch applies to both real successful runs and successful dry-run reports. It does not suppress error mail: as long as `Mail` contains a recipient, handled Syncerate errors still attempt to send their normal error email. A successful dry-run email is explicitly marked `DRY RUN`, states that no replication was performed, and contains the planned-command report.

A working local `mail` command is required for delivery. Syncerate can send real-success, dry-run-success, Syncoid-error, script-error, and MQTT-error messages. Normal success and failure real-run emails begin with the same final run summary, including the total/completed/failed dataset counters below the transfer line and above runtime. **Preflight dataset mismatch emails are the deliberate exception: their complete mismatching-first then matching-pair report comes above the final run summary**, so the offending paths are immediately visible. The **failure reason comes after the summary**, followed (with file logging enabled) by the `.err` and available `.out` contents in the **email message body**, while the `.log`, `.err`, and available `.out` are also attached **as files**. This applies to missing-dataset failure mails as well as ordinary fatal Syncoid, ZFS and script errors. Without file logging, the failure reason still appears after the summary, but no files can be attached. Missing dataset/pool reports also include the failed pair list and relevant ZFS messages.

Dry-run success mail instead identifies `DRY RUN`, records the number of planned datasets and zero completed/failed, and includes the exact planned commands; it does not claim transferred data. Error notifications in dry-run mode remain marked as dry run. With `[runtime].ContinueOnMissingDataset = false`, Syncerate records the first recognized missing dataset/pool, stops before the next pair, and sends an exit-code-`8` failure mail. With it set to `true`, it records each recognized failure, continues later configured pairs, and still sends an exit-code-`8` failure mail at the end. `SendMailOnSuccess = false` suppresses success mail **only**; configured failure email is still attempted. Mail delivery is best-effort: a missing `mail` executable, attachment/read failure, or non-zero mail-command result is logged and does not replace the replication result.

## Syncoid warnings and resume support

Ordinary Syncoid `WARN` and `WARNING` lines are ignored for failure detection, including generic skip, missing-snapshot cleanup, and known-host warnings. The specific `Skipping dataset (dataset no longer exists): ...` message is an explicit runtime missing-data report and is handled as a deferred failure. Matching is case-insensitive and accepts leading indentation. Ordinary warnings are not separately logged or added to the failure summary; their original text remains in `.out` when file logging is enabled.

An ordinary warning alone does not make the run fail. An ordinary warning followed by exit `0` is successful; a non-zero exit still fails. The explicit disappeared-dataset warning and resume policy described here are the exceptions. Warning text containing words such as `Permission denied` or `Broken pipe` is treated as part of that warning. A separate non-warning error line still receives its normal handling.

The separate resume policy applies to Syncoid's `ZFS resume feature not available` warning:

```toml
[runtime]
ContinueWithoutResume = true
```

This optional TOML Boolean defaults to `true`; use native unquoted `true` or `false`. Syncerate logs the resume-unavailable warning and waits for Syncoid to finish. A later error or non-zero exit still fails.

To require resume support:

```toml
[runtime]
ContinueWithoutResume = false
```

Syncerate stops the current child process and returns exit code `4` when that warning is observed. The remaining dataset pairs and successful-run actions are not started. Enabled error notifications are attempted, even when success notifications are disabled. This reacts to Syncoid's output; it does not perform a separate capability check before Syncoid starts.

## Interrupted receive recovery

Syncoid owns resumable-receive recovery. When the source snapshot for an interrupted receive no longer exists, Syncerate lets Syncoid reset the stale receive state and start a replacement send without modifying the configured command.

Syncerate retains internal recovery tracking for the non-warning stale-source message and the receive-reset announcement. The reset warning itself is ignored without separate warning logging; it only supplies context so a following non-warning Broken Pipe during that reset does not consume the ordinary retry allowance. A new `INFO: Sending incremental` or `INFO: Sending full` clears that recovery state.

`ContinueWithoutResume` controls unavailable resume support, not stale-state recovery. Real process failures still fail, including a non-zero exit after a missing destroy-snapshot message.

## Optional Broken Pipe retry

The feature is disabled by default:

```toml
[runtime]
RetryBrokenPipe = false
```

Enable it and select the retry count and wait time with:

```toml
[runtime]
RetryBrokenPipe = true
BrokenPipeRetryCount = 1
BrokenPipeRetryWaitSeconds = 10
```

`BrokenPipeRetryCount` is the number of retries allowed **after the initial attempt for each individual dataset pair**. It defaults to `1` when omitted. A value of `3` permits up to four total attempts for a dataset: the initial attempt plus three retries. A value of `0` stops the run after its first ordinary Broken Pipe.

`BrokenPipeRetryWaitSeconds` is the number of whole seconds to wait before each retry. It defaults to `10` when omitted, and `0` retries immediately.

When enabled, Syncerate watches Syncoid output case-insensitively for the text `Broken pipe` and applies this policy independently to every dataset pair. The exception is a Broken Pipe emitted while Syncoid is actively resetting a stale interrupted receive; that expected recovery symptom is logged and ignored until Syncoid starts the replacement send. For ordinary Broken Pipe events:

1. Broken Pipe stops only the current Syncoid attempt.
2. If that dataset still has retries available, Syncerate waits for `BrokenPipeRetryWaitSeconds` and retries the same dataset with the same command.
3. If Broken Pipe continues after all configured retries, Syncerate stops the entire run with exit code `2`. It does not start later dataset pairs or run successful completion actions.
4. Enabled mail/MQTT error notifications are attempted even when success notifications are disabled.
5. A successful retry allows normal processing to continue; every later dataset receives its own retry allowance.

If a confirmed missing-dataset/pool error has already been observed, a following Broken Pipe is treated as a secondary symptom. Syncerate waits for that Syncoid process to finish and applies the missing-data exception below instead of retrying it.
The retry count is never shared between datasets. This option does not retry authentication failures, non-warning missing-dataset errors, connection failures, or other nonzero Syncoid exits. Warning lines do not trigger retries. When the option is disabled or omitted, Broken Pipe is not given special retry handling; Syncerate waits for Syncoid's real exit status and applies the normal failure behavior.

## MQTT notifications

`SendMQTTOnSuccess` is optional and defaults to `true`. Setting it to `false` suppresses successful MQTT messages for both real runs and dry runs, including Home Assistant availability and JSON success events. It does not disable error reporting.

During dry-run mode, Syncerate never publishes the normal retained `mqtt_message` or retained Home Assistant `online` availability payload. When success MQTT is enabled, it sends one non-retained JSON dry-run report instead. `MQTT_JSON_Status = true` uses `mqtt_json_topic`; otherwise `Use_MQTT = true` uses the derived `<mqtt_topic>/dry-run` topic. The JSON includes `"dry_run": true` and the planned source/destination pairs.

| Enabled MQTT options | Real success, when `SendMQTTOnSuccess = true` | Dry-run success, when `SendMQTTOnSuccess = true` | Handled error, regardless of the success switch |
| --- | --- | --- | --- |
| `Use_MQTT` only | Retained `mqtt_message` on `mqtt_topic`, plus configured HA availability | One non-retained JSON dry-run report on `<mqtt_topic>/dry-run`; no retained success/availability payload | Non-retained JSON on `<mqtt_topic>/error` |
| `MQTT_JSON_Status` only | Non-retained JSON on `mqtt_json_topic` | One non-retained JSON dry-run report on `mqtt_json_topic` | Non-retained JSON on `mqtt_json_topic` |
| Both | Both normal success outputs | One non-retained JSON dry-run report on `mqtt_json_topic`; no retained legacy/HA success output | One non-retained JSON event on `mqtt_json_topic` |
| Neither | No MQTT publishing | No MQTT publishing | No MQTT publishing |

The error topic for `Use_MQTT` alone is derived by appending `/error` to the exact configured `mqtt_topic`; there is no extra configuration key. Subscribe your error handler to that topic. Error events use the JSON schema below and contain `status`, `exit_code`, `error`, and captured output in `stderr`. When the failure happened during dry-run mode, the JSON also has `"dry_run": true`. Failure events never publish the success payload or availability `online`, never replace a retained success message, and are not suppressed by `SendMQTTOnSuccess`.

For email and MQTT only on errors, configure:

```toml
[mail]
Mail = "user@example.com"
SendMailOnSuccess = false

[mqtt]
Use_MQTT = true
SendMQTTOnSuccess = false
broker_address = "mqtt.example.com"
broker_port = 1883
mqtt_topic = "syncerate/result"
mqtt_message = "ON"
MQTT_JSON_Status = false
```

This sends error email and publishes failure JSON on `syncerate/result/error`. Keep the other required application settings in your configuration. Enable `MQTT_JSON_Status` and set `mqtt_json_topic` to route errors to a dedicated status topic instead.

### Original retained MQTT behavior

Enable retained success messages and non-retained error reports:

```toml
[mqtt]
Use_MQTT = true
SendMQTTOnSuccess = true
broker_address = "192.0.2.30"
broker_port = 1883
mqtt_username = "syncerate"
mqtt_password = "secret"
mqtt_topic = "home-assistant/syncerate/command"
mqtt_message = "ON"
```

After replication completes successfully, Syncerate publishes `mqtt_message` to `mqtt_topic` with **retain enabled** when `SendMQTTOnSuccess` is true. Handled failures publish JSON on `<mqtt_topic>/error` when JSON status is disabled, or on `mqtt_json_topic` when enabled.

To add the original Home Assistant availability integration:

```toml
[mqtt]
Use_MQTT = true

[home_assistant]
Use_HomeAssistant = true
HomeAssistant_Available = "home-assistant/syncerate/available"
```

On a successful run with `SendMQTTOnSuccess = true`, Syncerate additionally publishes retained payload `online` to `HomeAssistant_Available`. This old HA behavior remains tied to `Use_MQTT` and is unchanged.

A matching example entity configuration is supplied in:

```text
config/HomeAssistant-Configuration-For-MQTT.yaml
```

### Independent JSON success/failure status

JSON can be enabled **in addition to** the old outputs:

```toml
[mqtt]
Use_MQTT = true
MQTT_JSON_Status = true
mqtt_topic = "home-assistant/syncerate/command"
mqtt_message = "ON"
mqtt_json_topic = "homeassistant/syncerate/status"
```

Or JSON can run by itself while the old MQTT output is disabled:

```toml
[mqtt]
Use_MQTT = false
MQTT_JSON_Status = true
broker_address = "192.0.2.30"
broker_port = 1883
mqtt_json_topic = "homeassistant/syncerate/status"
```

The JSON topic is deliberately separate from the retained legacy topics. When both old MQTT and JSON are enabled, `mqtt_json_topic` must differ from `mqtt_topic`; when the old Home Assistant availability integration is also enabled, it must differ from `HomeAssistant_Available` as well.

**Every completion-notification JSON publish uses `retain = false`. There is no configuration option that can enable retain for these events.** The independent live monitor retains only its last result and HA discovery definitions. This prevents Syncerate from creating a retained JSON success/failure event that Home Assistant could replay on reconnect. Use a new dedicated topic such as `homeassistant/syncerate/status` so it also does not inherit the meaning of an older retained legacy topic.

Successful JSON example:

```json
{
  "status": "success",
  "success": true,
  "title": "Main ZFS backup",
  "name": "Main ZFS backup",
  "job": "syncerate",
  "dry_run": false,
  "planned_datasets": [],
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
  "dry_run": false,
  "planned_datasets": [],
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

`title` comes from `BackupTitle`; `name` carries the same value as a compatibility alias. `dry_run` is `true` only for successful dry-run reports, and `planned_datasets` then lists the source/destination pairs that would have been processed. The configured `SyncoidCommand` is deliberately excluded from JSON so SSH endpoints, key paths, and command options are not exposed through the status event.

For a preflight dataset-name mismatch (exit `1`), failure JSON additionally carries `mismatching_datasets`, `matching_datasets`, `source_dataset_count`, and `destination_dataset_count`. Every comparison object contains 1-based `line`, full `source`, full `destination`, and `reason`; an absent counterpart uses JSON `null`. For compatibility with existing automation consumers, the mismatches are **also** included in `failed_datasets` (these are *validation* failures, not attempted ZFS transfers). For example:

```json
{
  "status": "failure",
  "success": false,
  "exit_code": 1,
  "error": "Source/destination final dataset names do not match",
  "matching_datasets": [
    {"line": 1, "source": "pool/good", "destination": "backup/good", "reason": ""}
  ],
  "mismatching_datasets": [
    {"line": 2, "source": "pool/Joplin", "destination": "backup/Joplin2", "reason": "Final dataset names differ: 'Joplin' != 'Joplin2'"}
  ],
  "source_dataset_count": 2,
  "destination_dataset_count": 2,
  "failed_datasets": [
    {"line": 2, "source": "pool/Joplin", "destination": "backup/Joplin2", "reason": "Final dataset names differ: 'Joplin' != 'Joplin2'"}
  ]
}
```

Only the extra/matching fields are illustrated here; the actual JSON retains all standard status fields and uses the existing configured MQTT status/error topic with `retain=false`.

The `stderr` field is bounded to the last 4000 characters of relevant captured child/Syncoid output. The `warning` and `skipped_datasets` fields remain in the JSON schema for compatibility; current runs do not report exhausted Broken Pipe retries as success. A missing dataset/pool run is a real failure with exit code `8`. With `ContinueOnMissingDataset = false` (the default), Syncerate stops the configured list after the first recognized missing dataset/pool error. With `true`, it continues later pairs but still fails at the end. The JSON failure event includes each recorded source/destination pair and the matched ZFS/Syncoid text in `failed_datasets`.

Failure JSON is best-effort and never replaces the original Syncerate exit code. `SendMQTTOnSuccess = false` does not affect this path. If MQTT itself is the failing component, Syncerate does not recursively try to report that MQTT failure over MQTT. Errors before configuration is loaded cannot be published.

For a broker without username authentication, leave both credential fields empty:

```toml
[mqtt]
mqtt_username = ""
mqtt_password = ""
```

A matching automation with explicit **success**, **failure**, and default **unknown** branches is supplied in:

```text
config/HomeAssistant-Automation-For-MQTT-JSON.yaml
```

The automation example listens to `homeassistant/syncerate/status`. When using `Use_MQTT` without JSON status, change its trigger topic to your derived error topic, such as `syncerate/result/error`; that subscription receives failures only.

## Successful-run system action

Disable the action:

```toml
[runtime]
SystemAction = "No"
```

Examples (choose one value):

```toml
[runtime]
SystemAction = "shutdown -P now"
```

```toml
[runtime]
SystemAction = "reboot"
```

```toml
[runtime]
SystemAction = "/path/to/trusted-script.sh"
```

The command is executed through a shell only after all dataset transfers succeed, configured success MQTT publishing has completed when `SendMQTTOnSuccess` allows it, and configured success email has been attempted when `SendMailOnSuccess` allows it. dry-run mode always skips `SystemAction`, even when it is configured. Configure only trusted commands. A system-action exception or non-zero shell return code is logged explicitly, but it remains a best-effort post-run action and does not change an otherwise successful Syncerate exit code.

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

```toml
[syncoid]
SyncoidCommand = "syncoid SourceDataSet DestDataSet"
```

Review the plan first by setting this in the settings file:

```toml
[runtime]
DryRun = true
```

Then run Syncerate normally:

```bash
./Syncerate.py --conf ./config/Syncerate.toml
```

Only after the dry-run report is correct, change the settings file back to:

```toml
[runtime]
DryRun = false
```

and run the same command for the real replication.

Verify the destination and snapshots:

```bash
sudo zfs list
sudo zfs list -t snapshot
```

## Preflight and runtime failures

| Stage/result | Behavior |
| --- | --- |
| Preflight list length/name mismatch (including final pair), empty list, or trailing slash | Stop with exit `1` before any Syncoid command starts. Log and report **all mismatching and matching pairs**, put mismatches first in failure email/MQTT and print the full audit at the **bottom of terminal output** after attempted configured notifications. |
| Syncoid reports a specifically recognized missing dataset/pool during execution | Record that pair and its raw failure context. For a definitive non-warning ZFS missing-data error, give Syncoid up to 5 seconds to unwind; if it remains stuck, stop only that already-failed attempt. With `ContinueOnMissingDataset = false` (default), stop the configured dataset list after recording the failure. With `true`, continue to later pairs. Recognized missing-data handling still requires matching runtime evidence plus an accepted exit/cleanup state; an exit code by itself never enables this path. |
| One or more missing-data failures were recorded | Return exit `8`, attempt enabled error mail/MQTT with failed pairs and reasons, and skip successful-run system actions. With continuation enabled, this happens after the remaining list completes; with it disabled, it happens immediately after the first recorded missing-data pair returns to the application layer. |
| ZFS reports a definitive `cannot receive ...: out of space` or other supported non-warning ENOSPC diagnostic | Immediately stop the failed Syncoid process and its verified dedicated process group; return exit `12` without retrying or executing later dataset pairs. Attempt configured failure mail and/or MQTT regardless of success-notification switches. |
| Authentication, connection, other recognized fatal errors, or unrelated nonzero exits | Stop the list; retain their error handling. |
| Ordinary Broken Pipe retries are exhausted | Stop with exit `2`; attempt enabled error notifications. |

### Destination out-of-space failures

Syncerate treats full-line, non-warning OpenZFS diagnostics including `cannot receive resume stream: out of space`, `cannot receive incremental stream: out of space`, `cannot receive new filesystem stream: out of space`, `cannot receive: no space left on device`, and supported ZFS create/write errors as immediately fatal. It detects them even when they arrive in chunks, or at process EOF without a final newline. Generic warnings or text merely mentioning `out of space` do not activate this handler. This is output-based detection, **not** a separate preflight free-space check; unrecognized/localized messages follow the normal Syncoid exit path.

When one of these errors is detected, Syncerate captures the ZFS error and surrounding `mbuffer`/Syncoid output, attempts to stop the current Syncoid process and subprocesses in its verified dedicated process group, closes the output logfile, and returns **exit code `12`**. It does not retry that pair or start another pair, even when `RetryBrokenPipe = true` or `ContinueOnMissingDataset = true`. No success notifications or `SystemAction` run. If `Mail` is enabled, error mail is attempted with an out-of-space subject and the diagnostic in the body even with logging disabled. If `Use_MQTT` or `MQTT_JSON_Status` is enabled, a non-retained JSON failure event is attempted on the configured error/status topic with exit code `12`, `status: failure`, and ZFS detail in `error`/`stderr`. `SendMailOnSuccess` and `SendMQTTOnSuccess` do not suppress those failure events. Notification delivery itself remains best-effort and is not proof the broker/mail system received it.

Before restarting a failed replication, investigate available destination pool/dataset space, quotas and reservations with `zpool list` and `zfs list -o name,used,avail,quota,refquota`. Make sufficient space available safely and verify any resumable receive state. Do not delete snapshots or reset an interrupted receive without understanding the recovery consequences.

The missing-data exception requires specific runtime evidence. It recognizes complete English OpenZFS missing dataset/pool diagnostics from open/import operations, missing destination parents/pools during create operations, and explicit missing destinations reported by receive operations. Syncoid's `CRITICAL ERROR:` and property-query wrappers are supported. It also recognizes the exact disappeared-dataset skip warning, because Syncoid can emit that message without setting a nonzero exit code.

Generic “no datasets found” text, generic skip warnings, missing snapshots/bookmarks, and arbitrary text containing “does not exist” do **not** qualify. A recognized missing-data message does not suppress later authentication/connection errors or unrelated exits outside `0`, `1`, and `2` while Syncoid is still exiting normally. The one exception is the deliberate 5-second cleanup guard after a definitive non-warning missing-data diagnostic: if that already-failed Syncoid process does not exit, Syncerate terminates only that attempt so it cannot block every later dataset. Unknown/localized messages retain normal process-exit handling instead of being guessed as missing data.

The final error notifications use the existing controls: error email requires `Mail` to contain a recipient; MQTT errors require `Use_MQTT` or `MQTT_JSON_Status`. `SendMailOnSuccess` and `SendMQTTOnSuccess` do not suppress errors. MQTT lists the affected pairs in `failed_datasets`; error email lists the pairs and captured reasons. With file logging enabled, the `.err` attachment also contains bounded raw Syncoid/ZFS/mbuffer context around handled missing-data failures, while `.out` remains the complete raw stream.

SSH prompt handling, repeated-prompt limits, stale receive recovery, and signal-derived exit codes remain active. First-contact host-key confirmation is automatically answered `yes`; prepopulate `known_hosts` or configure `StrictHostKeyChecking` when preverified keys are required.

### Source of the message matching

The rules were checked against [Syncoid's implementation](https://github.com/jimsalterjrs/sanoid/blob/d39b51a013081e86bb26a6859866c34d98c39ea3/syncoid), including its missing-source checks, recursive disappeared-dataset path, logging wrappers, and transfer exit handling. The underlying diagnostics were checked against OpenZFS's [dataset operations](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_dataset.c), [pool operations](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_pool.c), [error descriptions](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_util.c), and [receive operations](https://github.com/openzfs/zfs/blob/1f380a4f34da6068d22960807f53cda68a356add/lib/libzfs/libzfs_sendrecv.c).

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | The dataset list completed and no fatal handled error was returned. Mail-command and system-action failures are currently logged rather than changing this code. |
| `1` | Source/destination list validation failed; when comparable, all matching/mismatching entries and their reasons are recorded and reported through enabled mail/MQTT. No transfer begins. |
| `2` | Script/configuration error or exhausted ordinary Broken Pipe retries. Syncoid can also return this code for an unrelated fatal error. |
| `4` | Syncoid reported unavailable resume support while `ContinueWithoutResume = false`. Other warning lines do not cause this exit. |
| `5` | Password, authentication, or permission failure. |
| `6` | Connection timed out. |
| `7` | Connection was refused. |
| `8` | One or more configured pairs encountered a missing ZFS dataset or pool. Syncerate continues the remaining list for the recognized missing-data cases, then reports the completed run as failed with code `8`. |
| `9` | The same monitored output pattern repeated too many times. |
| `10` | MQTT dependency or publishing failure. |
| `11` | Reserved for system-action failures; the current system-action runner logs failures without returning this code. |
| `12` | Explicit ZFS receive/create/write `out of space` or `No space left on device` failure. Stop without Broken Pipe retry or missing-dataset continuation; attempt configured failure notifications. |
| `13` | The selected TOML file is already locked by another Syncerate process. Duplicate launch stops and attempts configured failure email/MQTT. |
| `14` | The per-TOML lock file could not be safely created, opened, or used. Syncerate refuses to run without a lock, and attempts configured failure email/MQTT. |

Non-zero Syncoid exit codes not handled by a specific rule are returned unchanged and may overlap the application codes above. Signal termination is reported as `128 + signal number`.
