#!/usr/bin/python3
from asyncio.log import logger
import os
import re
import datetime
import logging
import subprocess
import argparse
import glob
import sys
from typing import List, Tuple, Optional
import tempfile
import tomllib
from pathlib import Path
from mqtt_report import RunReporter, validate_config as validate_mqtt_config

__version__ = "0.0.6"

class CustomLogger(logging.Logger):
    def __init__(self, name, log_filename):
        super().__init__(name)

        # Set up formatter for log messages
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Set up log file handler
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)  # or INFO as desired
        file_handler.setFormatter(formatter)
        self.addHandler(file_handler)

        # Set up console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)
        
def setup_logger(log_folder: str, log_date: str) -> Tuple[logging.Logger, logging.Logger, str]:
    """
    Creates two loggers:
      - main logger: INFO to console, DEBUG to .log
      - error logger: ERROR to console and ERROR to .err

    Returns: (logger, error_logger, err_filepath)
    """
    os.makedirs(log_folder, exist_ok=True)

    log_filepath = os.path.join(log_folder, f"SnapBeforeWatchTower-Date-{log_date}.log")
    err_filepath = os.path.join(log_folder, f"SnapBeforeWatchTower-Date-{log_date}.err")

    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    def _build_logger(name: str, level: int, handlers: List[logging.Handler]) -> logging.Logger:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = False  # do not double-log via root logger

        # Prevent duplicate handlers if the script is run multiple times in-process
        if lg.handlers:
            # If you *really* want to rebuild handlers each time, clear:
            lg.handlers.clear()

        for h in handlers:
            h.setFormatter(fmt)
            lg.addHandler(h)

        return lg

    # Main logger handlers
    file_h = logging.FileHandler(log_filepath)
    file_h.setLevel(logging.DEBUG)

    console_h = logging.StreamHandler()
    console_h.setLevel(logging.INFO)

    logger = _build_logger(
        name="SnapBeforeWatchTower",
        level=logging.DEBUG,
        handlers=[file_h, console_h],
    )

    # Error logger handlers (err file + console)
    err_file_h = logging.FileHandler(err_filepath)
    err_file_h.setLevel(logging.ERROR)

    err_console_h = logging.StreamHandler()
    err_console_h.setLevel(logging.ERROR)

    error_logger = _build_logger(
        name="SnapBeforeWatchTowerError",
        level=logging.ERROR,
        handlers=[err_file_h, err_console_h],
    )

    return logger, error_logger, err_filepath

def choose_log_folder(preferred_root_folder: str, fallback_folder: str | None = None) -> str:
    """
    If running as root, use preferred_root_folder.
    If not root, use fallback_folder or a temp directory.
    Ensures the returned folder exists and is writable.
    """
    is_root = (os.geteuid() == 0)

    if is_root:
        os.makedirs(preferred_root_folder, exist_ok=True)
        return preferred_root_folder

    # Not root: use fallback
    if fallback_folder is None:
        fallback_folder = os.path.join(tempfile.gettempdir(), "SnapBeforeWatchTower")

    os.makedirs(fallback_folder, exist_ok=True)
    return fallback_folder

def pick_log_folder(script_log_folder: str, tmp_name: str = "SnapBeforeWatchTower") -> str:
    """
    Policy:
      - If NOT root: always use /tmp/<tmp_name>
      - If root: try <script>/logs; if not writable, fall back to /tmp/<tmp_name>
    """
    tmp_folder = os.path.join(tempfile.gettempdir(), tmp_name)

    def _ensure_writable(path: str) -> bool:
        try:
            os.makedirs(path, exist_ok=True)
            test_path = os.path.join(path, ".write_test")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_path)
            return True
        except Exception:
            return False

    if os.geteuid() != 0:
        os.makedirs(tmp_folder, exist_ok=True)
        return tmp_folder

    # root path
    if _ensure_writable(script_log_folder):
        return script_log_folder

    os.makedirs(tmp_folder, exist_ok=True)
    return tmp_folder

class CommandError(RuntimeError):
    def __init__(self, cmd, returncode, stdout, stderr):
        super().__init__(f"Command failed ({returncode}): {' '.join(cmd)}")
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class MissingDatasetsError(RuntimeError):
    """Final run failure raised after all remaining datasets were processed."""

    def __init__(self, datasets):
        self.datasets = tuple(datasets)
        label = "dataset" if len(self.datasets) == 1 else "datasets"
        names = ", ".join(self.datasets)
        super().__init__(f"Missing ZFS {label} (dataset does not exist): {names}")


def is_missing_dataset_error(exc):
    """Return True only for command failures whose ZFS stderr says the dataset is absent."""
    stderr = getattr(exc, "stderr", "") or ""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    lowered = stderr.lower()
    return "dataset does not exist" in lowered or "no such pool or dataset" in lowered


def remember_missing_dataset(error_logger, missing_datasets, dataset, exc):
    """Record a known missing-dataset failure and tell the caller whether it may continue."""
    if not is_missing_dataset_error(exc):
        return False
    if dataset not in missing_datasets:
        missing_datasets.append(dataset)
    error_logger.error(
        f"Missing ZFS dataset: {dataset}. ZFS reported that the dataset does not exist; "
        "continuing with the remaining datasets."
    )
    return True


def run_cmd(cmd, logger=None, error_logger=None, check=True, dry_run=False):
    """
    Runs a command with captured stdout/stderr so the terminal doesn't get spammed.
    If check=True, raises CommandError on failure.
    If dry_run=True, does NOT execute the command.
    """
    if dry_run:
        #if logger:
        #    logger.info(f"[DRY-RUN] Would run: {' '.join(cmd)}")
        # mimic a successful completed process
        return subprocess.CompletedProcess(cmd, 0, "", "")
    
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        if error_logger:
            error_logger.error(f"Command failed: {' '.join(cmd)} (rc={proc.returncode})")
            if proc.stderr.strip():
                error_logger.error(proc.stderr.strip())
        if check:
            raise CommandError(cmd, proc.returncode, proc.stdout, proc.stderr)

    return proc

def get_newest_files(log_dir, prefix):
    files = glob.glob(os.path.join(log_dir, f"{prefix}*"))
    # Use modification time (mtime) which is more portable than creation time
    files.sort(key=os.path.getmtime, reverse=True)
    
    newest_log = None
    newest_err = None

    for file in files:
        ext = os.path.splitext(file)[-1][1:]  # Get the file extension without the dot
        if ext == "log" and not newest_log:
            newest_log = file
        elif ext == "err" and not newest_err:
            newest_err = file
        
        if newest_log and newest_err:
            break

    return newest_log, newest_err

# This is is for the send mail part
def send_mail(subject, body, recipient, attachment_files=None):
    # Put all options before the recipient. This is more compatible with mail/mailx variants.
    mail_command = ['mail', '-s', subject]

    if attachment_files:
        for file in attachment_files:
            mail_command.extend(['--attach', file])

    mail_command.append(recipient)

    if not body:
        body = "No mail body was generated. Check attached logs.\n"

    process = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr_output = process.communicate(input=body.encode())

    mail_exit_code = process.returncode

    return mail_exit_code, stderr_output.decode().strip()

# This is for the send mail function
# In case one needs to be notified of errors
def MailTo(
    logger,
    error_logger,
    recipient,
    log_folder,
    subject="SnapBeforeWatchTower report - logs attached",
    intro="",
    prefix="SnapBeforeWatchTower",
):
    print_separator(logger)
    logger.info("Preparing email report...")

    newest_log, newest_err = get_newest_files(log_folder, prefix)

    attachment_files = []
    body = ""

    if intro:
        body += intro.strip() + "\n\n"

    # Attach latest .err first if it exists and is non-empty.
    if newest_err and os.path.isfile(newest_err):
        try:
            if os.path.getsize(newest_err) > 0:
                attachment_files.append(newest_err)
                with open(newest_err, "r", encoding="utf-8", errors="replace") as f:
                    body += "\n----------\n\n.err file\n" + f.read()
        except Exception as e:
            error_logger.error(f"Could not read err file for mail body: {e}")

    # Attach latest .log if present.
    if newest_log:
        attachment_files.append(newest_log)
        if os.path.isfile(newest_log):
            with open(newest_log, "r", encoding="utf-8", errors="replace") as f:
                body += "\n----------\n\n.log file\n" + f.read()

    if not body.strip():
        body = "No log content was found. Check the script output on the host.\n"

    mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)

    if mail_exit_code == 0:
        WasMailSent(logger, error_logger, 0, "")
    else:
        WasMailSent(logger, error_logger, mail_exit_code, stderr_output)


def WasMailSent(logger, error_logger, MailExitCode, popenstderr):
    if MailExitCode == 0:
        print_separator(logger)
        logger.info('Mail was sent successfully')
    else:
        print_separator(logger, error_logger)
        error_logger.error('There was an error sending the mail')
        error_logger.error('This is what popen said')
        error_logger.error('')
        error_logger.error(popenstderr)
        error_logger.error('')
        error_logger.error('----------')

def parse_older_than(value):
    pattern = r'^(\d+)([dwm])$'
    match = re.match(pattern, value)
    if not match:
        raise argparse.ArgumentTypeError("Invalid retention age. Use format 'Nd', 'Nw', or 'Nm' (N=integer).")

    num = int(match.group(1))
    unit = match.group(2)

    if unit == 'd':
        return datetime.timedelta(days=num)
    elif unit == 'w':
        return datetime.timedelta(weeks=num)
    elif unit == 'm':
        return datetime.timedelta(days=num * 30)  # Calculate based on 30 days per month
    else:
        raise argparse.ArgumentTypeError("Invalid retention age. Use format 'Nd', 'Nw', or 'Nm' (N=integer).")

def create_snapshot(logger, error_logger, dataset, dry_run=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    snapshot_name = f"SnapBeforeWatchTower-Date-{timestamp}"
    full_snapshot_name = f"{dataset}@{snapshot_name}"
    logger.info(f"Creating snapshot of: {dataset}")
    logger.debug(f"Full snapshot name: {full_snapshot_name}")

    if dry_run:
        logger.info("")
        logger.info(f"[DRY-RUN] Would create snapshot: {full_snapshot_name}")
        return

    try:
        subprocess.run(["zfs", "snapshot", full_snapshot_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
    except subprocess.CalledProcessError as e:
        print_separator(logger, error_logger)
        error_logger.error(f"Error creating snapshot of {dataset}. Command output: {e.stderr.strip()}")
        raise e

def extract_snapshot_date(snapshot_name):
    # Assuming the snapshot name has the format 'SnapBeforeWatchTower-Date2023-05-28_09_33_17'
    date_str = snapshot_name.split('Date', 1)[-1]
    return datetime.datetime.strptime(date_str, "%Y-%m-%d_%H_%M_%S")

def is_older_than(logger, error_logger, snapshot_date_str, older_than):
    try:
        snapshot_date = datetime.datetime.strptime(snapshot_date_str, "%Y-%m-%d_%H_%M_%S")
        return datetime.datetime.now() - snapshot_date > older_than
    except ValueError as e:
        error_logger.error(f"Date conversion error: {str(e)}")
        return False  # Assume not older to prevent accidental deletion

   
def delete_old_snapshots(
    logger: logging.Logger,
    error_logger: logging.Logger,
    dataset: str,
    older_than: datetime.timedelta,
    retain_count: int,
    dry_run=False
) -> None:
    """
    Correct retention behavior:
      - always keep the newest `retain_count` matching snapshots (by parsed timestamp)
      - for older snapshots beyond that, delete only those older than cutoff

    Snapshot name pattern expected:
      SnapBeforeWatchTower-Date-YYYY-MM-DD_HH_MM_SS
      (also accepts DateYYYY... or Date-YYYY... via regex)
    """
    snap_regex = re.compile(
        r"^(?P<full>.+)@SnapBeforeWatchTower-Date-?(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}_\d{2}_\d{2})$"
    )

    # List snapshots (non-recursive, matching your current behavior)
    # If you want recursive, change to: ["zfs","list","-H","-t","snapshot","-o","name","-r",dataset]
    proc = run_cmd(["zfs", "list", "-H", "-t", "snapshot", "-o", "name", dataset], logger, error_logger, check=True)
    if proc.returncode != 0:
        error_logger.error(f"Error listing snapshots for {dataset}: {proc.stderr.strip()}")
        return

    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return

    snaps = []
    for s in lines:
        m = snap_regex.match(s)
        if not m:
            continue
        ts_str = m.group("ts")
        try:
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d_%H_%M_%S")
        except ValueError as e:
            error_logger.error(f"Skipping snapshot with unparseable timestamp: {s} ({e})")
            continue
        snaps.append((ts, s))

    if not snaps:
        return

    # Newest first
    snaps.sort(key=lambda x: x[0], reverse=True)

    # Always keep newest retain_count
    keep_set = set(s for _, s in snaps[:max(retain_count, 0)])

    cutoff = datetime.datetime.now() - older_than

    # Only delete snapshots not in keep_set AND older than cutoff
    to_delete = [s for ts, s in snaps if (s not in keep_set and ts < cutoff)]

    logger.info(f"[{dataset}] Found {len(snaps)} matching snapshots (retain_count={retain_count}).")
    logger.info(f"[{dataset}] Cutoff time: {cutoff.strftime('%Y-%m-%d %H:%M:%S')}  (older_than={older_than})")
    logger.info(f"[{dataset}] Will delete {len(to_delete)} snapshot(s).")

    logger.info("")

    if not to_delete:
        logger.info(f"[{dataset}] Nothing to delete.")
        return

    for snap_name in to_delete:
        run_cmd(
            ["zfs", "destroy", snap_name],
            logger=logger,
            error_logger=error_logger,
            check=True,
            dry_run=dry_run,
        )
        if dry_run:
            logger.info(f"[DRY-RUN] Would delete snapshot: {snap_name}")
        else:
            logger.info(f"Deleted snapshot: {snap_name}")


def delete_old_files(
    logger: logging.Logger,
    error_logger: logging.Logger,
    log_folder: str,
    older_than: datetime.timedelta,
    retain_count: int,
    dry_run=False
) -> None:
    """
    Deletes old log groups (.log/.err/.digest) based on embedded timestamp, while keeping
    at least `retain_count` newest timestamp groups overall.

    Fixes the edge case where `eligible_for_deletion[:-0]` would become empty.
    """
    os.makedirs(log_folder, exist_ok=True)

    # Matches:
    #   SnapBeforeWatchTower-Date-YYYY-MM-DD_HH_MM_SS.log|err|digest
    # and some minor variations you already support
    date_pattern = re.compile(
        r"SnapBeforeWatchTower[-_][Dd]ate[-_]?(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}_\d{2}_\d{2})\.(?P<ext>log|err|digest)$"
    )

    files_by_ts: dict[datetime.datetime, List[str]] = {}

    for filename in os.listdir(log_folder):
        m = date_pattern.search(filename)
        if not m:
            continue
        ts_str = m.group("ts")
        try:
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d_%H_%M_%S")
        except ValueError:
            continue
        files_by_ts.setdefault(ts, []).append(filename)

    if not files_by_ts:
        return

    # Oldest -> newest
    all_dates = sorted(files_by_ts.keys())

    cutoff = datetime.datetime.now() - older_than
    eligible = [d for d in all_dates if d < cutoff]

    # Ensure we keep at least `retain_count` newest groups overall
    keep_needed = max(retain_count, 0)
    currently_kept = len(all_dates) - len(eligible)

    if currently_kept < keep_needed:
        # We must retain some of the newest dates from the eligible list
        to_retain = keep_needed - currently_kept
        if to_retain > 0:
            eligible = eligible[:-to_retain]  # keep newest `to_retain` among eligible

    # Delete all files for the remaining eligible date groups
    for d in eligible:
        for filename in files_by_ts.get(d, []):
            path_to_file = os.path.join(log_folder, filename)
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete file: {filename}")
            else:
                try:
                    os.remove(path_to_file)
                    logger.info(f"Deleted file: {filename}")
                except Exception as e:
                    error_logger.error(f"Failed to delete file: {filename}. Error: {e}")

def print_separator(logger, error_logger=None):
    separator_length = 20
    separator = "\n" + "\n" + "-" * separator_length + "\n"
    
    if error_logger:
        error_logger.error(separator)
    else:
        logger.info(separator)

def save_docker_image_digests(
    logger: logging.Logger,
    error_logger: logging.Logger,
    log_folder: str,
    log_date: str,
    dry_run=False
) -> Optional[str]:
    """
    Save `docker images --digests` output to a .digest file that shares the same
    timestamp as the .log/.err group for this run.

    Returns the digest filepath on success, or None on failure.
    """

    if dry_run:
        logger.info("[DRY-RUN] Would collect docker image digests")
        return None

    os.makedirs(log_folder, exist_ok=True)

    filename = f"SnapBeforeWatchTower-Date-{log_date}.digest"
    filepath = os.path.join(log_folder, filename)

    # Run docker and capture output
    proc = subprocess.run(
        ["docker", "images", "--digests"],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        # Don’t leave behind an empty/partial file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        error_logger.error("Failed to collect docker image digests.")
        if proc.stderr.strip():
            error_logger.error(proc.stderr.strip())
        else:
            error_logger.error("No stderr from docker. Is the Docker daemon running?")
        return None

    # Write output only on success
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(proc.stdout)
        logger.info(f"Wrote docker image digests: {filepath}")
        return filepath
    except Exception as e:
        error_logger.error(f"Failed to write digest file {filepath}: {e}")
        return None


def load_app_config(path):
    """Load and validate the single TOML configuration file used by the application."""
    config_path = Path(path).expanduser().resolve()
    with config_path.open('rb') as handle:
        document = tomllib.load(handle)
    if not isinstance(document, dict):
        raise ValueError('configuration root must be a TOML table')

    supported_sections = {'application', 'mail', 'mqtt'}
    unknown_sections = set(document) - supported_sections
    if unknown_sections:
        names = ', '.join(sorted(unknown_sections))
        raise ValueError(f'unsupported configuration section(s): {names}')

    application = document.get('application')
    if not isinstance(application, dict):
        raise ValueError('missing required [application] table')
    app_keys = {'command', 'dataset_file', 'older_than', 'retain_count', 'dry_run'}
    unknown_app = set(application) - app_keys
    if unknown_app:
        names = ', '.join(sorted(unknown_app))
        raise ValueError(f'[application] contains unsupported key(s): {names}')
    missing_app = app_keys - set(application)
    if missing_app:
        names = ', '.join(sorted(missing_app))
        raise ValueError(f'[application] is missing required key(s): {names}')

    command = application['command']
    if command not in {'create', 'delete'}:
        raise ValueError('[application].command must be "create" or "delete"')

    dataset_file = application['dataset_file']
    if not isinstance(dataset_file, str) or not dataset_file.strip() or '\0' in dataset_file:
        raise ValueError('[application].dataset_file must be a nonempty string without NUL')
    dataset_path = Path(dataset_file.strip()).expanduser()
    if not dataset_path.is_absolute():
        dataset_path = config_path.parent / dataset_path
    dataset_path = dataset_path.resolve()

    older_than_raw = application['older_than']
    if not isinstance(older_than_raw, str):
        raise ValueError('[application].older_than must be a string such as "7d", "2w", or "1m"')
    try:
        older_than = parse_older_than(older_than_raw.strip())
    except argparse.ArgumentTypeError as exc:
        raise ValueError(f'[application].older_than: {exc}') from exc

    retain_count = application['retain_count']
    if type(retain_count) is not int:
        raise ValueError('[application].retain_count must be an integer')
    dry_run = application['dry_run']
    if type(dry_run) is not bool:
        raise ValueError('[application].dry_run must be true or false')

    mail = document.get('mail', {})
    if not isinstance(mail, dict):
        raise ValueError('[mail] must be a TOML table')
    mail_keys = {'enabled', 'recipient', 'on_success'}
    unknown_mail = set(mail) - mail_keys
    if unknown_mail:
        names = ', '.join(sorted(unknown_mail))
        raise ValueError(f'[mail] contains unsupported key(s): {names}')
    mail_enabled = mail.get('enabled', False)
    if type(mail_enabled) is not bool:
        raise ValueError('[mail].enabled must be true or false')
    mail_on_success = mail.get('on_success', False)
    if type(mail_on_success) is not bool:
        raise ValueError('[mail].on_success must be true or false')
    recipient = mail.get('recipient', '')
    if not isinstance(recipient, str) or '\0' in recipient:
        raise ValueError('[mail].recipient must be a string without NUL')
    recipient = recipient.strip()
    if mail_enabled and not recipient:
        raise ValueError('[mail].recipient must be set when [mail].enabled=true')
    if not mail_enabled:
        recipient = None
        mail_on_success = False

    mqtt = document.get('mqtt', {})
    if not isinstance(mqtt, dict):
        raise ValueError('[mqtt] must be a TOML table')
    mqtt_enabled = mqtt.get('enabled', False)
    if type(mqtt_enabled) is not bool:
        raise ValueError('[mqtt].enabled must be true or false')
    mqtt_values = dict(mqtt)
    mqtt_values.pop('enabled', None)
    mqtt_config = validate_mqtt_config(
        mqtt_values,
        base_dir=config_path.parent,
        dry_run=dry_run,
        enabled=mqtt_enabled,
    )

    args = argparse.Namespace(
        command=command,
        file=str(dataset_path),
        older_than=older_than,
        retain_count=retain_count,
        send_mail=recipient,
        mail_on_success=mail_on_success,
        dry_run=dry_run,
        config_path=str(config_path),
    )
    return args, mqtt_config


def main():
    parser = argparse.ArgumentParser(
        add_help=False,
        usage='%(prog)s -c CONFIG',
        description='Run SnapBeforeWatchTower using one TOML configuration file.',
    )
    parser.add_argument('-c', metavar='CONFIG', required=True, help='Path to the TOML configuration file')
    cli = parser.parse_args()
    try:
        args, mqtt_config = load_app_config(cli.c)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(f'Cannot load configuration: {exc}')
    with RunReporter(mqtt_config, args.command, __version__, dry_run=args.dry_run) as reporter:
        run(args, reporter)


def run(args, reporter):
    """Execute the original operation flow with an attached final-outcome observer."""
    global err_filepath
    
    dry_run = args.dry_run

    log_date = datetime.datetime.now().strftime('%Y-%m-%d_%H_%M_%S')
    # Pick log folder: root-only folder if root, otherwise /tmp fallback
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    preferred_log_folder = os.path.join(SCRIPT_DIR, "logs")
    log_folder = pick_log_folder(preferred_log_folder)

    # Create separate loggers for main logs and error logs
    logger, error_logger, err_filepath = setup_logger(log_folder, log_date)
    reporter.attach(error_logger)

    if dry_run:
        logger.info("========== DRY-RUN MODE ENABLED ==========")

    # If not root: log once, optionally mail, and exit BEFORE running zfs/docker/etc.
    if os.geteuid() != 0:
        msg = (
            "This script must be run as root (sudo). "
            f"Logs were written to: {log_folder} (fallback, because not root)."
        )
        error_logger.error(msg)

        if args.send_mail:
            try:
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    subject="SnapBeforeWatchTower FAILED - not run as root",
                    intro=msg,
                )
            except Exception as mail_e:
                error_logger.error(f"Additionally failed to send mail: {mail_e}")

        sys.exit(1)

    had_error = False
    missing_datasets = []

    try:
        # Read the dataset file inside the try block, so bad paths also trigger error mail.
        with open(args.file, "r", encoding="utf-8") as file:
            datasets = [ln.strip() for ln in file.read().splitlines() if ln.strip()]

        if args.command == 'create':
            save_docker_image_digests(logger, error_logger, log_folder, log_date, dry_run=dry_run)

            print_separator(logger)
            logger.info("Starting snapshot creation..." + (" [DRY-RUN]" if dry_run else ""))

            for dataset in datasets:

                print_separator(logger)

                try:
                    create_snapshot(logger, error_logger, dataset, dry_run=dry_run)

                    # 🔹 NEW: spacing between create and stats
                    logger.info("")

                    delete_old_snapshots(logger, error_logger, dataset, args.older_than, args.retain_count, dry_run=dry_run)
                except (subprocess.CalledProcessError, CommandError) as exc:
                    if remember_missing_dataset(error_logger, missing_datasets, dataset, exc):
                        continue
                    raise

            print_separator(logger)
            if missing_datasets:
                logger.info("Snapshot creation processing completed; missing datasets were skipped and recorded as a final failure.")
            else:
                logger.info("Snapshot creation completed.")

            delete_old_files(logger, error_logger, log_folder, args.older_than, args.retain_count, dry_run=dry_run)

        elif args.command == 'delete':
            print_separator(logger)
            logger.info("Starting snapshot deletion..." + (" [DRY-RUN]" if dry_run else ""))

            print_separator(logger)

            for dataset in datasets:
                try:
                    delete_old_snapshots(logger, error_logger, dataset, args.older_than, args.retain_count, dry_run=dry_run)
                except CommandError as exc:
                    if remember_missing_dataset(error_logger, missing_datasets, dataset, exc):
                        print_separator(logger)
                        continue
                    raise
                # 🔹 NEW: spacing between create and stats
                print_separator(logger)


            if missing_datasets:
                logger.info("Snapshot deletion processing completed; missing datasets were skipped and recorded as a final failure.")
            else:
                logger.info("Snapshot deletion completed.")

            print_separator(logger)

            delete_old_files(logger, error_logger, log_folder, args.older_than, args.retain_count, dry_run=dry_run)

        if missing_datasets:
            raise MissingDatasetsError(missing_datasets)

    except MissingDatasetsError as e:
        had_error = True
        error_logger.error(f"Run failed because one or more configured datasets are missing: {e}")

        if args.send_mail:
            try:
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    subject="SnapBeforeWatchTower FAILED - missing dataset",
                    intro=(
                        "SnapBeforeWatchTower processed the remaining configured datasets, but the run "
                        f"failed because one or more ZFS datasets do not exist. {e}"
                    ),
                )
            except Exception as mail_e:
                error_logger.error(f"Additionally failed to send mail: {mail_e}")
        raise

    except Exception as e:
        had_error = True
        error_logger.error(f"Fatal error: {e}")

        # Send error mail when mail is enabled.
        if args.send_mail:
            try:
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    subject="SnapBeforeWatchTower FAILED - logs attached",
                    intro="SnapBeforeWatchTower failed. See attached logs.",
                )
            except Exception as mail_e:
                error_logger.error(f"Additionally failed to send mail: {mail_e}")
        raise

    finally:
        # If run was successful and user asked for mail on success
        if (not had_error) and args.send_mail and args.mail_on_success:
            try:
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    subject="SnapBeforeWatchTower SUCCESS - logs attached",
                    intro="SnapBeforeWatchTower completed successfully. Logs attached.",
                )
            except Exception as mail_e:
                error_logger.error(f"Failed to send success mail: {mail_e}")

        # Check if the .err file is empty, and remove it if it is
        if os.path.exists(err_filepath) and os.path.getsize(err_filepath) == 0:
            os.remove(err_filepath)

if __name__ == "__main__":
    main()
