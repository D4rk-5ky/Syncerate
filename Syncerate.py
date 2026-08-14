#!/usr/bin/python3

"""Compatibility entry point for the modular Syncerate application.

All implementation code lives in the adjacent ``syncerate`` package. Importing
this file remains side-effect free, and existing imports of public names from
``Syncerate.py`` continue to work.
"""

import sys

from syncerate import VERSION, __version__
from syncerate.app import log_syncerate_error, main, successfull_run
from syncerate.cli import parse_arguments
from syncerate.config import CONFIG_SECTION, load_app_config, option_is_enabled
from syncerate.datasets import (
    load_dataset_pairs,
    missmatchinglists,
    parse_destination_line,
    parse_destination_list,
    read_dataset_list,
)
from syncerate.errors import (
    EXIT_CONNECTION_REFUSED,
    EXIT_CONNECTION_TIMEOUT,
    EXIT_DATASET_MISSING,
    EXIT_LIST_ERROR,
    EXIT_MQTT_ERROR,
    EXIT_OK,
    EXIT_PASSWORD_DENIED,
    EXIT_REPEATED_PATTERN,
    EXIT_SCRIPT_ERROR,
    EXIT_SYSTEM_ACTION_ERROR,
    EXIT_WARNING,
    SyncerateError,
)
from syncerate.logging_setup import (
    create_run_context,
    get_console_logger,
    get_logger,
    log_startup_configuration,
)
from syncerate.models import (
    AppConfig,
    DatasetPair,
    ReplicationSummary,
    RunContext,
    SyncoidAttemptResult,
)
from syncerate.notifications import (
    MailTo,
    WasMailSent,
    backup_header_text,
    send_error_mail,
    send_mail,
    send_mqtt_messages,
)
from syncerate.syncoid_runner import (
    build_syncoid_command,
    close_child_logfile,
    die,
    effective_user_name,
    log_command_debug,
    resolve_password,
    run_replications,
    safe_text,
    send_secret,
    ssh_command,
)
from syncerate.system_actions import SystemAction


if __name__ == "__main__":
    sys.exit(main())
