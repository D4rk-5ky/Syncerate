"""Real child-process regressions for a full receive pool and bounded delivery."""

import io
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

try:
    import paho.mqtt.publish
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
from pathlib import Path
from unittest import mock

from syncerate.app import main
from syncerate.config import load_app_config
from syncerate.errors import EXIT_STORAGE_FULL, SyncerateError
from syncerate.models import DatasetPair
from syncerate.notifications import _run_notification, send_mail
from syncerate.process_utils import terminate_process_group
from syncerate.syncoid_runner import run_replications
from tests.helpers import make_config, make_logger, no_logging_context, write_executable
from tests.test_config import BASE


def receive_mqtt_packet(connection):
    """Read one MQTT packet from a timeout-bounded local test connection."""
    header = connection.recv(1)
    if not header:
        raise EOFError("No MQTT packet")
    size, multiplier = 0, 1
    for _ in range(4):
        part = connection.recv(1)
        if not part:
            raise EOFError("Incomplete MQTT size")
        size += (part[0] & 127) * multiplier
        if part[0] < 128:
            break
        multiplier *= 128
    data = bytearray()
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise EOFError("Incomplete MQTT payload")
        data.extend(part)
    return header[0], bytes(data)


class StorageFailureTests(unittest.TestCase):
    def run_output(self, output, *, body_prefix="", split=False, **overrides):
        """Emit diagnostics then stall, letting a broken monitor fail within seconds."""
        with tempfile.TemporaryDirectory() as td:
            body = "import time, sys\n" + body_prefix
            if split:
                body += f"\nfor part in {list(output)!r}:\n    sys.stdout.write(part); sys.stdout.flush(); time.sleep(0.001)\n"
            else:
                body += f"sys.stdout.write({output!r}); sys.stdout.flush()\n"
            body += "time.sleep(10)\n"
            script = write_executable(Path(td) / "fake.py", body)
            cfg = make_config(
                syncoid_command=f"{shlex.quote(script)} SourceDataSet DestDataSet",
                **overrides,
            )
            started = time.monotonic()
            with self.assertRaises(SyncerateError) as caught:
                run_replications(cfg, no_logging_context(),
                                 [DatasetPair("pool/data", "backup/data", ())],
                                 None, make_logger())
            self.assertEqual(caught.exception.exit_code, EXIT_STORAGE_FULL)
            self.assertLess(time.monotonic() - started, 7)
            return caught.exception

    def test_reported_error_without_newline_stops_hanging_receive(self):
        error = self.run_output(
            "INFO: Sending incremental pool/data@snap ... next\r\n"
            "mbuffer: warning: HOME environment variable not set - unable to find defaults file\r\n"
            "cannot receive incremental stream: out of space               ]   0% ETA 0:00:00"
        )
        self.assertIn("out of space", error.child_before + error.child_warning)

    def test_split_error_and_quota_variants_stop_without_eof(self):
        for diagnostic in (
            "cannot receive new filesystem stream: out of space",
            "cannot receive incremental stream: No space left on device",
            "cannot receive: disk quota exceeded",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.run_output(diagnostic, split=True)

    def test_storage_error_overrides_recovery_and_buffered_broken_pipe(self):
        for prefix in (
            "Broken pipe\r\n",
            "snapshot used in the initial send no longer exists\r\n",
            "could not find any snapshots to destroy; check snapshot names.\r\n",
        ):
            with self.subTest(prefix=prefix):
                self.run_output(prefix + "cannot receive: out of space\r\n",
                                retry_broken_pipe=True, broken_pipe_retry_count=0)

    def test_benign_dataset_name_does_not_trigger_storage_failure(self):
        with tempfile.TemporaryDirectory() as td:
            script = write_executable(Path(td) / "ok.py",
                                      "print('INFO: Sending incremental pool/out of space@snap')\n")
            cfg = make_config(syncoid_command=f"{script} SourceDataSet DestDataSet")
            run_replications(cfg, no_logging_context(),
                             [DatasetPair("pool/data", "backup/data", ())], None, make_logger())

    def test_delayed_storage_reason_after_broken_pipe_is_not_retried(self):
        self.run_output("cannot receive: out of space",
                        body_prefix="print('Broken pipe', flush=True); time.sleep(0.1)\n",
                        retry_broken_pipe=True, broken_pipe_retry_count=0)

    def test_stale_receive_recovery_still_completes(self):
        with tempfile.TemporaryDirectory() as td:
            script = write_executable(Path(td) / "recover.py",
                "print('snapshot used in the initial send no longer exists', flush=True)\n"
                "print('Broken pipe', flush=True)\n"
                "print('WARN: resetting partially receive state because the snapshot source no longer exists', flush=True)\n"
                "print('INFO: Sending incremental pool/data@snap ... next', flush=True)\n")
            cfg = make_config(syncoid_command=f"{script} SourceDataSet DestDataSet",
                              retry_broken_pipe=True, broken_pipe_retry_count=0)
            summary = run_replications(cfg, no_logging_context(),
                                      [DatasetPair("pool/data", "backup/data", ())], None, make_logger())
            self.assertFalse(summary.has_broken_pipe_warning)

    def test_stubborn_pipeline_helper_is_stopped_even_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as td:
            pid_file = Path(td) / "pid"
            heartbeat = Path(td) / "heartbeat"
            helper = (
                "import os, signal, time; from pathlib import Path; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "signal.signal(signal.SIGHUP, signal.SIG_IGN); "
                f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
                f"for n in range(500):\n    Path({str(heartbeat)!r}).write_text(str(n)); time.sleep(0.02)"
            )
            prefix = (
                "import subprocess, os\nfrom pathlib import Path\n"
                f"subprocess.Popen([{sys.executable!r}, '-c', {helper!r}])\n"
                f"while not Path({str(pid_file)!r}).exists(): time.sleep(0.01)\n"
                "print('cannot receive incremental stream: out of space', flush=True)\n"
                "os._exit(0)\n"
            )
            try:
                self.run_output("", body_prefix=prefix)
                last_heartbeat = heartbeat.read_text()
                time.sleep(0.2)
                self.assertEqual(heartbeat.read_text(), last_heartbeat)
            finally:
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_own_process_group_is_never_signalled(self):
        with self.assertRaises(ValueError):
            terminate_process_group(os.getpgrp())

    @unittest.skipUnless(MQTT_AVAILABLE, "Optional paho-mqtt is not installed")
    def test_full_pool_reaches_mail_and_json_failure_and_skips_next_dataset(self):
        for logging_enabled in (True, False):
            with self.subTest(logging_enabled=logging_enabled), tempfile.TemporaryDirectory() as td:
                directory = Path(td)
                calls = directory / "calls"
                script = write_executable(directory / "fake.py",
                    "import sys, time\nfrom pathlib import Path\n"
                    f"with Path({str(calls)!r}).open('a') as f: f.write(sys.argv[1] + '\\n')\n"
                    "print('cannot receive incremental stream: out of space', flush=True)\n"
                    "time.sleep(4)\n")
                source, dest = directory / "source", directory / "dest"
                source.write_text("pool/data\npool/later\n")
                dest.write_text("backup/data\nbackup/later\n")
                config_text = (BASE.replace("/tmp/source", str(source))
                               .replace("/tmp/dest", str(dest))
                               .replace("syncoid SourceDataSet", f"{script} SourceDataSet")
                               .replace("Mail = No", "Mail = example@example.test")
                               .replace("SystemAction = No", "SystemAction = echo forbidden")
                               .replace("MQTT_JSON_Status = No", "MQTT_JSON_Status = Yes")
                               .replace("RetryBrokenPipe = No", "RetryBrokenPipe = Yes"))
                if logging_enabled:
                    config_text = config_text.replace("LogDestination = No", f"LogDestination = {directory}/logs")
                config_text += "broker_address = example.invalid\nbroker_port = 1883\nmqtt_json_topic = test/status\n"
                config = directory / "config.cfg"
                config.write_text(config_text)
                with mock.patch("syncerate.notifications._run_notification", return_value=None) as publish, \
                     mock.patch("syncerate.notifications.send_mail", return_value=(0, "")) as mail, \
                     mock.patch("syncerate.app.SystemAction") as action, \
                     mock.patch("sys.stdout", io.StringIO()):
                    self.assertEqual(main(["-c", str(config)]), EXIT_STORAGE_FULL)
                self.assertEqual(calls.read_text(), "pool/data\n")
                action.assert_not_called()
                mail.assert_called_once()
                self.assertIn("out of space", mail.call_args.args[1])
                publish.assert_called_once()
                messages = publish.call_args.args[1]["msgs"]
                self.assertEqual(len(messages), 1)
                self.assertFalse(messages[0]["retain"])
                payload = json.loads(messages[0]["payload"])
                self.assertEqual(payload["status"], "failure")
                self.assertEqual(payload["exit_code"], EXIT_STORAGE_FULL)
                self.assertIn("out of space", payload["stderr"])
                if logging_enabled:
                    self.assertIn("out of space", next((directory / "logs").glob("*.err")).read_text())

    @unittest.skipUnless(MQTT_AVAILABLE, "Optional paho-mqtt is not installed")
    def test_cli_delivers_failure_to_local_broker_and_fake_mail_command(self):
        """Exercise source CLI and spawned delivery workers without mocking delivery."""
        with tempfile.TemporaryDirectory() as td, socket.socket() as broker:
            directory = Path(td)
            broker.bind(("127.0.0.1", 0))
            broker.listen(1)
            broker.settimeout(15)
            received, errors = [], []

            def serve():
                """Accept CONNECT, return CONNACK, and capture a single PUBLISH."""
                try:
                    with broker.accept()[0] as connection:
                        connection.settimeout(10)
                        header, _ = receive_mqtt_packet(connection)
                        if header != 0x10:
                            raise ValueError("Expected CONNECT")
                        connection.sendall(b"\x20\x02\x00\x00")
                        received.append(receive_mqtt_packet(connection))
                except Exception as exc:
                    errors.append(exc)

            server = threading.Thread(target=serve, daemon=True)
            server.start()
            mail_record = directory / "mail.json"
            write_executable(directory / "mail",
                "import json, sys\nfrom pathlib import Path\n"
                f"Path({str(mail_record)!r}).write_text(json.dumps({{'args': sys.argv[1:], 'body': sys.stdin.read()}}))\n")
            script = write_executable(directory / "fake.py",
                "import time\nprint('cannot receive incremental stream: out of space', flush=True)\ntime.sleep(15)\n")
            (directory / "source").write_text("pool/data\n")
            (directory / "dest").write_text("backup/data\n")
            config_text = (BASE.replace("/tmp/source", str(directory / "source"))
                           .replace("/tmp/dest", str(directory / "dest"))
                           .replace("syncoid SourceDataSet", f"{script} SourceDataSet")
                           .replace("Mail = No", "Mail = example@example.test")
                           .replace("MQTT_JSON_Status = No", "MQTT_JSON_Status = Yes"))
            config_text += (f"broker_address = 127.0.0.1\nbroker_port = {broker.getsockname()[1]}\n"
                            "mqtt_json_topic = test/status\nNotificationTimeoutSeconds = 5\n")
            config = directory / "config.cfg"
            config.write_text(config_text)
            environment = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ.get("PATH", ""))
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / "Syncerate.py"), "-c", str(config)],
                env=environment, capture_output=True, text=True, timeout=20,
            )
            server.join(timeout=1)
            self.assertEqual(result.returncode, EXIT_STORAGE_FULL, result.stdout + result.stderr)
            self.assertEqual(errors, [])
            self.assertEqual(len(received), 1, result.stdout + result.stderr)
            header, packet = received[0]
            self.assertEqual(header, 0x30)  # PUBLISH, QoS 0, retain false.
            topic_length = int.from_bytes(packet[:2], "big")
            self.assertEqual(packet[2:2 + topic_length], b"test/status")
            payload = json.loads(packet[2 + topic_length:])
            self.assertEqual(payload["status"], "failure")
            self.assertEqual(payload["exit_code"], EXIT_STORAGE_FULL)
            mail = json.loads(mail_record.read_text())
            self.assertIn("example@example.test", mail["args"])
            self.assertIn("out of space", mail["body"])


class NotificationDeadlineTests(unittest.TestCase):
    def test_notification_timeout_default_and_validation(self):
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config.cfg"
            config.write_text(BASE)
            self.assertEqual(load_app_config(str(config)).notification_timeout_seconds, 30)
            for value in ("0", "-1", "1.5", "No"):
                config.write_text(BASE + f"NotificationTimeoutSeconds = {value}\n")
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_app_config(str(config))

    def test_mail_worker_passes_body_and_returns_stderr_and_exit_status(self):
        result = _run_notification("mail", {
            "command": [sys.executable, "-c",
                        "import sys; assert sys.stdin.read() == 'body'; sys.stderr.write('reason'); sys.exit(7)"],
            "body": "body",
        }, 5)
        self.assertEqual(result, (7, "reason"))

    def test_hung_mail_command_is_bounded(self):
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "mail delivery timed out"):
            _run_notification("mail", {
                "command": [sys.executable, "-c", "import time; time.sleep(10)"],
                "body": "test",
            }, 1)
        self.assertLess(time.monotonic() - started, 5)

    def test_mail_public_api_preserves_argv_and_timeout(self):
        with mock.patch("syncerate.notifications._run_notification", return_value=(0, "")) as worker:
            send_mail("subject", "body", "example@example.test", ["test.log"], timeout_seconds=9)
        self.assertEqual(worker.call_args.args, (
            "mail", {"command": ["mail", "-s", "subject", "example@example.test", "--attach", "test.log"],
                     "body": "body"}, 9))

    def test_unresponsive_mqtt_broker_is_bounded(self):
        try:
            import paho.mqtt.publish
        except ImportError:
            self.skipTest("Optional paho-mqtt dependency is not installed")
        # TCP connects, but no MQTT CONNACK ever arrives. This must not prevent exit.
        with socket.socket() as broker:
            broker.bind(("127.0.0.1", 0))
            broker.listen(1)
            started = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "mqtt delivery timed out"):
                _run_notification("mqtt", {
                    "msgs": [{"topic": "test/status", "payload": "test", "retain": False}],
                    "hostname": "127.0.0.1", "port": broker.getsockname()[1],
                }, 1)
            self.assertLess(time.monotonic() - started, 5)

    @unittest.skipUnless(MQTT_AVAILABLE, "Optional paho-mqtt is not installed")
    def test_mqtt_timeout_preserves_replication_failure_and_mail_is_attempted(self):
        from syncerate.notifications import send_error_mail, send_mqtt_failure_status
        cfg = make_config(mqtt_json_status=True, mail_option="example@example.test")
        cfg.raw_config.read_dict({"Syncerate Config": {
            "broker_address": "example.invalid", "broker_port": "1883", "mqtt_json_topic": "test/status"}})
        error = SyncerateError("Storage full", EXIT_STORAGE_FULL, kind="known_child")
        with mock.patch("syncerate.notifications._run_notification", side_effect=TimeoutError("stalled")), \
             mock.patch("syncerate.notifications.send_mail", return_value=(0, "")) as mail:
            send_mqtt_failure_status(error, cfg, make_logger())
            send_error_mail(error, cfg, no_logging_context(), make_logger())
        mail.assert_called_once()
        self.assertEqual(error.exit_code, EXIT_STORAGE_FULL)


if __name__ == "__main__":
    unittest.main()
