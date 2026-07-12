"""Syncoid command construction, process monitoring, and safety handling."""

import logging
import os
import pwd
import shlex
from getpass import getpass
from typing import Any, Optional, Sequence

import pexpect

from .errors import (
    EXIT_CONNECTION_REFUSED,
    EXIT_CONNECTION_TIMEOUT,
    EXIT_DATASET_MISSING,
    EXIT_LIST_ERROR,
    EXIT_OK,
    EXIT_PASSWORD_DENIED,
    EXIT_REPEATED_PATTERN,
    EXIT_WARNING,
    SyncerateError,
)
from .models import AppConfig, DatasetPair, RunContext, SyncoidAttemptResult


def resolve_password(
    app_config: AppConfig,
    logger: logging.Logger,
) -> Optional[str]:
    """Resolve No, Ask, or a literal password/passphrase from the config."""

    password_option = app_config.password_option

    if password_option.upper() == "ASK":
        password = getpass("PLz. insert a desiret password if needed :    ")
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("The Password has been manualy added, not written to log")
        logger.info("")
        return password

    if password_option.upper() == "NO":
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("No password is in use")
        return None

    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("Password is in the config file, not written to log")
    return password_option

def safe_text(value: Any) -> str:
    """Convert optional pexpect output values to safe text."""

    if value is None:
        return ""
    return str(value)

def close_child_logfile(
    child: Any,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Flush and close a pexpect logfile without closing the child process."""

    if child is None:
        return

    logfile = getattr(child, "logfile", None)
    if logfile is None:
        return

    try:
        logfile.flush()
        logfile.close()
    except Exception:
        if logger is not None:
            logger.exception("Could not close pexpect logfile cleanly")
    finally:
        child.logfile = None

def die(
    child: Any = None,
    errstr: Optional[str] = None,
    error_code: Optional[int] = None,
    SynCoidFail: Optional[int] = None,
    MQTT_Fail: Optional[int] = None,
    SynCoidFailChild: Any = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Convert the old internal exit paths into one SyncerateError exception."""

    if error_code is not None:
        exit_code = int(error_code)
    elif SynCoidFail is not None:
        exit_code = int(SynCoidFail)
    elif MQTT_Fail is not None:
        exit_code = int(MQTT_Fail)
    else:
        exit_code = EXIT_LIST_ERROR

    if child is not None:
        child_before = safe_text(getattr(child, "before", ""))
        child_warning = safe_text(getattr(child, "after", "")) + safe_text(
            getattr(child, "buffer", "")
        )

        try:
            child.terminate(force=True)
        except Exception:
            if logger is not None:
                logger.exception("Could not terminate child process cleanly")

        close_child_logfile(child, logger)

        raise SyncerateError(
            errstr or "Known Syncoid error",
            exit_code,
            kind="known_child",
            child_before=child_before,
            child_warning=child_warning,
        )

    if SynCoidFail is not None:
        syncoid_before = ""
        if SynCoidFailChild is not None:
            syncoid_before = safe_text(getattr(SynCoidFailChild, "before", ""))

        raise SyncerateError(
            "Unknown Syncoid crash",
            exit_code,
            kind="syncoid",
            syncoid_before=syncoid_before,
        )

    if MQTT_Fail is not None:
        raise SyncerateError(
            "MQTT error",
            exit_code,
            kind="mqtt",
        )

    raise SyncerateError(
        errstr or "Script error",
        exit_code,
        kind="script",
    )

def log_command_debug(command_list: list[str], logger: logging.Logger) -> None:
    """Log shell-style, raw-list, and argument-by-argument command views."""

    logger.info("")
    logger.info("Syncoid command debug:")
    logger.info("")
    logger.info("Shell-style command:")
    logger.info("%s", shlex.join(command_list))
    logger.info("")
    logger.info("Raw Python argv:")
    logger.info("%r", command_list)
    logger.info("")
    logger.info("Individual arguments:")
    logger.info("Argument count: %s", len(command_list))

    for number, argument in enumerate(command_list):
        logger.info("argv[%s] = %r", number, argument)

    logger.info("")

def build_syncoid_command(
    command_template: str,
    source_dataset: str,
    destination_dataset: str,
    extra_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """Build a safe argv-style command while preserving dataset spaces."""

    if extra_args is None:
        extra_args = []

    command_parts = shlex.split(command_template)
    command_parts = [
        part.replace("SourceDataSet", source_dataset).replace(
            "DestDataSet",
            destination_dataset,
        )
        for part in command_parts
    ]
    command_parts.extend(extra_args)
    return command_parts

def effective_user_name() -> str:
    """Return the username belonging to Syncerate's effective local UID."""

    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except (KeyError, OSError):
        return f"UID {os.geteuid()}"

def ssh_command(
    syncoid_command: list[str],
    password: Optional[str],
    run_context: RunContext,
    logger: logging.Logger,
) -> SyncoidAttemptResult:
    """Start and monitor one Syncoid process and return explicit flags."""

    repeated_pattern = False
    ignored_missing_destroy_snapshot = False
    retry_without_resume = False
    modified_command = list(syncoid_command)

    logger.info("")
    logger.info(
        "Local Syncoid process identity: %s (effective UID %s)",
        effective_user_name(),
        os.geteuid(),
    )
    logger.info(
        "Local ZFS commands inherit this identity; remote ZFS commands use the SSH user in the dataset endpoint."
    )
    logger.info("")

    if run_context.logging_enabled:
        assert run_context.output_file is not None
        with open(run_context.output_file, "a", encoding="utf-8") as output_file:
            for line in ["", "----------", ""]:
                output_file.write(line + "\n")

    child = pexpect.spawn(
        syncoid_command[0],
        syncoid_command[1:],
        timeout=None,
        encoding="utf-8",
    )

    output_handle = None
    if run_context.logging_enabled:
        assert run_context.output_file is not None
        output_handle = open(run_context.output_file, "a", encoding="utf-8")
        child.logfile = output_handle

    PATTERN_HOSTKEY = 0
    PATTERN_NO_DESTROY_SNAP = 1
    PATTERN_PERMISSION_DENIED = 2
    PATTERN_TIMEOUT = 3
    PATTERN_REFUSED = 4
    PATTERN_PASSPHRASE = 5
    PATTERN_EOF = 6
    PATTERN_WARN_SKIPPING = 7
    PATTERN_NO_RESUME = 8
    PATTERN_RESUME_UNAVAILABLE = 9
    PATTERN_GENERIC_WARN = 10
    PATTERN_PASSWORD = 11

    patterns = [
        "Are you sure you want to continue connecting",
        "could not find any snapshots to destroy; check snapshot names.",
        "Permission denied",
        "Connection timed out",
        "Connection refused",
        "passphrase",
        pexpect.EOF,
        "WARN Skipping dataset",
        "used in the initial send no longer exists",
        r"WARN: ZFS resume feature not available on (?:source|target|source and target) machines? - sync will continue without resume support\.",
        "WARN|WARNING",
        "password",
    ]

    max_pattern_executions = 5
    pattern_count = {index: 0 for index in range(len(patterns))}

    while True:
        index = child.expect(patterns)
        pattern_count[index] += 1

        if pattern_count[index] > max_pattern_executions:
            logger.error("")
            logger.error(
                "Pattern '%s' has been executed more than %s times.",
                patterns[index],
                max_pattern_executions,
            )
            logger.error("")
            repeated_pattern = True
            break

        if index == PATTERN_HOSTKEY:
            child.sendline("yes")

        elif index == PATTERN_NO_DESTROY_SNAP:
            logger.info("")
            logger.info("----------")
            logger.info("")
            logger.info(
                "Syncoid wanted to delete a syncoid-created snapshot that no longer exists."
            )
            logger.info("This can happen when multiple hosts share the same datasets.")
            logger.info("Marking this as non-fatal and continuing until Syncoid exits.")
            logger.info("")
            ignored_missing_destroy_snapshot = True
            continue

        elif index == PATTERN_PERMISSION_DENIED:
            die(
                child=child,
                errstr="ERROR! Incorrect password or SSH permission denied.",
                error_code=EXIT_PASSWORD_DENIED,
                logger=logger,
            )

        elif index == PATTERN_TIMEOUT:
            die(
                child,
                "ERROR! Connection timed out.",
                EXIT_CONNECTION_TIMEOUT,
                logger=logger,
            )

        elif index == PATTERN_REFUSED:
            die(
                child,
                "ERROR! Connection refused.",
                EXIT_CONNECTION_REFUSED,
                logger=logger,
            )

        elif index == PATTERN_PASSPHRASE:
            if run_context.logging_enabled:
                child.logfile = None

            if password is None:
                die(
                    child,
                    "ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.",
                    EXIT_PASSWORD_DENIED,
                    logger=logger,
                )

            child.sendline(password)

            if run_context.logging_enabled:
                child.logfile = output_handle

        elif index == PATTERN_EOF:
            close_child_logfile(child, logger)
            return SyncoidAttemptResult(
                child=child,
                command=modified_command,
                repeated_pattern=repeated_pattern,
                retry_without_resume=retry_without_resume,
                ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
            )

        elif index == PATTERN_WARN_SKIPPING:
            die(
                child,
                "ERROR! Syncoid skipped a dataset. Check source/destination datasets.",
                EXIT_DATASET_MISSING,
                logger=logger,
            )

        elif index == PATTERN_NO_RESUME:
            retry_without_resume = True

            logger.info("")
            logger.info("----------")
            logger.info("")
            logger.info("The last transfer failed and the resume snapshot no longer exists.")
            logger.info("Gonna rerun the command with --no-resume.")
            logger.info("")

            if "--no-resume" not in syncoid_command:
                modified_command = syncoid_command + ["--no-resume"]
            else:
                modified_command = list(syncoid_command)

            logger.info("The modified command reads : %s", shlex.join(modified_command))
            logger.info("")
            logger.info("----------")
            logger.info("")

            close_child_logfile(child, logger)
            return SyncoidAttemptResult(
                child=child,
                command=modified_command,
                repeated_pattern=repeated_pattern,
                retry_without_resume=retry_without_resume,
                ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
            )

        elif index == PATTERN_RESUME_UNAVAILABLE:
            logger.warning("")
            logger.warning(
                "Syncoid reported that resumable receive is unavailable for this transfer."
            )
            logger.warning(
                "Syncoid explicitly continues without resume support, so Syncerate will wait for its real exit status."
            )
            logger.warning("")
            continue

        elif index == PATTERN_GENERIC_WARN:
            warning_text = safe_text(child.after) + safe_text(child.buffer)

            if (
                ignored_missing_destroy_snapshot
                and "zfs destroy" in warning_text
                and "failed: 256" in warning_text
            ):
                logger.info("")
                logger.info("Syncoid produced the known non-fatal destroy warning.")
                logger.info(
                    "Continuing because ignored_missing_destroy_snapshot is True."
                )
                logger.info("")
                continue

            die(
                child,
                "ERROR! Syncoid produced a warning.",
                EXIT_WARNING,
                logger=logger,
            )

        elif index == PATTERN_PASSWORD:
            if run_context.logging_enabled:
                child.logfile = None

            if password is None:
                die(
                    child,
                    "ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.",
                    EXIT_PASSWORD_DENIED,
                    logger=logger,
                )

            child.sendline(password)

            if run_context.logging_enabled:
                child.logfile = output_handle

    close_child_logfile(child, logger)
    return SyncoidAttemptResult(
        child=child,
        command=modified_command,
        repeated_pattern=repeated_pattern,
        retry_without_resume=retry_without_resume,
        ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
    )

def run_replications(
    app_config: AppConfig,
    run_context: RunContext,
    dataset_pairs: list[DatasetPair],
    password: Optional[str],
    logger: logging.Logger,
) -> None:
    """Run all validated DatasetPair entries sequentially."""

    for dataset_pair in dataset_pairs:
        syncoid_execute = build_syncoid_command(
            app_config.syncoid_command,
            dataset_pair.source,
            dataset_pair.destination,
            dataset_pair.extra_arguments,
        )

        logger.info("")
        logger.info("----------")
        logger.info("")

        if dataset_pair.extra_arguments:
            logger.info("Extra Syncoid arguments for this destination:")
            logger.info("%s", list(dataset_pair.extra_arguments))
            logger.info("")

        logger.info(
            "Executing the altered Syncoid Command    :   %s",
            shlex.join(syncoid_execute),
        )
        logger.info("")

        log_command_debug(syncoid_execute, logger)

        result = ssh_command(
            syncoid_execute,
            password,
            run_context,
            logger,
        )

        if result.retry_without_resume:
            result.child.close()

            logger.info(
                "Executing the modified Syncoid Command    :    %s",
                shlex.join(result.command),
            )

            result = ssh_command(
                result.command,
                password,
                run_context,
                logger,
            )
            result.child.close()
        else:
            result.child.close()

        child = result.child

        if result.repeated_pattern:
            die(
                child,
                "ERROR: The script is repeating itself",
                EXIT_REPEATED_PATTERN,
                logger=logger,
            )

        if child.exitstatus is None and child.signalstatus is not None:
            exit_code = 128 + int(child.signalstatus)

            logger.error("")
            logger.error("Syncoid was terminated by signal: %s", child.signalstatus)
            logger.error("Using exit code: %s", exit_code)

            die(
                SynCoidFail=exit_code,
                SynCoidFailChild=child,
                logger=logger,
            )

        if child.exitstatus != EXIT_OK and result.ignored_missing_destroy_snapshot:
            logger.warning("")
            logger.warning(
                "Syncoid exited with non-zero status %s, but ignored_missing_destroy_snapshot is True.",
                child.exitstatus,
            )
            logger.warning(
                "Ignoring this because the known no-destroy-snapshot message was seen."
            )
            logger.warning("")

        if child.exitstatus != EXIT_OK and not result.ignored_missing_destroy_snapshot:
            exit_code = int(child.exitstatus)

            logger.error("")
            logger.error("This is the Syncoid exit status: %s", exit_code)

            die(
                SynCoidFail=exit_code,
                SynCoidFailChild=child,
                logger=logger,
            )
