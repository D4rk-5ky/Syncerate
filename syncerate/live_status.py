"""Optional, best-effort live MQTT/HA reporting for a single locked TOML backup.

Unlike legacy completion notifications, this client runs in Paho's network
thread, never blocks Syncoid, and never changes Syncerate's exit status.
Only the owner of the per-TOML lock may publish the live status/last result.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .models import AppConfig, DatasetPair, ReplicationSummary


def utc_timestamp() -> str:
    """Return an unambiguous machine-readable UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def backup_identity(config_path: str, hostname: Optional[str] = None) -> tuple[str, str]:
    """Derive a stable, topic-safe ID from host and the canonical TOML path."""
    machine = hostname or socket.gethostname()
    canonical = str(Path(config_path).resolve(strict=False))
    stem = re.sub(r"[^a-z0-9_-]+", "_", Path(canonical).stem.lower()).strip("_") or "backup"
    host_label = re.sub(r"[^a-z0-9_-]+", "_", machine.lower()).strip("_") or "host"
    fingerprint = hashlib.sha256(f"{machine}\0{canonical}".encode("utf-8")).hexdigest()[:12]
    return f"{host_label[:30]}_{stem[:40]}_{fingerprint}", machine


def discovery_messages(monitor: "LiveBackupMonitor") -> list[dict[str, Any]]:
    """Build retained HA MQTT discovery for live sensors and the last result."""
    cfg = monitor.config
    if not cfg.live_mqtt_discovery:
        return []
    device = {
        "identifiers": [f"syncerate_{monitor.backup_id}"],
        "name": f"Syncerate: {monitor.backup_name}",
        "manufacturer": "Syncerate",
        "model": "ZFS Syncoid backup",
    }
    live = {
        "status": ("Status", "value_json.status", None),
        "current_dataset": ("Current dataset", "value_json.current_dataset", None),
        "total_datasets": ("Total datasets", "value_json.total_datasets", None),
        "completed_datasets": ("Completed datasets", "value_json.completed_datasets", None),
        "failed_datasets": ("Failed datasets", "value_json.failed_datasets", None),
        "data_transferred_bytes": ("Data transferred", "value_json.data_transferred_bytes", "B"),
        "runtime_seconds": ("Runtime", "value_json.runtime_seconds", "s"),
        "last_heartbeat": ("Last heartbeat", "value_json.last_heartbeat", None),
    }
    messages = []
    for key, (name, template, unit) in live.items():
        payload = {
            "name": name,
            "unique_id": f"syncerate_{monitor.backup_id}_{key}",
            "object_id": f"syncerate_{monitor.backup_id}_{key}",
            "device": device,
            "state_topic": monitor.status_topic,
            "value_template": "{{ " + template + " }}",
            "expire_after": cfg.live_heartbeat_seconds * 3,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if key == "last_heartbeat":
            payload["device_class"] = "timestamp"
        messages.append({
            "topic": f"homeassistant/sensor/syncerate_{monitor.backup_id}/{key}/config",
            "payload": json.dumps(payload, separators=(",", ":")),
            "qos": 1,
            "retain": True,
        })
    payload = {
        "name": "Last result",
        "unique_id": f"syncerate_{monitor.backup_id}_last_result",
        "object_id": f"syncerate_{monitor.backup_id}_last_result",
        "device": device,
        "state_topic": monitor.last_result_topic,
        "value_template": "{{ value_json.status }}",
        "json_attributes_topic": monitor.last_result_topic,
    }
    messages.append({
        "topic": f"homeassistant/sensor/syncerate_{monitor.backup_id}/last_result/config",
        "payload": json.dumps(payload, separators=(",", ":")),
        "qos": 1,
        "retain": True,
    })
    return messages


class LiveBackupMonitor:
    """Publish optional non-retained heartbeats and retained last results.

    A persistent Paho client handles network I/O in its own thread. Any broker,
    import, or network failure logs a warning, never changes replication state.
    """

    def __init__(self, config: AppConfig, logger: logging.Logger, *, dry_run: bool = False) -> None:
        self.config = config
        self.logger = logger
        self.backup_id, self.hostname = backup_identity(config.config_path)
        self.backup_name = config.live_backup_name or config.backup_title or Path(config.config_path).stem
        self.run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.status_topic = f"syncerate/{self.backup_id}/status"
        self.last_result_topic = f"syncerate/{self.backup_id}/last_result"
        self.events_topic = f"syncerate/{self.backup_id}/events"
        self.started_at = utc_timestamp()
        self.start_monotonic = time.monotonic()
        self.dry_run = dry_run
        self._lock = threading.Lock()
        self._stop_signal = threading.Event()
        self._connected = threading.Event()
        self._client: Any = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._started_event_sent = False
        self._completed = False
        self._last_result: Optional[str] = None
        self._state: dict[str, Any] = {
            "status": "running",
            "current_dataset": "",
            "total_datasets": 0,
            "completed_datasets": 0,
            "failed_datasets": 0,
            "data_transferred_bytes": 0,
            "data_transferred_complete": False,
        }

    def _publish(self, topic: str, payload: str, *, retain: bool = False, qos: int = 0) -> Any:
        """Queue a message without waiting for broker acknowledgement."""
        if self._client is None or not self._connected.is_set():
            return None
        try:
            result = self._client.publish(topic, payload, qos=qos, retain=retain)
            if getattr(result, "rc", 0) != 0:
                self.logger.warning("Live MQTT queue rejected %s (rc=%s)", topic, result.rc)
                return None
            return result
        except Exception as exc:
            self.logger.warning("Live MQTT publish to %s failed: %s", topic, exc)
            return None

    def _payload(self) -> str:
        """Snapshot current counters for a heartbeat or terminal state."""
        with self._lock:
            state = dict(self._state)
        state.update({
            "backup_name": self.backup_name,
            "backup_id": self.backup_id,
            "hostname": self.hostname,
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "runtime_seconds": int(max(0, time.monotonic() - self.start_monotonic)),
            "last_heartbeat": utc_timestamp(),
        })
        return json.dumps(state, ensure_ascii=False, separators=(",", ":"))

    def _heartbeat(self) -> None:
        """Periodically refresh live state without touching the replication thread."""
        while not self._stop_signal.wait(self.config.live_heartbeat_seconds):
            self._publish(self.status_topic, self._payload())

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        """Republish retained discovery and most recent state on reconnection."""
        try:
            if reason_code != 0:
                self.logger.warning("Live MQTT broker refused connection: %s", reason_code)
                return
            self._connected.set()
            for msg in discovery_messages(self):
                self._publish(msg["topic"], msg["payload"], retain=True, qos=1)
            self._publish(self.status_topic, self._payload())
            with self._lock:
                should_send_start = not self._started_event_sent and not self._completed
                if should_send_start:
                    self._started_event_sent = True
                result = self._last_result
            if should_send_start and self.config.live_notify_start:
                self._event("started")
            if result is not None:
                self._publish(self.last_result_topic, result, retain=True, qos=1)
        except Exception as exc:
            self.logger.warning("Live MQTT connection callback failed: %s", exc)

    def _on_disconnect(self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        """Mark broker disconnected; a reconnect will refresh discovery/state."""
        self._connected.clear()

    def _event(self, event_type: str, **fields: Any) -> None:
        """Emit one optional non-retained per-backup event."""
        event = {
            "event": event_type,
            "backup_id": self.backup_id,
            "backup_name": self.backup_name,
            "hostname": self.hostname,
            "run_id": self.run_id,
            "timestamp": utc_timestamp(),
            **fields,
        }
        self._publish(self.events_topic, json.dumps(event, ensure_ascii=False), qos=1)

    def start(self) -> None:
        """Start background MQTT without letting any failure abort this backup."""
        try:
            from paho.mqtt import client as mqtt
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"syncerate_{self.backup_id[:22]}_{uuid.uuid4().hex[:6]}",
            )
            if self.config.mqtt_username.strip():
                self._client.username_pw_set(self.config.mqtt_username.strip(), self.config.mqtt_password)
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.reconnect_delay_set(min_delay=1, max_delay=30)
            self._client.connect_async(self.config.broker_address, self.config.broker_port, keepalive=30)
            self._client.loop_start()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat, daemon=True, name=f"syncerate-heartbeat-{self.backup_id[:16]}"
            )
            self._heartbeat_thread.start()
        except Exception as exc:
            self.logger.warning("Live MQTT disabled for this run (backup continues): %s", exc)
            self.stop()

    def progress(self, stage: str, pair: DatasetPair, summary: ReplicationSummary) -> None:
        """Update one dataset's progress after runner state changes."""
        with self._lock:
            self._state.update({
                "current_dataset": f"{pair.source} -> {pair.destination}",
                "total_datasets": summary.total_datasets,
                "completed_datasets": summary.completed_datasets,
                "failed_datasets": summary.failed_datasets,
                "data_transferred_bytes": summary.transferred_bytes,
                "data_transferred_complete": summary.transfer_measurement_complete,
            })
        # Include the new current dataset immediately when its transfer starts.
        self._publish(self.status_topic, self._payload())

    def planned(self, total: int) -> None:
        """Record validated pair total before any transfer starts."""
        with self._lock:
            self._state["total_datasets"] = total
        self._publish(self.status_topic, self._payload())

    def finish(self, status: str, exit_code: int, *, error: str = "", summary: Optional[ReplicationSummary] = None) -> None:
        """Publish terminal state and retained result once; failures stay best-effort."""
        if self._completed:
            return
        with self._lock:
            if self._completed:
                return
            self._completed = True
            self._state["status"] = status
            if summary is not None:
                self._state.update({
                    "total_datasets": summary.total_datasets,
                    "completed_datasets": summary.completed_datasets,
                    "failed_datasets": summary.failed_datasets,
                    "data_transferred_bytes": summary.transferred_bytes,
                    "data_transferred_complete": summary.transfer_measurement_complete,
                })
        self._stop_signal.set()
        payload = json.loads(self._payload())
        payload.update({"exit_code": exit_code, "error": error, "completed_at": utc_timestamp()})
        result = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._last_result = result
        # Give short jobs a bounded chance to connect. If the optional Paho
        # import failed, do not introduce an unnecessary shutdown delay.
        if self._client is not None:
            self._connected.wait(timeout=0.75)
        self._publish(self.status_topic, result, qos=1)  # non-retained final live state
        self._publish(self.last_result_topic, result, retain=True, qos=1)
        should_notify = (
            (status == "success" and self.config.live_notify_success)
            or (status != "success" and self.config.live_notify_failure)
        )
        if should_notify:
            self._event("completed" if status == "success" else "failed", status=status, exit_code=exit_code, error=error)

    def stop(self) -> None:
        """Release background client on normal return, without blocking replication."""
        self._stop_signal.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=0.3)
        if self._client is not None:
            client = self._client
            # Avoid blocking Syncerate if the MQTT network loop is stuck in a
            # broker/SSL socket operation while the backup finishes.
            def disconnect_background() -> None:
                try:
                    if self._completed and self._connected.is_set():
                        time.sleep(0.15)  # best-effort QoS1 flush
                    client.disconnect()
                    client.loop_stop()
                except Exception as exc:
                    self.logger.warning("Live MQTT shutdown failed: %s", exc)
            cleanup = threading.Thread(target=disconnect_background, daemon=True,
                                       name="syncerate-live-mqtt-cleanup")
            cleanup.start()
            cleanup.join(timeout=0.75)
            if cleanup.is_alive():
                self.logger.warning("Live MQTT shutdown exceeded 0.75 seconds; exiting without waiting for the broker")
        self._connected.clear()


def publish_duplicate_event(config: AppConfig, logger: logging.Logger, *, reason: str, exit_code: int) -> None:
    """Best-effort duplicate rejection event; NEVER touch owner's live/result topics.

    A daemon publisher is bounded to one second, preventing an unreachable broker
    from holding an already rejected process open indefinitely.
    """
    if not config.live_mqtt_enabled or not config.live_notify_failure:
        return
    backup_id, hostname = backup_identity(config.config_path)
    topic = f"syncerate/{backup_id}/events"
    payload = json.dumps({
        "event": "duplicate_rejected", "backup_id": backup_id,
        "backup_name": config.live_backup_name or config.backup_title or Path(config.config_path).stem,
        "hostname": hostname, "timestamp": utc_timestamp(),
        "exit_code": exit_code, "error": reason,
    }, ensure_ascii=False)

    def attempt() -> None:
        try:
            from paho.mqtt import publish
            auth = None
            if config.mqtt_username.strip():
                auth = {"username": config.mqtt_username.strip(), "password": config.mqtt_password}
            publish.single(topic, payload=payload, qos=1, retain=False,
                           hostname=config.broker_address, port=config.broker_port, auth=auth)
        except Exception as exc:
            logger.warning("Live MQTT duplicate-rejection event failed: %s", exc)

    worker = threading.Thread(target=attempt, daemon=True, name="syncerate-duplicate-event")
    worker.start()
    worker.join(timeout=1.0)
    if worker.is_alive():
        logger.warning("Live MQTT duplicate event exceeded its one-second best-effort delivery window")
