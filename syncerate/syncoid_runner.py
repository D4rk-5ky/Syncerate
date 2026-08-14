"""Syncoid command construction, process monitoring, and safety handling."""

import logging
import os
import pwd
import shlex
import time
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
from .models import (
    AppConfig,
    DatasetPair,
    ReplicationSummary,
    RunContext,
    SyncoidAttemptResult,
)


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

def send_secret(
    child: Any,
    password: str,
    output_handle: Any,
    logging_enabled: bool,
) -> None:
    """Wait for no-echo credential input, send the secret, and restore logging."""

    if logging_enabled:
        child.logfile = None

    try:
        child.waitnoecho(timeout=3)
        child.sendline(password)
    finally:
        if logging_enabled:
            child.logfile = output_handle

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
    retry_broken_pipe: bool = False,
) -> SyncoidAttemptResult:
    """Start and monitor one Syncoid process and return explicit flags."""

    repeated_pattern = False
    ignored_missing_destroy_snapshot = False
    retry_without_resume = False
    broken_pipe_detected = False
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
    PATTERN_BROKEN_PIPE = 10
    PATTERN_GENERIC_WARN = 11
    PATTERN_PASSWORD = 12

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
        r"(?i)broken pipe",
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
            if password is None:
                die(
                    child,
                    "ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.",
                    EXIT_PASSWORD_DENIED,
                    logger=logger,
                )

            send_secret(
                child,
                password,
                output_handle,
                run_context.logging_enabled,
            )

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

        elif index == PATTERN_BROKEN_PIPE:
            if not retry_broken_pipe:
                logger.warning("")
                logger.warning(
                    "Broken Pipe appeared in Syncoid output, but RetryBrokenPipe is disabled."
                )
                logger.warning(
                    "Waiting for Syncoid's real exit status and preserving normal failure handling."
                )
                logger.warning("")
                continue

            logger.warning("")
            logger.warning("Broken Pipe appeared in Syncoid output.")
            logger.warning(
                "Stopping this attempt so the dataset-level retry policy can handle it."
            )
            logger.warning("")

            broken_pipe_detected = True

            try:
                child.terminate(force=True)
            except Exception:
                logger.exception(
                    "Could not terminate the Broken Pipe attempt cleanly"
                )

            close_child_logfile(child, logger)
            return SyncoidAttemptResult(
                child=child,
                command=modified_command,
                repeated_pattern=repeated_pattern,
                retry_without_resume=retry_without_resume,
                ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
                broken_pipe_detected=broken_pipe_detected,
            )

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
            if password is None:
                die(
                    child,
                    "ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.",
                    EXIT_PASSWORD_DENIED,
                    logger=logger,
                )

            send_secret(
                child,
                password,
                output_handle,
                run_context.logging_enabled,
            )

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
) -> ReplicationSummary:
    """Run all dataset pairs and return any non-fatal run warnings."""

    summary = ReplicationSummary()

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

        current_command = list(syncoid_execute)
        resume_retry_used = False
        broken_pipe_retries_used = 0

        while True:
            result = ssh_command(
                current_command,
                password,
                run_context,
                logger,
                retry_broken_pipe=app_config.retry_broken_pipe,
            )
            child = result.child

            if result.broken_pipe_detected:
                child.close()

                if broken_pipe_retries_used < app_config.broken_pipe_retry_count:
                    broken_pipe_retries_used += 1
                    current_command = list(result.command)

                    logger.warning("")
                    logger.warning("----------")
                    logger.warning("")
                    logger.warning(
                        "Broken Pipe detected for %s -> %s.",
                        dataset_pair.source,
                        dataset_pair.destination,
                    )
                    logger.warning(
                        "RetryBrokenPipe is enabled; waiting %s seconds before retry %s of %s for this dataset.",
                        app_config.broken_pipe_retry_wait_seconds,
                        broken_pipe_retries_used,
                        app_config.broken_pipe_retry_count,
                    )
                    logger.warning("")
                    time.sleep(app_config.broken_pipe_retry_wait_seconds)
                    continue

                summary.broken_pipe_failed_datasets.append(dataset_pair)

                logger.warning("")
                logger.warning("----------")
                logger.warning("")
                logger.warning(
                    "Broken Pipe persisted for %s -> %s.",
                    dataset_pair.source,
                    dataset_pair.destination,
                )
                logger.warning(
                    "The configured retry count of %s has been exhausted; skipping this dataset and continuing the list.",
                    app_config.broken_pipe_retry_count,
                )
                logger.warning(
                    "The final run remains successful but will carry a Broken Pipe warning."
                )
                logger.warning("")
                break

            if result.retry_without_resume and not resume_retry_used:
                child.close()
                resume_retry_used = True
                current_command = list(result.command)

                logger.info(
                    "Executing the modified Syncoid Command    :    %s",
                    shlex.join(current_command),
                )
                continue

            child.close()

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
                logger.error(
                    "Syncoid was terminated by signal: %s",
                    child.signalstatus,
                )
                logger.error("Using exit code: %s", exit_code)

                die(
                    SynCoidFail=exit_code,
                    SynCoidFailChild=child,
                    logger=logger,
                )

            if (
                child.exitstatus != EXIT_OK
                and result.ignored_missing_destroy_snapshot
            ):
                logger.warning("")
                logger.warning(
                    "Syncoid exited with non-zero status %s, but ignored_missing_destroy_snapshot is True.",
                    child.exitstatus,
                )
                logger.warning(
                    "Ignoring this because the known no-destroy-snapshot message was seen."
                )
                logger.warning("")

            if (
                child.exitstatus != EXIT_OK
                and not result.ignored_missing_destroy_snapshot
            ):
                exit_code = int(child.exitstatus)

                logger.error("")
                logger.error("This is the Syncoid exit status: %s", exit_code)

                die(
                    SynCoidFail=exit_code,
                    SynCoidFailChild=child,
                    logger=logger,
                )

            break

    return summary
