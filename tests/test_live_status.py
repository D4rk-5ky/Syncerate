"""Regression tests for opt-in, per-TOML live MQTT and HA Discovery."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from syncerate.config import load_app_config
from syncerate.live_status import (
    LiveBackupMonitor, backup_identity, discovery_messages, publish_duplicate_event,
)
from syncerate.models import DatasetPair, ReplicationSummary
from tests.helpers import make_config, make_logger


class FakeClient:
    def __init__(self):
        self.messages = []
        self.disconnected = False

    def publish(self, topic, payload, qos=0, retain=False):
        self.messages.append((topic, json.loads(payload) if payload.startswith('{') else payload, qos, retain))
        return type('Response', (), {'rc': 0})()

    def disconnect(self):
        self.disconnected = True

    def loop_stop(self):
        pass


class LiveStatusTests(unittest.TestCase):
    def test_identity_distinguishes_host_and_directory_and_resolves_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / 'one' / 'backup.toml'
            b = root / 'two' / 'backup.toml'
            a.parent.mkdir(); b.parent.mkdir()
            a.write_text('', encoding='utf-8')
            b.write_text('', encoding='utf-8')
            alias = root / 'alias.toml'
            alias.symlink_to(a)
            self.assertEqual(backup_identity(str(a), 'node1'), backup_identity(str(alias), 'node1'))
            self.assertNotEqual(backup_identity(str(a), 'node1'), backup_identity(str(b), 'node1'))
            self.assertNotEqual(backup_identity(str(a), 'node1'), backup_identity(str(a), 'node2'))
            self.assertNotIn('/', backup_identity(str(a), 'node1')[0])

    def make_connected(self, **overrides):
        cfg = make_config(config_path='/config/daily.toml', live_mqtt_enabled=True, **overrides)
        m = LiveBackupMonitor(cfg, make_logger('live-test'))
        client = FakeClient()
        m._client = client
        m._on_connect(client, None, None, 0, None)
        return m, client

    def test_ha_discovery_is_retained_unique_and_live_expires(self):
        m, client = self.make_connected(live_heartbeat_seconds=60)
        discoveries = [entry for entry in client.messages if entry[0].endswith('/config')]
        self.assertEqual(len(discoveries), 13)
        self.assertTrue(all(x[3] and x[2] == 1 for x in discoveries))
        self.assertEqual(len({x[1]['unique_id'] for x in discoveries}), 13)
        self.assertTrue(all(x[1]['expire_after'] == 180 for x in discoveries[:-1]))
        self.assertNotIn('expire_after', discoveries[-1][1])
        self.assertEqual(discoveries[0][1]['state_topic'], m.status_topic)
        self.assertEqual(discoveries[-1][1]['state_topic'], m.last_result_topic)
        self.assertEqual(client.messages[-1][0], m.status_topic)
        self.assertFalse(client.messages[-1][3])

    def test_progress_and_end_result_retention_and_event_controls(self):
        m, client = self.make_connected(live_notify_start=False, live_notify_success=True)
        m.planned(3)
        pair = DatasetPair('pool/Docker', 'archive/Docker', ())
        summary = ReplicationSummary(total_datasets=3, attempted_datasets=1, completed_datasets=1,
                                     transferred_bytes=5000)
        m.progress('completed', pair, summary)
        report = [p for t,p,q,r in client.messages if t == m.status_topic][-1]
        self.assertEqual(report['current_dataset'], 'pool/Docker -> archive/Docker')
        self.assertEqual(report['completed_datasets'], 1)
        self.assertEqual(report['failed_datasets'], 0)
        self.assertEqual(report['data_transferred_bytes'], 5000)
        m.finish('success', 0, summary=summary)
        final = [x for x in client.messages if x[0] == m.last_result_topic][-1]
        self.assertEqual(final[1]['status'], 'success')
        self.assertTrue(final[3]); self.assertEqual(final[2], 1)
        self.assertFalse([x for x in client.messages if x[0] == m.status_topic and x[3]])
        events = [p for t,p,q,r in client.messages if t == m.events_topic]
        self.assertEqual([evt['event'] for evt in events], ['completed'])
        m.finish('failed', 2, error='should not publish twice', summary=summary)
        self.assertEqual(len([x for x in client.messages if x[0] == m.last_result_topic]), 1)
        m.stop()

    def test_failure_retains_result_and_does_not_claim_unattempted_are_failed(self):
        m, client = self.make_connected(live_notify_failure=True)
        summary = ReplicationSummary(total_datasets=5, attempted_datasets=2, completed_datasets=1)
        m.finish('failed', 12, error='out of space', summary=summary)
        result = [x[1] for x in client.messages if x[0] == m.last_result_topic][-1]
        self.assertEqual((result['total_datasets'], result['completed_datasets'], result['failed_datasets']), (5,1,1))
        self.assertEqual(result['error'], 'out of space')
        events = [x[1] for x in client.messages if x[0] == m.events_topic]
        self.assertEqual(events[0]['event'], 'failed')
        self.assertEqual(events[0]['exit_code'], 12)
        m.stop()

    def test_opt_out_discovery_and_events(self):
        m, client = self.make_connected(live_mqtt_discovery=False, live_notify_start=False,
                                         live_notify_success=False, live_notify_failure=False)
        self.assertEqual(discovery_messages(m), [])
        m.finish('failed', 14, error='cannot acquire lock')
        self.assertFalse([x for x in client.messages if x[0] == m.events_topic])
        self.assertTrue([x for x in client.messages if x[0] == m.last_result_topic])
        m.stop()

    def test_unavailable_broker_is_best_effort_even_if_start_fails(self):
        m = LiveBackupMonitor(make_config(live_mqtt_enabled=True), make_logger('unavailable'))
        with mock.patch.dict('sys.modules', {'paho': None}):
            m.start()  # optional dependency missing; no exception
        summary = ReplicationSummary(total_datasets=1)
        m.progress('started', DatasetPair('pool/a', 'backup/a', ()), summary)
        t0 = time.monotonic()
        m.finish('success', 0, summary=summary)
        self.assertLess(time.monotonic() - t0, 2.5)
        m.stop()

    def test_background_paho_client_start_publishes_discovery_then_live_state(self):
        from types import ModuleType, SimpleNamespace
        clients = []
        class ConnectedClient(FakeClient):
            def __init__(self, **kwargs):
                super().__init__()
                self.kwargs = kwargs
                clients.append(self)
            def username_pw_set(self, username, password):
                self.credentials = (username, password)
            def reconnect_delay_set(self, **kwargs):
                self.reconnect_delays = kwargs
            def connect_async(self, host, port, keepalive):
                self.connection = (host, port, keepalive)
            def loop_start(self):
                self.on_connect(self, None, None, 0, None)
        pkg = ModuleType('paho'); mqtt = ModuleType('paho.mqtt')
        client_module = ModuleType('paho.mqtt.client')
        client_module.Client = ConnectedClient
        client_module.CallbackAPIVersion = SimpleNamespace(VERSION2='v2')
        mqtt.client = client_module; pkg.mqtt = mqtt
        cfg = make_config(config_path='/tmp/nas.toml', live_mqtt_enabled=True,
                          broker_address='mqtt.example', mqtt_username='user', mqtt_password='pw',
                          live_notify_start=True)
        m = LiveBackupMonitor(cfg, make_logger('live-paho-start'))
        with mock.patch.dict('sys.modules', {'paho':pkg, 'paho.mqtt':mqtt, 'paho.mqtt.client':client_module}):
            m.start()
        self.assertEqual(len(clients), 1)
        c = clients[0]
        self.assertEqual(c.connection, ('mqtt.example', 1883, 30))
        self.assertEqual(c.credentials, ('user', 'pw'))
        self.assertEqual(c.kwargs['callback_api_version'], 'v2')
        self.assertTrue(m._heartbeat_thread.is_alive())
        self.assertEqual(len([x for x in c.messages if x[0].endswith('/config')]), 13)
        self.assertEqual([x[1]['event'] for x in c.messages if x[0] == m.events_topic], ['started'])
        m.finish('success', 0)
        m.stop()
        self.assertTrue(c.disconnected)

    def test_duplicate_event_never_writes_live_or_last_result(self):
        published = []
        def fake_single(topic, **kw):
            published.append((topic, kw))
        from types import ModuleType
        pkg = ModuleType('paho'); mqtt = ModuleType('paho.mqtt'); publish = ModuleType('paho.mqtt.publish')
        publish.single = fake_single
        mqtt.publish = publish; pkg.mqtt = mqtt
        with mock.patch.dict('sys.modules', {'paho':pkg, 'paho.mqtt':mqtt, 'paho.mqtt.publish':publish}):
            publish_duplicate_event(make_config(live_mqtt_enabled=True),
                                    make_logger('duplicate'), reason='Already running', exit_code=13)
        self.assertEqual(len(published), 1)
        self.assertTrue(published[0][0].endswith('/events'))
        self.assertFalse(published[0][1]['retain'])
        self.assertEqual(json.loads(published[0][1]['payload'])['event'], 'duplicate_rejected')

    def test_broker_credentials_required_for_live_only_and_option_validation(self):
        from tests.test_config import BASE
        text = BASE.replace('[mqtt]', '[mqtt]\nLiveMQTTEnabled = true\nLiveHeartbeatSeconds = 60')
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'config.toml'
            path.write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'broker_address'):
                load_app_config(str(path))
            path.write_text(text.replace('broker_address = ""', 'broker_address = "127.0.0.1"'), encoding='utf-8')
            cfg = load_app_config(str(path))
            self.assertTrue(cfg.live_mqtt_enabled)
            self.assertFalse(cfg.use_mqtt)
            self.assertTrue(cfg.live_mqtt_discovery)
            path.write_text(text.replace('LiveHeartbeatSeconds = 60', 'LiveHeartbeatSeconds = 0').replace('broker_address = ""', 'broker_address = "127.0.0.1"'), encoding='utf-8')
            with self.assertRaises((ValueError,)): load_app_config(str(path))


if __name__ == '__main__':
    unittest.main()
