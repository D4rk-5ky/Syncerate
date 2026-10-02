"""TOML configuration loading and validation for Syncerate."""

import shlex
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - Python < 3.11 guard
    raise RuntimeError(
        "Syncerate requires Python 3.11 or newer for built-in TOML support"
    ) from exc

from .models import AppConfig


CONFIG_OPTION_LOCATIONS = {
    "backup": ("BackupTitle", "BackupComment"),
    "syncoid": (
        "SourceListPath",
        "DestListPath",
        "SyncoidCommand",
    ),
    "ssh": ("PassWord", "UseSSHAgent", "SSHAgentKeyLifetimeSeconds"),
    "mail": ("Mail", "SendMailOnSuccess"),
    "mqtt": (
        "Use_MQTT",
        "SendMQTTOnSuccess",
        "broker_address",
        "broker_port",
        "mqtt_username",
        "mqtt_password",
        "mqtt_topic",
        "mqtt_message",
        "MQTT_JSON_Status",
        "mqtt_json_topic",
    ),
    "home_assistant": ("Use_HomeAssistant", "HomeAssistant_Available"),
    "logging": ("DateTime", "LogDestination"),
    "runtime": (
        "DryRun",
        "SystemAction",
        "ContinueOnMissingDataset",
        "ContinueWithoutResume",
        "RetryBrokenPipe",
        "BrokenPipeRetryCount",
        "BrokenPipeRetryWaitSeconds",
    ),
}

# Keep startup logging order in the same ownership order as the schema/example.
CONFIG_SECTIONS = tuple(CONFIG_OPTION_LOCATIONS)

# Kept as a small compatibility helper for code importing it from older releases.
# The TOML loader itself requires native true/false values and does not use this.
_ENABLED_VALUES = {"YES", "TRUE", "1", "ON"}


def option_is_enabled(value: Any) -> bool:
    """Return True for legacy text values that represented an enabled option."""

    return str(value).strip().upper() in _ENABLED_VALUES


def validate_syncoid_command_template(command_template: str) -> None:
    """Validate command syntax and require exactly one source/destination placeholder."""

    if not command_template.strip():
        raise ValueError("SyncoidCommand must not be empty")

    try:
        command_parts = shlex.split(command_template)
    except ValueError as exc:
        raise ValueError(f"Could not parse SyncoidCommand: {exc}") from exc

    if not command_parts:
        raise ValueError("SyncoidCommand must contain an executable command")

    source_count = sum(part.count("SourceDataSet") for part in command_parts)
    destination_count = sum(part.count("DestDataSet") for part in command_parts)

    if source_count != 1 or destination_count != 1:
        raise ValueError(
            "SyncoidCommand must contain exactly one SourceDataSet placeholder "
            "and exactly one DestDataSet placeholder"
        )


def _section(raw_config: dict[str, Any], name: str) -> dict[str, Any]:
    """Return one TOML table as a dictionary, treating an omitted table as empty."""

    value = raw_config.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    return value


def _required_text(section: dict[str, Any], section_name: str, option_name: str) -> str:
    """Return one required non-empty string from a TOML table."""

    if option_name not in section:
        raise ValueError(f"{section_name}.{option_name} is required")
    value = section[option_name]
    if not isinstance(value, str):
        raise ValueError(f"{section_name}.{option_name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{section_name}.{option_name} must not be empty")
    return value


def _optional_text(
    section: dict[str, Any],
    section_name: str,
    option_name: str,
    *,
    fallback: str = "",
    strip: bool = True,
) -> str:
    """Return an optional string while rejecting non-string TOML values."""

    if option_name not in section:
        return fallback
    value = section[option_name]
    if not isinstance(value, str):
        raise ValueError(f"{section_name}.{option_name} must be a string")
    return value.strip() if strip else value


def _boolean(
    section: dict[str, Any],
    section_name: str,
    option_name: str,
    *,
    fallback: bool = False,
) -> bool:
    """Return one native TOML Boolean and reject quoted/string substitutes."""

    if option_name not in section:
        return fallback
    value = section[option_name]
    if type(value) is not bool:
        raise ValueError(
            f"{section_name}.{option_name} must be a TOML boolean: true or false"
        )
    return value


def _integer(
    section: dict[str, Any],
    section_name: str,
    option_name: str,
    *,
    fallback: int,
) -> int:
    """Return one TOML integer while rejecting booleans/floats/strings."""

    if option_name not in section:
        return fallback
    value = section[option_name]
    if type(value) is not int:
        raise ValueError(f"{section_name}.{option_name} must be a whole number")
    return value


def load_app_config(config_path: str) -> AppConfig:
    """Read the TOML file, validate startup settings, and return AppConfig."""

    path = Path(config_path)
    try:
        with path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Could not read config file: {config_path}")
    except OSError:
        raise
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML configuration: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ValueError("The TOML root must contain configuration tables")

    backup = _section(raw_config, "backup")
    syncoid = _section(raw_config, "syncoid")
    ssh = _section(raw_config, "ssh")
    mail = _section(raw_config, "mail")
    logging_section = _section(raw_config, "logging")
    runtime = _section(raw_config, "runtime")
    mqtt = _section(raw_config, "mqtt")
    home_assistant = _section(raw_config, "home_assistant")

    moved_runtime_options = (
        "ContinueWithoutResume",
        "RetryBrokenPipe",
        "BrokenPipeRetryCount",
        "BrokenPipeRetryWaitSeconds",
    )
    misplaced_runtime_options = [
        option for option in moved_runtime_options if option in syncoid
    ]
    if misplaced_runtime_options:
        names = ", ".join(f"syncoid.{option}" for option in misplaced_runtime_options)
        raise ValueError(
            f"{names} moved to the [runtime] table in Syncerate 0.4.42"
        )

    source_list_path = _required_text(syncoid, "syncoid", "SourceListPath")
    destination_list_path = _required_text(syncoid, "syncoid", "DestListPath")
    syncoid_command = _required_text(syncoid, "syncoid", "SyncoidCommand")
    validate_syncoid_command_template(syncoid_command)

    password_option = _required_text(ssh, "ssh", "PassWord")
    mail_option = _required_text(mail, "mail", "Mail")
    datetime_format = _required_text(logging_section, "logging", "DateTime")
    log_destination_text = _required_text(
        logging_section, "logging", "LogDestination"
    )
    system_option = _required_text(runtime, "runtime", "SystemAction")

    if log_destination_text.upper() == "NO":
        log_destination = None
    else:
        log_destination = log_destination_text
        if not log_destination.endswith("/"):
            log_destination += "/"

    ssh_agent_key_lifetime_seconds = _integer(
        ssh,
        "ssh",
        "SSHAgentKeyLifetimeSeconds",
        fallback=3600,
    )
    if ssh_agent_key_lifetime_seconds <= 0:
        raise ValueError(
            "ssh.SSHAgentKeyLifetimeSeconds must be a positive whole number"
        )

    broken_pipe_retry_count = _integer(
        runtime,
        "runtime",
        "BrokenPipeRetryCount",
        fallback=1,
    )
    if broken_pipe_retry_count < 0:
        raise ValueError(
            "runtime.BrokenPipeRetryCount must be zero or a positive whole number"
        )

    broken_pipe_retry_wait_seconds = _integer(
        runtime,
        "runtime",
        "BrokenPipeRetryWaitSeconds",
        fallback=10,
    )
    if broken_pipe_retry_wait_seconds < 0:
        raise ValueError(
            "runtime.BrokenPipeRetryWaitSeconds must be zero or a positive whole number"
        )

    dry_run = _boolean(runtime, "runtime", "DryRun")
    continue_on_missing_dataset = _boolean(
        runtime, "runtime", "ContinueOnMissingDataset"
    )
    continue_without_resume = _boolean(
        runtime,
        "runtime",
        "ContinueWithoutResume",
        fallback=True,
    )
    retry_broken_pipe = _boolean(runtime, "runtime", "RetryBrokenPipe")
    use_ssh_agent = _boolean(ssh, "ssh", "UseSSHAgent")
    send_mail_on_success = _boolean(
        mail,
        "mail",
        "SendMailOnSuccess",
        fallback=True,
    )
    use_mqtt = _boolean(mqtt, "mqtt", "Use_MQTT")
    send_mqtt_on_success = _boolean(
        mqtt,
        "mqtt",
        "SendMQTTOnSuccess",
        fallback=True,
    )
    mqtt_json_status = _boolean(mqtt, "mqtt", "MQTT_JSON_Status")
    use_home_assistant = _boolean(
        home_assistant,
        "home_assistant",
        "Use_HomeAssistant",
    )

    broker_address = _optional_text(mqtt, "mqtt", "broker_address")
    broker_port = _integer(mqtt, "mqtt", "broker_port", fallback=1883)
    mqtt_username = _optional_text(mqtt, "mqtt", "mqtt_username")
    mqtt_password = _optional_text(
        mqtt, "mqtt", "mqtt_password", strip=False
    )
    mqtt_topic = _optional_text(mqtt, "mqtt", "mqtt_topic")
    mqtt_message = _optional_text(
        mqtt, "mqtt", "mqtt_message", strip=False
    )
    mqtt_json_topic = _optional_text(mqtt, "mqtt", "mqtt_json_topic")
    home_assistant_available = _optional_text(
        home_assistant,
        "home_assistant",
        "HomeAssistant_Available",
    )

    if use_mqtt or mqtt_json_status:
        if not broker_address:
            raise ValueError(
                "mqtt.broker_address must be configured when MQTT publishing is enabled"
            )
        if not 1 <= broker_port <= 65535:
            raise ValueError("mqtt.broker_port must be between 1 and 65535")

    if use_mqtt:
        if not mqtt_topic:
            raise ValueError(
                "mqtt.mqtt_topic must be configured when mqtt.Use_MQTT is enabled"
            )
        if "mqtt_message" not in mqtt:
            raise ValueError(
                "mqtt.mqtt_message must be configured when mqtt.Use_MQTT is enabled"
            )
        if use_home_assistant and not home_assistant_available:
            raise ValueError(
                "home_assistant.HomeAssistant_Available must be configured when "
                "mqtt.Use_MQTT and home_assistant.Use_HomeAssistant are enabled"
            )

    if mqtt_json_status:
        if not mqtt_json_topic:
            raise ValueError(
                "mqtt.mqtt_json_topic must be configured when mqtt.MQTT_JSON_Status is enabled"
            )
        if use_mqtt and mqtt_json_topic == mqtt_topic:
            raise ValueError(
                "mqtt.mqtt_json_topic must be different from the legacy mqtt.mqtt_topic"
            )
        if (
            use_mqtt
            and use_home_assistant
            and mqtt_json_topic == home_assistant_available
        ):
            raise ValueError(
                "mqtt.mqtt_json_topic must be different from "
                "home_assistant.HomeAssistant_Available"
            )

    return AppConfig(
        config_path=config_path,
        raw_config=raw_config,
        mail_option=mail_option,
        system_option=system_option,
        use_mqtt=use_mqtt,
        datetime_format=datetime_format,
        log_destination=log_destination,
        backup_title=_optional_text(backup, "backup", "BackupTitle"),
        backup_comment=_optional_text(
            backup, "backup", "BackupComment", strip=False
        ).strip(),
        source_list_path=source_list_path,
        destination_list_path=destination_list_path,
        password_option=password_option,
        syncoid_command=syncoid_command,
        dry_run=dry_run,
        send_mail_on_success=send_mail_on_success,
        send_mqtt_on_success=send_mqtt_on_success,
        mqtt_json_status=mqtt_json_status,
        use_home_assistant=use_home_assistant,
        use_ssh_agent=use_ssh_agent,
        ssh_agent_key_lifetime_seconds=ssh_agent_key_lifetime_seconds,
        retry_broken_pipe=retry_broken_pipe,
        continue_on_missing_dataset=continue_on_missing_dataset,
        continue_without_resume=continue_without_resume,
        broken_pipe_retry_count=broken_pipe_retry_count,
        broken_pipe_retry_wait_seconds=broken_pipe_retry_wait_seconds,
        broker_address=broker_address,
        broker_port=broker_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_topic=mqtt_topic,
        mqtt_message=mqtt_message,
        mqtt_json_topic=mqtt_json_topic,
        home_assistant_available=home_assistant_available,
    )
