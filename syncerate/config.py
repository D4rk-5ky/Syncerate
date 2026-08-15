"""Configuration-file loading and Boolean option normalization."""

import configparser
from typing import Any

from .models import AppConfig

CONFIG_SECTION = "Syncerate Config"


def option_is_enabled(value: Any) -> bool:
    """Return True for supported enabled values used in the config file."""

    return str(value).strip().upper() in {"YES", "TRUE", "1", "ON"}

def load_app_config(config_path: str) -> AppConfig:
    """Read the INI file and return all startup settings as AppConfig."""

    raw_config = configparser.RawConfigParser()
    loaded_files = raw_config.read(config_path)

    if not loaded_files:
        raise FileNotFoundError(f"Could not read config file: {config_path}")

    if not raw_config.has_section(CONFIG_SECTION):
        raise configparser.NoSectionError(CONFIG_SECTION)

    log_destination_text = raw_config.get(
        CONFIG_SECTION,
        "LogDestination",
    ).strip()

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

    use_mqtt = option_is_enabled(
        raw_config.get(CONFIG_SECTION, "Use_MQTT", fallback="No")
    )
    mqtt_json_status = option_is_enabled(
        raw_config.get(CONFIG_SECTION, "MQTT_JSON_Status", fallback="No")
    )

    # The legacy MQTT/HA outputs and the JSON status output are independent.
    # Legacy behavior remains unchanged when Use_MQTT is enabled: the old
    # success-only mqtt_message is retained, and Use_HomeAssistant optionally
    # adds the retained availability message. JSON uses its own topic and is
    # always non-retained.
    legacy_mqtt_topic = ""
    use_home_assistant = False
    home_assistant_available = ""

    if use_mqtt:
        legacy_mqtt_topic = raw_config.get(
            CONFIG_SECTION, "mqtt_topic", fallback=""
        ).strip()
        use_home_assistant = option_is_enabled(
            raw_config.get(CONFIG_SECTION, "Use_HomeAssistant", fallback="No")
        )
        if use_home_assistant:
            home_assistant_available = raw_config.get(
                CONFIG_SECTION, "HomeAssistant_Available", fallback=""
            ).strip()

    if mqtt_json_status:
        mqtt_json_topic = raw_config.get(
            CONFIG_SECTION, "mqtt_json_topic", fallback=""
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
        mail_option=raw_config.get(CONFIG_SECTION, "Mail"),
        system_option=raw_config.get(CONFIG_SECTION, "SystemAction"),
        use_mqtt=use_mqtt,
        datetime_format=raw_config.get(CONFIG_SECTION, "DateTime"),
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
        source_list_path=raw_config.get(CONFIG_SECTION, "SourceListPath"),
        destination_list_path=raw_config.get(CONFIG_SECTION, "DestListPath"),
        password_option=raw_config.get(CONFIG_SECTION, "PassWord"),
        syncoid_command=raw_config.get(CONFIG_SECTION, "SyncoidCommand"),
        mqtt_json_status=mqtt_json_status,
        use_ssh_agent=option_is_enabled(
            raw_config.get(CONFIG_SECTION, "UseSSHAgent", fallback="No")
        ),
        ssh_agent_key_lifetime_seconds=ssh_agent_key_lifetime_seconds,
        retry_broken_pipe=option_is_enabled(
            raw_config.get(CONFIG_SECTION, "RetryBrokenPipe", fallback="No")
        ),
        broken_pipe_retry_count=broken_pipe_retry_count,
        broken_pipe_retry_wait_seconds=broken_pipe_retry_wait_seconds,
    )
