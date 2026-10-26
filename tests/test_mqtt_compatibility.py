"""Run callback and loopback packet regressions with each installed Paho version."""
from dataclasses import replace
import json
import socket
import socketserver
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock
from syncerate.errors import SyncerateError
from syncerate.live_status import LiveBackupMonitor, publish_duplicate_event
from syncerate.models import ReplicationSummary
from syncerate.notifications import send_mqtt_failure_status, send_mqtt_messages
from tests.helpers import make_config, make_logger
from tests.test_live_status import FakeClient

def wait_until(predicate, timeout=4):
    """Bound asynchronous assertions so a failed MQTT callback cannot hang tests."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('MQTT condition did not arrive before the test deadline')

class CallbackCompatibilityTests(unittest.TestCase):

    def test_legacy_constructor_and_callbacks_publish_without_v2_enum(self):
        """Reject v2-only kwargs and invoke exactly the Paho 1.x callbacks."""
        clients = []

        class LegacyClient(FakeClient):

            def __init__(self, client_id=''):
                super().__init__()
                self.client_id = client_id
                clients.append(self)

            def reconnect_delay_set(self, **kwargs):
                pass

            def connect_async(self, host, port, keepalive):
                pass

            def loop_start(self):
                self.on_connect(self, None, {}, 0)

            def disconnect(self):
                self.on_disconnect(self, None, 0)
                super().disconnect()
        pkg = ModuleType('paho')
        mqtt = ModuleType('paho.mqtt')
        client = ModuleType('paho.mqtt.client')
        client.Client = LegacyClient
        pkg.mqtt = mqtt
        mqtt.client = client
        m = LiveBackupMonitor(make_config(live_mqtt_enabled=True), make_logger('legacy-paho'))
        try:
            with mock.patch.dict('sys.modules', {'paho': pkg, 'paho.mqtt': mqtt, 'paho.mqtt.client': client}):
                m.start()
            self.assertTrue(m._connected.is_set())
            self.assertEqual(len(clients), 1)
            self.assertTrue(clients[0].client_id.startswith('syncerate_'))
            self.assertEqual(len([v for v in clients[0].messages if v[0].endswith('/config')]), 13)
            m.finish('success', 0)
            self.assertTrue(any((t == m.last_result_topic and r for t, p, q, r in clients[0].messages)))
        finally:
            m.stop()
        self.assertFalse(m._connected.is_set())
        self.assertTrue(clients[0].disconnected)

    def test_connect_refusal_and_disconnect_accept_both_callback_apis(self):
        """Refusal publishes nothing; both disconnect signatures clear connectivity."""
        for modern in (False, True):
            with self.subTest(modern=modern):
                m = LiveBackupMonitor(make_config(), make_logger('callbacks'))
                client = FakeClient()
                m._client = client
                tail = (None,) if modern else ()
                m._on_connect(client, None, {}, 5, *tail)
                self.assertFalse(m._connected.is_set())
                self.assertEqual(client.messages, [])
                m._on_connect(client, None, {}, 0, *tail)
                self.assertTrue(m._connected.is_set())
                tail = ({}, 0, None) if modern else (0,)
                m._on_disconnect(client, None, *tail)
                self.assertFalse(m._connected.is_set())
                m.stop()

    def test_constructor_failure_is_not_retried_as_legacy(self):
        """Unrelated constructor failure stays best-effort, without a legacy retry."""
        pkg = ModuleType('paho')
        mqtt = ModuleType('paho.mqtt')
        client = ModuleType('paho.mqtt.client')
        client.CallbackAPIVersion = SimpleNamespace(VERSION2='v2')
        client.Client = mock.Mock(side_effect=RuntimeError('bad client configuration'))
        pkg.mqtt = mqtt
        mqtt.client = client
        m = LiveBackupMonitor(make_config(), make_logger('constructor-failure'))
        with mock.patch.dict('sys.modules', {'paho': pkg, 'paho.mqtt': mqtt, 'paho.mqtt.client': client}):
            m.start()
        client.Client.assert_called_once()
        self.assertIsNone(m._client)
        m.stop()

class PacketBroker:
    """Minimal test-only MQTT 3.1.1 recorder, supporting CONNECT, QoS0/1 and ping."""

    def __init__(self):
        self.messages = []
        self.credentials = []
        self.clients = set()
        self.lock = threading.Lock()
        owner = self

        class Handler(socketserver.BaseRequestHandler):

            def read_exact(self, length):
                """Read a complete frame fragment, raising EOFError on peer closure."""
                data = bytearray()
                while len(data) < length:
                    chunk = self.request.recv(length - len(data))
                    if not chunk:
                        raise EOFError
                    data.extend(chunk)
                return bytes(data)

            def handle(self):
                """Record publications and send real CONNACK/PUBACK/PINGRESP packets."""
                with owner.lock:
                    owner.clients.add(self.request)
                try:
                    while True:
                        header = self.read_exact(1)[0]
                        size = 0
                        multiplier = 1
                        for _ in range(4):
                            digit = self.read_exact(1)[0]
                            size += (digit & 127) * multiplier
                            if not digit & 128:
                                break
                            multiplier *= 128
                        else:
                            raise ValueError('Invalid remaining length')
                        body = self.read_exact(size)
                        kind = header >> 4
                        if kind == 1:
                            flags = body[7]
                            offset = 10
                            fields = []
                            while offset < len(body):
                                length = int.from_bytes(body[offset:offset + 2], 'big')
                                offset += 2
                                fields.append(body[offset:offset + length].decode())
                                offset += length
                            with owner.lock:
                                owner.credentials.append((flags, fields))
                            self.request.sendall(b' \x02\x00\x00')
                        elif kind == 3:
                            length = int.from_bytes(body[:2], 'big')
                            topic = body[2:2 + length].decode()
                            offset = length + 2
                            qos = header >> 1 & 3
                            packet_id = body[offset:offset + 2] if qos else b''
                            offset += 2 if qos else 0
                            with owner.lock:
                                owner.messages.append((topic, body[offset:].decode(), qos, bool(header & 1)))
                            if qos == 1:
                                self.request.sendall(b'@\x02' + packet_id)
                        elif kind == 12:
                            self.request.sendall(b'\xd0\x00')
                        elif kind == 14:
                            return
                        else:
                            raise ValueError(f'Unexpected MQTT packet {kind}')
                except (OSError, EOFError):
                    pass
                finally:
                    with owner.lock:
                        owner.clients.discard(self.request)

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True
        self.server = Server(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    def drop_clients(self):
        """Force socket loss so the actual Paho client must reconnect."""
        with self.lock:
            clients = list(self.clients)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()

    def snapshot(self):
        """Copy received messages under the fixture lock for asynchronous assertions."""
        with self.lock:
            return list(self.messages)

    def close(self):
        """Close listener and clients, and join the owned listener thread."""
        self.server.shutdown()
        self.drop_clients()
        self.server.server_close()
        self.thread.join(timeout=1)

class RealPahoCompatibilityTests(unittest.TestCase):

    def setUp(self):
        """Use the installed Paho package against an isolated loopback fixture."""
        try:
            from paho.mqtt import client
        except ImportError:
            self.skipTest('Optional paho-mqtt is not installed')
        self.broker = PacketBroker()
        self.addCleanup(self.broker.close)
        self.logger = make_logger('real-paho')
        self.config = make_config(broker_address='127.0.0.1', broker_port=self.broker.port, mqtt_username='fixture-user', mqtt_password='fixture-password', mqtt_topic='compat/legacy', mqtt_message='ON', mqtt_json_topic='compat/json', home_assistant_available='compat/availability')

    def test_all_completion_failure_and_dry_run_routes(self):
        """Verify real helper payloads, auth, topics, QoS and retain across all modes."""
        for legacy, structured in [(True, False), (False, True), (True, True)]:
            cfg = replace(self.config, use_mqtt=legacy, mqtt_json_status=structured, use_home_assistant=True)
            for success, dry in [(True, False), (False, False), (True, True)]:
                with self.subTest(legacy=legacy, structured=structured, success=success, dry_run=dry):
                    start = len(self.broker.snapshot())
                    send_mqtt_messages(cfg, self.logger, success=success, dry_run=dry, exit_code=0 if success else 12)
                    expected = []
                    if legacy and success and (not dry):
                        expected += [('compat/availability', 'online', True), ('compat/legacy', 'ON', True)]
                    if structured or not success or dry:
                        topic = 'compat/json' if structured else 'compat/legacy/dry-run' if dry else 'compat/legacy/error'
                        expected += [(topic, None, False)]
                    wait_until(lambda: len(self.broker.snapshot()) >= start + len(expected))
                    actual = self.broker.snapshot()[start:]
                    self.assertEqual(len(actual), len(expected))
                    for (topic, payload, qos, retained), (target, literal, retain) in zip(actual, expected):
                        self.assertEqual((topic, qos, retained), (target, 0, retain))
                        if literal is not None:
                            self.assertEqual(payload, literal)
                        else:
                            report = json.loads(payload)
                            self.assertEqual((report['success'], report['dry_run']), (success, dry))
        cfg = replace(self.config, use_mqtt=True, send_mqtt_on_success=False)
        send_mqtt_failure_status(SyncerateError('test failure', 12), cfg, self.logger)
        wait_until(lambda: any((json.loads(p)['error'] == 'test failure' for t, p, q, r in self.broker.snapshot() if t.endswith('/error'))))
        self.assertTrue(all((flags & 192 == 192 and fields[-2:] == ['fixture-user', 'fixture-password'] for flags, fields in self.broker.credentials)))

    def test_live_discovery_heartbeat_reconnect_and_last_result(self):
        """Check actual callbacks, measurements, reconnect, events and retained result."""
        cfg = replace(self.config, live_mqtt_enabled=True, live_notify_start=True, live_heartbeat_seconds=0.1)
        m = LiveBackupMonitor(cfg, self.logger)
        self.addCleanup(m.stop)
        m.start()
        wait_until(lambda: len([p for p in self.broker.snapshot() if p[0].endswith('/config')]) == 13)
        initial = len([p for p in self.broker.snapshot() if p[0] == m.status_topic])
        wait_until(lambda: len([p for p in self.broker.snapshot() if p[0] == m.status_topic]) > initial)
        m.transfer_progress({'current_dataset_transferred_bytes': 123, 'current_dataset_progress_percent': 50})
        wait_until(lambda: any((json.loads(p).get('current_dataset_transferred_bytes') == 123 for t, p, q, r in self.broker.snapshot() if t == m.status_topic)))
        self.broker.drop_clients()
        wait_until(lambda: not m._connected.is_set())
        wait_until(lambda: len([p for p in self.broker.snapshot() if p[0].endswith('/config')]) >= 26)
        m.finish('success', 0, summary=ReplicationSummary(total_datasets=1, attempted_datasets=1, completed_datasets=1))
        wait_until(lambda: any((t == m.last_result_topic for t, p, q, r in self.broker.snapshot())))
        wait_until(lambda: any((t == m.events_topic and json.loads(p)['event'] == 'completed' for t, p, q, r in self.broker.snapshot())))
        packets = self.broker.snapshot()
        self.assertTrue(all((q == 1 and r for t, p, q, r in packets if t.endswith('/config') or t == m.last_result_topic)))
        self.assertTrue(all((not r for t, p, q, r in packets if t in (m.status_topic, m.events_topic))))
        self.assertEqual(len([1 for t, p, q, r in packets if t == m.events_topic and json.loads(p)['event'] == 'started']), 1)
        result = next((json.loads(p) for t, p, q, r in packets if t == m.last_result_topic))
        self.assertEqual((result['status'], result['completed_datasets']), ('success', 1))

    def test_duplicate_rejection_uses_single_helper_without_owner_topics(self):
        """Verify publish.single sends a non-retained event without owner updates."""
        publish_duplicate_event(replace(self.config, live_mqtt_enabled=True), self.logger, reason='Already running', exit_code=13)
        wait_until(lambda: len(self.broker.snapshot()) == 1)
        topic, payload, qos, retained = self.broker.snapshot()[0]
        self.assertTrue(topic.endswith('/events'))
        self.assertEqual((qos, retained), (1, False))
        self.assertEqual(json.loads(payload)['event'], 'duplicate_rejected')
if __name__ == '__main__':
    unittest.main()
