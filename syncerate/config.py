"""Configuration-file loading, validation, and Boolean option normalization."""

import configparser
import shlex
from typing import Any

from .models import AppConfig

CONFIG_SECTION = "Syncerate Config"

_ENABLED_VALUES = {"YES", "TRUE", "1", "ON"}
_DISABLED_VALUES = {"NO", "FALSE", "0", "OFF"}


def option_is_enabled(value: Any) -> bool:
    """Return True for supported enabled values used in the config file."""

    return str(value).strip().upper() in _ENABLED_VALUES


def parse_boolean_option(
    raw_config: configparser.RawConfigParser,
    option_name: str,
    *,
    fallback: str = "No",
) -> bool:
    """Read one documented Boolean option and reject ambiguous/typo values."""

    value = raw_config.get(CONFIG_SECTION, option_name, fallback=fallback)
    normalized = value.strip().upper()

    if normalized in _ENABLED_VALUES:
        return True
    if normalized in _DISABLED_VALUES:
        return False

    raise ValueError(
        f"{option_name} must be one of: Yes, No, True, False, 1, 0, On, Off"
    )


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


def _required_text(
    raw_config: configparser.RawConfigParser,
    option_name: str,
) -> str:
    """Return one required non-empty configuration value."""

    value = raw_config.get(CONFIG_SECTION, option_name).strip()
    if not value:
        raise ValueError(f"{option_name} must not be empty")
    return value


def load_app_config(config_path: str) -> AppConfig:
    """Read the INI file, validate startup settings, and return AppConfig."""

    raw_config = configparser.RawConfigParser()
    loaded_files = raw_config.read(config_path)

    if not loaded_files:
        raise FileNotFoundError(f"Could not read config file: {config_path}")

    if not raw_config.has_section(CONFIG_SECTION):
        raise configparser.NoSectionError(CONFIG_SECTION)

    mail_option = _required_text(raw_config, "Mail")
    system_option = _required_text(raw_config, "SystemAction")
    datetime_format = _required_text(raw_config, "DateTime")
    source_list_path = _required_text(raw_config, "SourceListPath")
    destination_list_path = _required_text(raw_config, "DestListPath")
    password_option = _required_text(raw_config, "PassWord")
    syncoid_command = _required_text(raw_config, "SyncoidCommand")
    validate_syncoid_command_template(syncoid_command)

    log_destination_text = _required_text(raw_config, "LogDestination")

    if log_destination_text.upper() == "NO":
        log_destination = None
    else:
        log_destination = log_destination_text
        if not log_destination.endswith("/"):
            log_destination += "/"

    ssh_agent_key_lifetime_seconds = raw_config.getint(
        CONFIG_SECTION,
        "SSHAgentKeyLifetimeSeconds",
        fallback=3600,
    )

    if ssh_agent_key_lifetime_seconds <= 0:
        raise ValueError(
            "SSHAgentKeyLifetimeSeconds must be a positive whole number"
        )

    broken_pipe_retry_count = raw_config.getint(
        CONFIG_SECTION,
        "BrokenPipeRetryCount",
        fallback=1,
    )

    if broken_pipe_retry_count < 0:
        raise ValueError(
            "BrokenPipeRetryCount must be zero or a positive whole number"
        )

    broken_pipe_retry_wait_seconds = raw_config.getint(
        CONFIG_SECTION,
        "BrokenPipeRetryWaitSeconds",
        fallback=10,
    )

    if broken_pipe_retry_wait_seconds < 0:
        raise ValueError(
            "BrokenPipeRetryWaitSeconds must be zero or a positive whole number"
        )

    use_mqtt = parse_boolean_option(raw_config, "Use_MQTT")
    mqtt_json_status = parse_boolean_option(raw_config, "MQTT_JSON_Status")
    use_home_assistant = parse_boolean_option(raw_config, "Use_HomeAssistant")
    use_ssh_agent = parse_boolean_option(raw_config, "UseSSHAgent")
    retry_broken_pipe = parse_boolean_option(raw_config, "RetryBrokenPipe")

    # The legacy MQTT/HA outputs and the JSON status output are independent.
    # Validate every enabled channel before replication begins so a typo or a
    # missing broker/topic cannot fail only after all datasets have been touched.
    legacy_mqtt_topic = ""
    home_assistant_available = ""

    if use_mqtt or mqtt_json_status:
        broker_address = raw_config.get(
            CONFIG_SECTION,
            "broker_address",
            fallback="",
        ).strip()
        if not broker_address:
            raise ValueError(
                "broker_address must be configured when MQTT publishing is enabled"
            )

        try:
            broker_port = raw_config.getint(CONFIG_SECTION, "broker_port")
        except (configparser.NoOptionError, ValueError) as exc:
            raise ValueError(
                "broker_port must be a whole number when MQTT publishing is enabled"
            ) from exc

        if not 1 <= broker_port <= 65535:
            raise ValueError("broker_port must be between 1 and 65535")

    if use_mqtt:
        legacy_mqtt_topic = raw_config.get(
            CONFIG_SECTION,
            "mqtt_topic",
            fallback="",
        ).strip()
        if not legacy_mqtt_topic:
            raise ValueError("mqtt_topic must be configured when Use_MQTT is enabled")

        # Require the option to exist even though an empty MQTT payload remains
        # valid and is therefore deliberately not rejected.
        if not raw_config.has_option(CONFIG_SECTION, "mqtt_message"):
            raise ValueError("mqtt_message must be configured when Use_MQTT is enabled")

        if use_home_assistant:
            home_assistant_available = raw_config.get(
                CONFIG_SECTION,
                "HomeAssistant_Available",
                fallback="",
            ).strip()
            if not home_assistant_available:
                raise ValueError(
                    "HomeAssistant_Available must be configured when "
                    "Use_MQTT and Use_HomeAssistant are enabled"
                )

    if mqtt_json_status:
        mqtt_json_topic = raw_config.get(
            CONFIG_SECTION,
            "mqtt_json_topic",
            fallback="",
        ).strip()
        if not mqtt_json_topic:
            raise ValueError(
                "mqtt_json_topic must be configured when MQTT_JSON_Status is enabled"
            )
        if use_mqtt and mqtt_json_topic == legacy_mqtt_topic:
            raise ValueError(
                "mqtt_json_topic must be different from the legacy mqtt_topic"
            )
        if (
            use_mqtt
            and use_home_assistant
            and mqtt_json_topic == home_assistant_available
        ):
            raise ValueError(
                "mqtt_json_topic must be different from HomeAssistant_Available"
            )

    return AppConfig(
        config_path=config_path,
        raw_config=raw_config,
        mail_option=mail_option,
        system_option=system_option,
        use_mqtt=use_mqtt,
        datetime_format=datetime_format,
        log_destination=log_destination,
        backup_title=raw_config.get(
            CONFIG_SECTION,
            "BackupTitle",
            fallback="",
        ).strip(),
        backup_comment=raw_config.get(
            CONFIG_SECTION,
            "BackupComment",
            fallback="",
        ).strip(),
        source_list_path=source_list_path,
        destination_list_path=destination_list_path,
        password_option=password_option,
        syncoid_command=syncoid_command,
        mqtt_json_status=mqtt_json_status,
        use_home_assistant=use_home_assistant,
        use_ssh_agent=use_ssh_agent,
        ssh_agent_key_lifetime_seconds=ssh_agent_key_lifetime_seconds,
        retry_broken_pipe=retry_broken_pipe,
        broken_pipe_retry_count=broken_pipe_retry_count,
        broken_pipe_retry_wait_seconds=broken_pipe_retry_wait_seconds,
    )
