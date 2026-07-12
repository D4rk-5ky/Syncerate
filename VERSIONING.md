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
