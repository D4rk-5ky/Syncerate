"""Syncoid command construction, process monitoring, and safety handling."""

import logging
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from getpass import getpass
from typing import Any, Optional, Sequence

import pexpect

from .config import validate_syncoid_command_template
from .errors import (
    EXIT_CONNECTION_REFUSED,
    EXIT_CONNECTION_TIMEOUT,
    EXIT_DATASET_MISSING,
    EXIT_LIST_ERROR,
    EXIT_OK,
    EXIT_PASSWORD_DENIED,
    EXIT_REPEATED_PATTERN,
    EXIT_SCRIPT_ERROR,
    EXIT_WARNING,
    SyncerateError,
)
from .models import (
    AppConfig,
    DatasetPair,
    ReplicationSummary,
    RunContext,
    SSHAgentSession,
    SyncoidAttemptResult,
)


_TRANSFER_START_RE = re.compile(
    r"(?i)(?:INFO:\s*)?(?:"
    r"Sending oldest full snapshot|"
    r"Sending incremental|"
    r"Sending full|"
    r"Updating new target filesystem with incremental|"
    r"Resuming interrupted zfs send/receive|"
    r"--no-stream selected; sending newest full snapshot"
    r")"
)

_PV_PROGRESS_RE = re.compile(
    r"^\s*(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>[KMGTPE]?i?B)\s+"
    r"\d+:\d{2}:\d{2}\s+\[",
    re.IGNORECASE,
)


def pv_amount_to_bytes(amount_text: str, unit_text: str) -> int:
    """Convert one pv human-readable byte counter value to whole bytes."""

    amount = float(amount_text.replace(",", "."))
    unit = unit_text.upper()

    binary_units = {
        "B": 1,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
        "PIB": 1024**5,
        "EIB": 1024**6,
    }
    decimal_units = {
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "PB": 1000**5,
        "EB": 1000**6,
    }

    if unit in binary_units:
        multiplier = binary_units[unit]
    elif unit in decimal_units:
        multiplier = decimal_units[unit]
    else:
        raise ValueError(f"Unsupported pv byte unit: {unit_text}")

    return max(0, round(amount * multiplier))


class TransferByteCounter:
    """Accumulate actual pv byte counters without double-counting progress refreshes."""

    def __init__(self, measurement_possible: bool = True) -> None:
        self.total_bytes = 0
        self.measurement_complete = measurement_possible
        self._current_transfer_active = False
        self._current_transfer_bytes = 0
        self._current_transfer_measured = False
        self._buffer = ""

    def _finish_current_transfer(self) -> None:
        """Commit the maximum observed pv value for the current Syncoid stream."""

        if not self._current_transfer_active:
            return

        if self._current_transfer_measured:
            self.total_bytes += self._current_transfer_bytes
        else:
            self.measurement_complete = False

        self._current_transfer_active = False
        self._current_transfer_bytes = 0
        self._current_transfer_measured = False

    def _start_transfer(self) -> None:
        """Finish the previous stream and begin tracking a new Syncoid stream."""

        self._finish_current_transfer()
        self._current_transfer_active = True

    def _process_line(self, line: str) -> None:
        """Consume one physical Syncoid/pv output line in stream order."""

        if _TRANSFER_START_RE.search(line):
            self._start_transfer()

        progress_match = _PV_PROGRESS_RE.match(line)
        if progress_match is None:
            return

        if not self._current_transfer_active:
            # Be tolerant of Syncoid versions or custom output that omit a
            # recognized transfer heading while still using pv's byte counter.
            self._current_transfer_active = True

        transferred_bytes = pv_amount_to_bytes(
            progress_match.group("amount"),
            progress_match.group("unit"),
        )
        self._current_transfer_measured = True
        self._current_transfer_bytes = max(
            self._current_transfer_bytes,
            transferred_bytes,
        )

    def feed(self, text: str) -> None:
        """Consume streamed output, treating both CR and LF as pv line boundaries."""

        if not text:
            return

        combined = self._buffer + text
        parts = re.split(r"[\r\n]+", combined)
        self._buffer = parts.pop()

        for line in parts:
            self._process_line(line)

    def finish(self) -> tuple[int, bool]:
        """Flush the final partial line and return bytes plus completeness state."""

        if self._buffer:
            self._process_line(self._buffer)
            self._buffer = ""

        self._finish_current_transfer()
        return self.total_bytes, self.measurement_complete


def build_attempt_result(
    child: Any,
    modified_command: list[str],
    transfer_counter: TransferByteCounter,
    *,
    repeated_pattern: bool,
    ignored_missing_destroy_snapshot: bool,
    broken_pipe_detected: bool = False,
) -> SyncoidAttemptResult:
    """Finalize transfer accounting and build one Syncoid attempt result."""

    transferred_bytes, measurement_complete = transfer_counter.finish()
    return SyncoidAttemptResult(
        child=child,
        command=modified_command,
        repeated_pattern=repeated_pattern,
        ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
        broken_pipe_detected=broken_pipe_detected,
        transferred_bytes=transferred_bytes,
        transfer_measurement_complete=measurement_complete,
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
    *,
    wait_for_noecho: bool = True,
) -> None:
    """Send a secret while suppressing it from an attached Pexpect logfile."""

    if logging_enabled:
        child.logfile = None

    try:
        if wait_for_noecho and not child.waitnoecho(timeout=3):
            raise SyncerateError(
                "Credential prompt did not disable terminal echo; refusing to send the secret.",
                EXIT_PASSWORD_DENIED,
                kind="script",
            )
        child.sendline(password)
    finally:
        if logging_enabled:
            child.logfile = output_handle


def extract_ssh_key_path(command_template: str) -> Optional[str]:
    """Return the last Syncoid --sshkey value from the configured command."""

    command_parts = shlex.split(command_template)
    identity_file: Optional[str] = None

    for index, argument in enumerate(command_parts):
        if argument == "--sshkey":
            if index + 1 >= len(command_parts):
                raise SyncerateError(
                    "UseSSHAgent is enabled, but --sshkey has no identity-file value.",
                    EXIT_SCRIPT_ERROR,
                    kind="script",
                )
            identity_file = command_parts[index + 1]
        elif argument.startswith("--sshkey="):
            identity_file = argument.split("=", 1)[1]

    return identity_file


def start_private_ssh_agent(
    app_config: AppConfig,
    logger: logging.Logger,
) -> SSHAgentSession:
    """Start one isolated foreground ssh-agent with a private per-run socket."""

    identity_file = extract_ssh_key_path(app_config.syncoid_command)
    if not identity_file:
        raise SyncerateError(
            "UseSSHAgent is enabled, but SyncoidCommand does not contain --sshkey.",
            EXIT_SCRIPT_ERROR,
            kind="script",
        )

    identity_file = os.path.expanduser(identity_file)
    if not os.path.isfile(identity_file):
        raise SyncerateError(
            f"UseSSHAgent identity file does not exist or is not a regular file: {identity_file}",
            EXIT_SCRIPT_ERROR,
            kind="script",
        )

    ssh_agent_path = shutil.which("ssh-agent")
    ssh_add_path = shutil.which("ssh-add")
    if ssh_agent_path is None or ssh_add_path is None:
        raise SyncerateError(
            "UseSSHAgent requires both ssh-agent and ssh-add from OpenSSH.",
            EXIT_SCRIPT_ERROR,
            kind="script",
        )

    temp_directory = tempfile.mkdtemp(prefix="syncerate-ssh-agent-")
    os.chmod(temp_directory, 0o700)
    socket_path = os.path.join(temp_directory, "agent.sock")

    environment = os.environ.copy()
    environment.pop("SSH_AUTH_SOCK", None)
    environment.pop("SSH_AGENT_PID", None)
    environment.pop("SSH_ASKPASS", None)
    environment["SSH_ASKPASS_REQUIRE"] = "never"

    process: Optional[subprocess.Popen[str]] = None
    try:
        process = subprocess.Popen(
            [
                ssh_agent_path,
                "-D",
                "-a",
                socket_path,
                "-t",
                str(app_config.ssh_agent_key_lifetime_seconds),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            umask=0o077,
        )

        environment["SSH_AUTH_SOCK"] = socket_path
        environment["SSH_AGENT_PID"] = str(process.pid)

        deadline = time.monotonic() + 5
        while not os.path.exists(socket_path):
            if process.poll() is not None:
                stderr_text = ""
                if process.stderr is not None:
                    stderr_text = process.stderr.read().strip()
                raise SyncerateError(
                    "Private ssh-agent exited during startup"
                    + (f": {stderr_text}" if stderr_text else "."),
                    EXIT_SCRIPT_ERROR,
                    kind="script",
                )

            if time.monotonic() >= deadline:
                raise SyncerateError(
                    "Timed out waiting for the private ssh-agent socket.",
                    EXIT_SCRIPT_ERROR,
                    kind="script",
                )

            time.sleep(0.05)

        socket_stat = os.stat(socket_path)
        if not stat.S_ISSOCK(socket_stat.st_mode):
            raise SyncerateError(
                "Private ssh-agent path exists but is not a Unix-domain socket.",
                EXIT_SCRIPT_ERROR,
                kind="script",
            )

        os.chmod(socket_path, 0o600)

        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("Started isolated per-run ssh-agent")
        logger.info("SSH identity file: %s", identity_file)
        logger.info(
            "Agent identity lifetime: %s seconds",
            app_config.ssh_agent_key_lifetime_seconds,
        )
        logger.info("")

        return SSHAgentSession(
            process=process,
            temp_directory=temp_directory,
            socket_path=socket_path,
            environment=environment,
            identity_file=identity_file,
            ssh_add_path=ssh_add_path,
            key_lifetime_seconds=app_config.ssh_agent_key_lifetime_seconds,
        )

    except Exception:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        shutil.rmtree(temp_directory, ignore_errors=True)
        raise


def add_identity_to_private_agent(
    session: SSHAgentSession,
    password: Optional[str],
    logger: logging.Logger,
) -> None:
    """Load the configured identity into the isolated agent using direct Pexpect."""

    child = pexpect.spawn(
        session.ssh_add_path,
        [
            "-q",
            "-t",
            str(session.key_lifetime_seconds),
            session.identity_file,
        ],
        timeout=30,
        encoding="utf-8",
        env=session.environment,
    )

    passphrase_sent = False
    prompt_pattern = r"(?i)enter passphrase for [^\r\n]*:\s*"
    bad_passphrase_pattern = r"(?i)bad passphrase[^\r\n]*"

    while True:
        index = child.expect(
            [
                prompt_pattern,
                bad_passphrase_pattern,
                pexpect.EOF,
                pexpect.TIMEOUT,
            ]
        )

        if index == 0:
            if password is None:
                child.terminate(force=True)
                child.close()
                raise SyncerateError(
                    "The SSH identity requires a passphrase, but PassWord is set to No.",
                    EXIT_PASSWORD_DENIED,
                    kind="script",
                )

            if passphrase_sent:
                child.terminate(force=True)
                child.close()
                raise SyncerateError(
                    "ssh-add rejected the configured SSH-key passphrase.",
                    EXIT_PASSWORD_DENIED,
                    kind="script",
                )

            send_secret(child, password, None, False)
            passphrase_sent = True
            continue

        if index == 1:
            child.terminate(force=True)
            child.close()
            raise SyncerateError(
                "ssh-add rejected the configured SSH-key passphrase.",
                EXIT_PASSWORD_DENIED,
                kind="script",
            )

        if index == 2:
            child.close()
            if child.exitstatus != EXIT_OK:
                raise SyncerateError(
                    "ssh-add could not load the configured SSH identity into the private agent.",
                    EXIT_PASSWORD_DENIED,
                    kind="script",
                )

            logger.info("SSH identity loaded into the isolated agent")
            return

        child.terminate(force=True)
        child.close()
        raise SyncerateError(
            "Timed out while loading the SSH identity into the private agent.",
            EXIT_CONNECTION_TIMEOUT,
            kind="script",
        )


def private_agent_has_identity(session: SSHAgentSession) -> bool:
    """Return whether the isolated agent currently contains an identity."""

    if session.process.poll() is not None:
        raise SyncerateError(
            "The private ssh-agent exited before replication completed.",
            EXIT_SCRIPT_ERROR,
            kind="script",
        )

    try:
        result = subprocess.run(
            [session.ssh_add_path, "-l"],
            env=session.environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise SyncerateError(
            "Timed out while checking the private ssh-agent identity.",
            EXIT_SCRIPT_ERROR,
            kind="script",
        ) from exc

    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False

    raise SyncerateError(
        "ssh-add could not query the private ssh-agent.",
        EXIT_SCRIPT_ERROR,
        kind="script",
    )


def ensure_private_agent_identity(
    session: SSHAgentSession,
    password: Optional[str],
    logger: logging.Logger,
) -> None:
    """Reload the one private-agent identity if its bounded lifetime expired."""

    if private_agent_has_identity(session):
        return

    logger.info(
        "Private ssh-agent identity lifetime expired; reloading the configured key before the next dataset."
    )
    add_identity_to_private_agent(session, password, logger)


def stop_private_ssh_agent(
    session: SSHAgentSession,
    logger: logging.Logger,
) -> None:
    """Delete agent identities, terminate the private agent, and remove its socket."""

    try:
        subprocess.run(
            [session.ssh_add_path, "-D"],
            env=session.environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except Exception:
        logger.warning("Could not explicitly remove identities from the private ssh-agent")

    try:
        if session.process.poll() is None:
            session.process.terminate()
            try:
                session.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                session.process.kill()
                session.process.wait(timeout=3)
    except Exception:
        logger.exception("Could not terminate the private ssh-agent cleanly")
    finally:
        shutil.rmtree(session.temp_directory, ignore_errors=True)
        logger.info("Private ssh-agent stopped and its temporary socket directory removed")


@contextmanager
def private_ssh_agent(
    app_config: AppConfig,
    password: Optional[str],
    logger: logging.Logger,
):
    """Yield an isolated agent session when UseSSHAgent is enabled."""

    if not app_config.use_ssh_agent:
        yield None
        return

    session = start_private_ssh_agent(app_config, logger)
    try:
        add_identity_to_private_agent(session, password, logger)
        yield session
    finally:
        stop_private_ssh_agent(session, logger)

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

    validate_syncoid_command_template(command_template)
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
    process_env: Optional[dict[str, str]] = None,
) -> SyncoidAttemptResult:
    """Start and monitor one Syncoid process and return explicit flags."""

    repeated_pattern = False
    ignored_missing_destroy_snapshot = False
    stale_resume_recovery_active = False
    stale_resume_reset_announced = False
    broken_pipe_detected = False
    modified_command = list(syncoid_command)
    transfer_counter = TransferByteCounter(
        measurement_possible="--quiet" not in modified_command
    )

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
        env=process_env,
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
    PATTERN_STALE_RESUME_SOURCE = 8
    PATTERN_RESUME_RESET = 9
    PATTERN_FRESH_SEND = 10
    PATTERN_RESUME_UNAVAILABLE = 11
    PATTERN_BROKEN_PIPE = 12
    PATTERN_GENERIC_WARN = 13
    PATTERN_PASSWORD = 14

    patterns = [
        "Are you sure you want to continue connecting",
        "could not find any snapshots to destroy; check snapshot names.",
        "Permission denied",
        "Connection timed out",
        "Connection refused",
        r"(?im)(?:^|[\r\n])[^\r\n]*\benter passphrase for [^\r\n]*:\s*",
        pexpect.EOF,
        "WARN Skipping dataset",
        r"(?i)used in the initial send no longer exists",
        r"(?i)(?:WARN|WARNING): resetting partially receive state because the snapshot source no longer exists",
        r"(?i)INFO: Sending (?:incremental|full)",
        r"WARN: ZFS resume feature not available on (?:source|target|source and target) machines? - sync will continue without resume support\.",
        r"(?i)broken pipe",
        r"(?im)(?:^|[\r\n])(?:WARN|WARNING)(?:\b|:)",
        r"(?im)(?:^|[\r\n])[^\r\n]*\bpassword:\s*$",
    ]

    max_pattern_executions = 5
    repeat_guarded_patterns = {
        PATTERN_HOSTKEY,
        PATTERN_PASSPHRASE,
        PATTERN_PASSWORD,
    }
    pattern_count = {index: 0 for index in repeat_guarded_patterns}

    while True:
        index = child.expect(patterns)

        transfer_counter.feed(safe_text(child.before))
        if isinstance(child.after, str):
            transfer_counter.feed(child.after)

        if index in repeat_guarded_patterns:
            pattern_count[index] += 1

        if (
            index in repeat_guarded_patterns
            and pattern_count[index] > max_pattern_executions
        ):
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
                wait_for_noecho=False,
            )

        elif index == PATTERN_EOF:
            close_child_logfile(child, logger)
            return build_attempt_result(
                child,
                modified_command,
                transfer_counter,
                repeated_pattern=repeated_pattern,
                ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
            )

        elif index == PATTERN_WARN_SKIPPING:
            die(
                child,
                "ERROR! Syncoid skipped a dataset. Check source/destination datasets.",
                EXIT_DATASET_MISSING,
                logger=logger,
            )

        elif index == PATTERN_STALE_RESUME_SOURCE:
            stale_resume_recovery_active = True
            stale_resume_reset_announced = False

            logger.warning("")
            logger.warning("----------")
            logger.warning("")
            logger.warning(
                "Syncoid reported that the source snapshot required by the interrupted receive no longer exists."
            )
            logger.warning(
                "Allowing Syncoid to finish its built-in stale receive-state recovery instead of interrupting it."
            )
            logger.warning(
                "Syncerate will keep the original Syncoid command unchanged and wait for Syncoid to reset the partial receive state itself."
            )
            logger.warning("")
            continue

        elif index == PATTERN_RESUME_RESET:
            stale_resume_recovery_active = True
            stale_resume_reset_announced = True

            logger.warning("")
            logger.warning("Syncoid is resetting the stale partially received ZFS stream.")
            logger.warning(
                "The old resumable receive token points to a source snapshot that no longer exists."
            )
            logger.warning(
                "Waiting for Syncoid to clear the receive state and start a fresh valid send."
            )
            logger.warning("")
            continue

        elif index == PATTERN_FRESH_SEND:
            if stale_resume_recovery_active:
                logger.info("")
                logger.info(
                    "Syncoid stale receive-state recovery completed; a new valid send is starting."
                )
                logger.info("")
                stale_resume_recovery_active = False
                stale_resume_reset_announced = False
            continue

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
            if stale_resume_recovery_active:
                logger.warning("")
                logger.warning(
                    "Broken Pipe occurred while Syncoid is recovering a stale interrupted receive."
                )
                if stale_resume_reset_announced:
                    logger.warning(
                        "This is treated as part of Syncoid's reset sequence; Syncerate will keep waiting for the replacement send."
                    )
                else:
                    logger.warning(
                        "This is an expected secondary symptom of the failed resume attempt; Syncerate will keep waiting for Syncoid's reset."
                    )
                logger.warning("")
                continue

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
            return build_attempt_result(
                child,
                modified_command,
                transfer_counter,
                repeated_pattern=repeated_pattern,
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
                wait_for_noecho=False,
            )

    close_child_logfile(child, logger)
    return build_attempt_result(
        child,
        modified_command,
        transfer_counter,
        repeated_pattern=repeated_pattern,
        ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
    )

def run_replications(
    app_config: AppConfig,
    run_context: RunContext,
    dataset_pairs: list[DatasetPair],
    password: Optional[str],
    logger: logging.Logger,
    ssh_agent_session: Optional[SSHAgentSession] = None,
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

        if ssh_agent_session is not None:
            ensure_private_agent_identity(ssh_agent_session, password, logger)
            logger.info(
                "Private ssh-agent identity is loaded; Syncoid will inherit SSH_AUTH_SOCK and keep the configured Syncoid command unchanged."
            )

        logger.info(
            "Executing the altered Syncoid Command    :   %s",
            shlex.join(syncoid_execute),
        )
        logger.info("")

        log_command_debug(syncoid_execute, logger)

        current_command = list(syncoid_execute)
        broken_pipe_retries_used = 0

        while True:
            result = ssh_command(
                current_command,
                password,
                run_context,
                logger,
                retry_broken_pipe=app_config.retry_broken_pipe,
                process_env=(
                    ssh_agent_session.environment
                    if ssh_agent_session is not None
                    else None
                ),
            )
            child = result.child
            summary.transferred_bytes += result.transferred_bytes
            summary.transfer_measurement_complete = (
                summary.transfer_measurement_complete
                and result.transfer_measurement_complete
            )

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

            if child.exitstatus is None:
                raise SyncerateError(
                    "Syncoid ended without an exit status or terminating signal.",
                    EXIT_SCRIPT_ERROR,
                    kind="script",
                )

            if child.exitstatus != EXIT_OK:
                exit_code = int(child.exitstatus)

                logger.error("")
                if result.ignored_missing_destroy_snapshot:
                    logger.error(
                        "The known missing destroy-snapshot condition was observed, "
                        "but Syncoid still exited non-zero."
                    )
                    logger.error(
                        "Preserving Syncoid's real exit status instead of masking a "
                        "possible later replication failure."
                    )
                logger.error("This is the Syncoid exit status: %s", exit_code)

                die(
                    SynCoidFail=exit_code,
                    SynCoidFailChild=child,
                    logger=logger,
                )

            break

    return summary
