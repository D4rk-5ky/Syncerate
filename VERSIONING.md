# Syncerate versioning

Syncerate uses three-part versions in the form:

```text
major.minor.patch
```

Every created release increments by exactly `0.0.1` unless a larger version change is explicitly requested.

The patch number rolls over as follows:

```text
0.0.98 -> 0.0.99 -> 0.1.0
```

It must never become `0.0.100`.

## 0.4.20

Previous version: `0.4.19`.

- Separated structured JSON MQTT status from the original retained MQTT topic by adding dedicated `mqtt_json_topic`.
- JSON status is now an independent channel controlled by `MQTT_JSON_Status`; it may run alongside the original MQTT/Home Assistant outputs or by itself while `Use_MQTT = No`.
- Every JSON success/failure publish hard-codes `retain=False`; there is no JSON retain configuration option.
- Preserved the original `Use_MQTT` behavior unchanged: successful runs publish the configured `mqtt_message` retained to `mqtt_topic`.
- Preserved the original `Use_HomeAssistant` behavior unchanged: when enabled with legacy MQTT, successful runs additionally publish retained payload `online` to `HomeAssistant_Available`.
- Fatal failure reporting publishes only to the independent JSON channel; the historical success-only MQTT and Home Assistant availability signals are not emitted as failure reports.
- Added validation preventing an enabled JSON topic from matching the retained legacy `mqtt_topic` or retained `HomeAssistant_Available` topic.
- Updated the supplied Home Assistant JSON automation to listen on dedicated `/json-status` topics so it cannot consume the retained legacy channels by mistake.
- Updated `README.md`, `commented_code_map.md`, `config/example-Syncerate.cfg`, and version metadata for the independent MQTT channel behavior.
- Preserved replication, stale-resume recovery, Broken Pipe handling, SSH authentication, email, system action, dataset validation, and existing exit-code behavior.

## 0.4.19

- Updated `.gitignore` to ignore private `*.cfg` / `*.conf` files, configured source/destination list patterns, runtime logs/output, Python/build caches, temporary files, and local editor metadata while preserving the shipped example configuration.
- No Syncerate runtime behavior changed in this release.

## 0.4.18

Previous version: `0.4.17`.

- Removed Syncerate's automatic stale-resume retry that modified the Syncoid command with `--no-resume`.
- When Syncoid reports that the source snapshot used by an interrupted resumable receive no longer exists, Syncerate now keeps the same Syncoid process alive so Syncoid can run its own receive-state recovery.
- Added dedicated recognition of Syncoid's `resetting partially receive state because the snapshot source no longer exists` warning and report it to terminal/log as a nonfatal recovery action instead of treating it as a generic fatal warning.
- Added explicit recovery-state tracking so `Broken pipe` from the failed resume pipeline is logged as an expected secondary symptom and does not trigger `RetryBrokenPipe` while Syncoid is resetting the stale receive state.
- Added recognition of the replacement `INFO: Sending incremental` / `INFO: Sending full` stage; once it appears, Syncerate logs that stale receive recovery completed and restores normal Broken Pipe handling for the new transfer.
- Removed the obsolete `retry_without_resume` field and one-time resume-retry control flow from `SyncoidAttemptResult` and `run_replications()`.
- Corrected the private-agent command hardening call to pass the `SSHAgentSession` exactly once; this was found by release verification and avoids a runtime argument-count failure when `UseSSHAgent = Yes`.
- Updated `README.md`, `commented_code_map.md`, `config/example-Syncerate.cfg`, and version metadata for the current recovery behavior.
- Preserved dataset validation, SSH authentication modes, private-agent cleanup, normal Broken Pipe retry/exhaustion behavior, missing-destroy-snapshot handling, notifications, MQTT JSON security behavior, system action, and existing exit-code handling.

## 0.4.17

Previous version: `0.4.16`.

- Removed the configured `SyncoidCommand` from structured MQTT JSON status payloads so executed replication command details, endpoints, key paths, and command options are not deliberately exposed to MQTT subscribers.
- Added explicit JSON `title`, sourced from the existing `BackupTitle` configuration value with `Syncerate` as the fallback.
- Kept JSON `name` as a compatibility alias carrying the same title value so existing consumers that already read `name` do not break.
- Updated `config/HomeAssistant-Automation-For-MQTT-JSON.yaml` to prefer JSON `title`, fall back through `name`/`job`, and remove all executed-command text from success and failure Pushover messages.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the current MQTT JSON security behavior.
- Preserved JSON success/failure semantics, non-retained status publishing, Broken Pipe warning detail, bounded stderr/output, legacy retained MQTT mode, Home Assistant availability, SSH authentication modes, replication behavior, and exit-code handling.

## 0.4.16

Previous version: `0.4.15`.

- Added optional `MQTT_JSON_Status`, disabled by default so the existing retained `mqtt_message` success-only behavior remains unchanged unless explicitly enabled.
- When JSON status mode is enabled, the configured `mqtt_topic` receives non-retained JSON on successful replication completion and on fatal Syncerate failures that occur after configuration has loaded.
- JSON payloads include `status`, Boolean `success`, `name`, `job`, `command`, `exit_code`, `error`, bounded `stderr`, `warning`, and `skipped_datasets`.
- Broken Pipe warning-success runs remain `status: success`, set `warning: true`, and include the skipped dataset pairs.
- JSON status messages are deliberately non-retained so an old success cannot retrigger a Home Assistant automation after Home Assistant or an MQTT subscriber reconnects. The existing Home Assistant availability payload remains retained.
- Added best-effort MQTT failure reporting that preserves the original application exit code if publishing the failure report also fails. MQTT-originated failures do not recursively try to report themselves over MQTT.
- Added `config/HomeAssistant-Automation-For-MQTT-JSON.yaml` with five MQTT triggers and explicit success, failure, and default unknown branches. The duplicate MSI trigger IDs from the supplied automation were replaced with unique `msi_z170` and `msi_z87` IDs.
- Updated the Home Assistant example to use current MQTT trigger YAML with `topic` directly under each MQTT trigger and to consume `trigger.payload_json`.
- Updated `README.md`, `commented_code_map.md`, `config/example-Syncerate.cfg`, compatibility exports, and current version metadata.
- Preserved SSH-agent, legacy Pexpect authentication, Broken Pipe retry, resume, dataset validation, email, system action, legacy MQTT, Home Assistant availability, and exit-code behavior outside the new opt-in JSON mode.

## 0.4.15

Previous version: `0.4.14`.

- Added optional `UseSSHAgent` authentication mode, disabled by default so existing installations retain the legacy Pexpect-through-Syncoid behavior unless explicitly enabled.
- Added `SSHAgentKeyLifetimeSeconds`, defaulting to `3600`, and require it to be a positive whole number.
- Private-agent mode reuses the identity already configured in `SyncoidCommand --sshkey`; it fails before replication if agent mode is enabled without a usable key path or without `ssh-agent`/`ssh-add`.
- Added one isolated foreground `ssh-agent` per Syncerate run with a random mode-`0700` temporary directory, a dedicated mode-`0600` Unix socket, no inherited `SSH_AUTH_SOCK`/`SSH_AGENT_PID`, and no inherited `SSH_ASKPASS`.
- Added direct Pexpect control of `ssh-add` for encrypted-key passphrase entry. This uses the same direct `Pexpect -> OpenSSH` relationship that was verified to work on Ubuntu 26.04, instead of trying to type the passphrase through the nested `Syncoid -> ssh` process chain.
- Added a bounded OpenSSH identity lifetime and a pre-dataset identity check. If the private agent becomes empty after the lifetime expires, Syncerate reloads the same key before starting the next dataset.
- Hardened Syncoid SSH only while private-agent mode is enabled by prepending `ForwardAgent=no`, `StrictHostKeyChecking=yes`, `IdentitiesOnly=yes`, the exact private `IdentityAgent` socket, `AddKeysToAgent=no`, `BatchMode=yes`, and `PreferredAuthentications=publickey`. This prevents agent forwarding, automatic host-key trust, and interactive account-password fallback in agent mode.
- Private-agent cleanup removes identities with `ssh-add -D`, terminates the foreground agent, escalates to kill only when needed, and removes the temporary socket directory in a context-manager `finally` block.
- Preserved the existing `send_secret()`/Pexpect prompt path when `UseSSHAgent` is disabled, including `PassWord = No` safety behavior.
- Preserved Broken Pipe retry, resume, warning, notification, system-action, dataset validation, and exit-code behavior.
- Restored original project files `_config.yaml` and `_layouts/default.html`, which were missing from the 0.4.14 archive, without changing their contents.
- Updated `README.md`, `commented_code_map.md`, `config/example-Syncerate.cfg`, compatibility exports, and current version metadata.

## 0.4.14

Previous version: `0.4.13`.

- Added shared `send_secret()` handling for both SSH account-password prompts and encrypted private-key passphrase prompts.
- Before sending either credential, Syncerate now calls `child.waitnoecho(timeout=3)` so newer OpenSSH versions have time to finish switching the pseudo-terminal into no-echo credential-input mode.
- If no-echo is not observed within the 3-second timeout, the credential is still sent, preserving the previous behavior as a fallback.
- Pexpect output logging is disabled while waiting for and sending the secret, then restored in a `finally` block so credentials are not intentionally written to the `.out` logfile and logging is restored even if the operation raises.
- Kept `PassWord = No` safety behavior unchanged: an unexpected password/passphrase prompt remains a fatal authentication error instead of waiting indefinitely.
- Preserved all 0.4.13 Broken Pipe retry, retry-count, retry-wait, dataset continuation, warning-success, Syncoid warning, resume, exit-code, notification, and system-action behavior.
- Re-exported `send_secret()` from the compatibility `Syncerate.py` entry point alongside the other Syncoid-runner helpers.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the current credential-input behavior and version.

## 0.4.13

Previous version: `0.4.12`.

- Added optional `BrokenPipeRetryCount` configuration directly below `RetryBrokenPipe`.
- The value is the number of retries allowed after the initial attempt for each individual dataset pair.
- The retry counter is created inside the per-dataset loop, so every dataset starts with the full configured allowance.
- The option defaults to `1` when omitted, preserving the previous one-retry behavior.
- `0` skips an affected dataset immediately after its first detected Broken Pipe. Negative values and non-integers are rejected as configuration errors.
- `BrokenPipeRetryWaitSeconds` now applies before every configured Broken Pipe retry rather than describing only one retry.
- When a dataset exhausts its retries, only that dataset is skipped; the remaining dataset list continues and each later dataset receives its own retry count.
- Preserved the successful final exit code and exact warning-success mail subject when no other fatal error occurs.
- Updated terminal, log, output, and email wording so it reports retry exhaustion rather than assuming exactly two Broken Pipe occurrences.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for all 22 current configuration options.

## 0.4.12

Previous version: `0.4.11`.

- Added optional `BrokenPipeRetryWaitSeconds` configuration directly below `RetryBrokenPipe` in the example configuration.
- The option controls how many whole seconds Syncerate waits before the one allowed Broken Pipe retry.
- The option defaults to `10` when omitted, preserving the previous behavior.
- `0` is accepted for an immediate retry. Negative values and non-integers are rejected as configuration errors.
- Updated warning-success email text to report the configured wait time instead of a hard-coded value.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the new option.
- Preserved the existing second-Broken-Pipe behavior, successful warning result, dataset-list continuation, exit code, and mail subject.

## 0.4.11

Previous version: `0.4.10`.

- Added a fixed 10-second wait before retrying a dataset after the first detected Broken Pipe.
- The wait occurs only when `RetryBrokenPipe` is enabled and only before the one allowed retry for that dataset pair.
- A second Broken Pipe still skips only the affected dataset, continues the remaining list, keeps the completed run successful when no other fatal error occurs, and uses the existing warning-success email subject.
- Updated the warning-success email body, `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` to explain the delay.
- Preserved all other Syncoid warning, retry, exit-code, notification, and safety behavior.

## 0.4.10

Previous version: `0.4.9`.

- Added optional `RetryBrokenPipe` configuration, disabled by default.
- Added case-insensitive detection of `Broken pipe` in Syncoid output.
- When enabled, the first Broken Pipe stops the current attempt and retries the same dataset pair once with the same effective command.
- If Broken Pipe appears on the retry, the affected dataset pair is recorded as skipped and Syncerate continues with the remaining dataset list.
- Kept the final process exit code successful (`0`) when the list completes and no other fatal error occurs.
- Added `ReplicationSummary` to carry nonfatal skipped-dataset information from the Syncoid runner to final notification handling.
- Added `broken_pipe_detected` to `SyncoidAttemptResult` so the process monitor returns the condition explicitly instead of using global state.
- Added warning-success logging to the terminal, `.log`, and `.out` output.
- Added the exact warning-success email subject `Syncerate Succsful - WARNING BROKEN PIPE` and included skipped dataset pairs in the email body.
- Preserved normal Syncoid exit-status behavior when `RetryBrokenPipe` is disabled or omitted.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the new option and behavior.

## 0.4.9

Previous version: `0.4.8`.

- Restored a prominent disclaimer and liability notice to `README.md`.
- Added an explicit AI-assisted / vibe-coded experimental-software warning.
- Tailored the risk description to Syncerate's actual behavior: Syncoid/ZFS replication, snapshots, target datasets, interrupted-receive handling, optional destructive Syncoid arguments, and the configured shell `SystemAction`.
- Clarified that Syncerate has no application-level dry-run mode.
- Added practical safeguards: inspect the command and dataset pairs, test with non-critical datasets, keep a separate verified backup, limit permissions, and verify logs and destination state.
- Updated current-version references to `0.4.9`.
- No application behavior or command handling was changed.

## 0.4.8

Previous version: `0.4.7`.

- Rewrote `README.md` as a current how-to guide for installing, configuring, and running Syncerate.
- Removed historical-version references and explanations that were only relevant to earlier implementations.
- Audited the README against `syncerate/cli.py`, `syncerate/config.py`, `syncerate/notifications.py`, `syncerate/datasets.py`, and `syncerate/syncoid_runner.py`.
- Documented every current command-line option: `-c` / `--conf`, `-h` / `--help`, and `--version`.
- Documented all 19 current configuration options and when each option is required or read.
- Corrected the required-option descriptions to match the loader: `Mail`, `PassWord`, `DateTime`, `LogDestination`, and `SystemAction` must remain present even when configured as `No`.
- Expanded practical explanations for source/destination pairing, per-destination Syncoid arguments, local and remote execution users, password handling, logging, email, MQTT, Home Assistant, system actions, safety behavior, and exit codes.
- Updated current-version references to `0.4.8`.
- No application behavior or command handling was changed.

## 0.4.7

Previous version: `0.4.6`.

- Split the application implementation from the single `Syncerate.py` file into the requested `syncerate/` package.
- Added `syncerate/__init__.py` as the single source of the application version.
- Added `syncerate/app.py` for application orchestration, successful-run processing, final error logging, and the top-level `main()` exception boundary.
- Added `syncerate/cli.py` for `argparse` command-line handling.
- Added `syncerate/config.py` for INI loading and optional Boolean normalization.
- Added `syncerate/datasets.py` for source/destination list parsing, validation, and `DatasetPair` creation.
- Added `syncerate/errors.py` for exit-code constants and `SyncerateError`.
- Added `syncerate/logging_setup.py` for timestamp creation, log paths, logger handlers, and safe startup configuration logging.
- Added `syncerate/models.py` for `AppConfig`, `RunContext`, `DatasetPair`, and `SyncoidAttemptResult`.
- Added `syncerate/notifications.py` for email, MQTT, Home Assistant MQTT availability, and error-mail handling.
- Added `syncerate/syncoid_runner.py` for password resolution, Syncoid command construction, `pexpect` monitoring, retries, and replication execution.
- Added `syncerate/system_actions.py` for the optional successful-run system command.
- Reduced `Syncerate.py` to an executable compatibility entry point that imports and re-exports the existing public classes, constants, and functions.
- Preserved the existing command line: `./Syncerate.py --conf ...`, `--help`, and `--version`.
- Preserved the version 0.4.6 runtime-state objects and kept importing both `Syncerate.py` and the package free of application startup work.
- Preserved lazy `paho-mqtt` loading and lazy Home Assistant configuration access.
- Preserved all dataset validation, Syncoid output matching, one-time `--no-resume` retry, unavailable-resume continuation, missing-destroy-snapshot handling, local effective-user behavior, remote SSH-user behavior, notification ordering, and exit codes.
- Updated `README.md`, `VERSIONING.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the modular application.

## 0.4.6

Previous version: `0.4.5`.

- Corrected the current release number to `0.4.6` so the project continues from version `0.4.5` without reusing an already-created version number.
- Updated `Syncerate.py`, `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` so every current-version reference is `0.4.6`.
- Rebuilt and reverified the complete project package.
- No application behavior was changed from version `0.4.5`.

## 0.4.5

- Completed the single-file runtime-state refactor while keeping all application code in `Syncerate.py`.
- Moved command-line parsing, configuration loading, timestamp creation, logger setup, dataset loading, password resolution, replication startup, success handling, and top-level error handling into `main()` and functions called by it.
- Made importing `Syncerate.py` side-effect free: importing defines constants, dataclasses, exceptions, and functions only; it does not require `--conf`, read files, create logs, ask for a password, or start Syncoid.
- Added `AppConfig` to carry configuration values explicitly instead of using runtime configuration globals.
- Added `RunContext` to carry the per-run timestamp and optional `.log`, `.err`, and `.out` paths.
- Added `DatasetPair` to keep each validated source, destination, and per-destination argument set together.
- Added `SyncoidAttemptResult` to return the child process, modified command, repeat state, resume-retry request, and known missing-destroy-snapshot state explicitly.
- Removed runtime globals including parsed arguments, raw configuration state, source/destination lists, resolved passwords, timestamp/log paths, and Syncoid control flags.
- Replaced internal `sys.exit()` calls in list validation, Syncoid monitoring, MQTT handling, mail handling, and error handling with `SyncerateError` exceptions or explicit result objects.
- Kept `sys.exit(main())` only at the executable program boundary.
- Preserved existing exit codes, command construction, source/destination validation, password behavior, lazy MQTT/HA behavior, notification order, one-time `--no-resume` retry, the exact nonfatal unavailable-resume warning, generic warning failure, known missing-destroy-snapshot handling, local effective-user behavior, and remote SSH-user behavior.
- Updated `README.md`, `commented_code_map.md`, and `config/example-Syncerate.cfg` for the refactored application behavior.

## 0.4.4

- Created the first intermediate build of the single-file runtime-state refactor.
- Began moving startup work into `main()` and replacing runtime globals with explicit state objects.
- This intermediate build was completed and fully documented in version `0.4.5`.

## 0.4.3

- Kept local Syncoid and ZFS execution under the effective user that starts `Syncerate.py`; no alternate local account is introduced.
- Added logging of the effective local username and UID before every Syncoid process starts.
- Documented that remote ZFS commands use the SSH user written in the remote source or destination endpoint.
- Added a dedicated handler for Syncoid's exact nonfatal `ZFS resume feature not available ... sync will continue without resume support` message.
- Changed that exact resume-capability message from fatal exit code `4` to a logged warning that waits for Syncoid's real final exit status.
- Kept unrelated Syncoid warnings fatal and preserved the existing resume-retry, authentication, dataset, repeated-pattern, and missing-destroy-snapshot safety behavior.
- Updated `README.md`, `commented_code_map.md`, and the example configuration for current version `0.4.3` behavior.

## 0.4.2

- Removed the GitHub Pages configuration file `_config.yaml` from the distributed project.
- Removed the GitHub Pages layout file `_layouts/default.html` from the distributed project.
- Kept all application, configuration, Home Assistant reference, and documentation files unchanged except for version references.
- Updated application and documentation version references to `0.4.2`.

## 0.4.1

- Removed the unconditional top-level `paho-mqtt` import.
- Added a lazy `paho-mqtt` import inside `send_mqtt_messages()` so the dependency is loaded only when MQTT publishing actually runs.
- Added a clear MQTT exit-code `10` error when MQTT is enabled but `paho-mqtt` is unavailable.
- Made `Use_MQTT` optional with a safe disabled fallback.
- Added support for `No`, `False`, `0`, and `Off` as disabled MQTT and Home Assistant values.
- Made `Use_HomeAssistant` optional.
- Moved Home Assistant option loading into the successful MQTT publishing path.
- Prevented Home Assistant configuration from being accessed during normal startup and configuration logging.
- Kept the Home Assistant availability topic unread unless Home Assistant support is enabled.
- Prevented disabled MQTT integration settings from being accessed for configuration logging.
- Added the application version constant and the `--version` command.
- Updated `config/example-Syncerate.cfg` with all available options and disabled MQTT and Home Assistant defaults.
- Replaced `README.md` with documentation for current application behavior only.
- Added `commented_code_map.md` describing every function, execution stage, command, and safety-related branch.
- Expanded `.gitignore` for Python bytecode, build caches, test caches, and temporary files.

## 0.4.0

Baseline version supplied for this work.

Observed baseline capabilities:

- Reads paired source and destination ZFS dataset lists.
- Validates equal list lengths and matching final dataset names.
- Builds safe argument-list Syncoid commands from `SourceDataSet` and `DestDataSet` placeholders.
- Supports dataset names containing spaces.
- Supports per-destination extra Syncoid arguments.
- Executes Syncoid through `pexpect` and handles known SSH, password, warning, resume, and connection patterns.
- Supports optional logs, email notifications, MQTT publishing, Home Assistant MQTT availability, and a successful-run system action.
