"""Optional final MQTT reports matching the supplied Home Assistant JSON contract."""
import datetime
import importlib
import json
import logging
from pathlib import Path
import ssl
import subprocess
import sys
import uuid


DEFAULTS = {
    'port': 1883,
    'title': 'SnapBeforeWatchTower',
    'username': None,
    'password': None,
    'qos': 0,
    'tls': False,
    'ca_file': None,
    'cert_file': None,
    'key_file': None,
    'timeout': 15,
}
SUPPORTED_KEYS = set(DEFAULTS) | {'host', 'topic'}
OPTIONAL_STRING_KEYS = ['username', 'password', 'ca_file', 'cert_file', 'key_file']


def validate_config(supplied, base_dir, dry_run=False, enabled=True):
    """Validate the TOML [mqtt] settings; disabled MQTT needs no dependency or broker details."""
    if not isinstance(supplied, dict):
        raise ValueError('MQTT configuration must be a TOML table')
    unsupported = set(supplied) - SUPPORTED_KEYS
    if unsupported:
        names = ', '.join(sorted(unsupported))
        raise ValueError(f'MQTT configuration contains unsupported key(s): {names}')
    if not enabled:
        return None

    config = dict(DEFAULTS, **supplied)
    for key in ['host', 'topic', 'title']:
        if not isinstance(config.get(key), str) or not config[key].strip() or '\0' in config[key]:
            raise ValueError(f'MQTT {key} must be a nonempty string without NUL')
        config[key] = config[key].strip()

    if any(char in config['topic'] for char in '+#') or len(config['topic'].encode('utf-8')) > 65535:
        raise ValueError('MQTT topic must be a publish topic without wildcards, at most 65535 UTF-8 bytes')

    for key, low, high in [('port', 1, 65535), ('qos', 0, 2), ('timeout', 1, 120)]:
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f'MQTT {key} must be an integer from {low} to {high}')
    if type(config['tls']) is not bool:
        raise ValueError('MQTT tls must be true or false')
    if config['tls'] and 'port' not in supplied:
        config['port'] = 8883

    for key in OPTIONAL_STRING_KEYS:
        value = config[key]
        if value == '':
            config[key] = None
            continue
        if value is not None and (not isinstance(value, str) or not value.strip() or '\0' in value):
            raise ValueError(f'MQTT {key} must be an empty string or a nonempty string without NUL')
        if isinstance(config[key], str):
            config[key] = config[key].strip()

    if config['password'] and not config['username']:
        raise ValueError('MQTT password requires username')
    if bool(config['cert_file']) != bool(config['key_file']):
        raise ValueError('MQTT cert_file and key_file must be supplied together')

    base_dir = Path(base_dir).resolve()
    for key in ['ca_file', 'cert_file', 'key_file']:
        if config[key]:
            if not config['tls']:
                raise ValueError(f'MQTT {key} requires tls=true')
            resolved = (base_dir / config[key]).resolve()
            if not resolved.is_file():
                raise ValueError(f'MQTT {key} does not point to a file')
            config[key] = str(resolved)

    if not dry_run:
        try:
            importlib.import_module('paho.mqtt.publish')
        except ImportError as exc:
            raise ValueError('MQTT requires paho-mqtt: install requirements-mqtt.txt with this Python interpreter') from exc
    return config


class ErrorCapture(logging.Handler):
    """Keep bounded, current-run error details without rereading potentially stale logs."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.text = ''

    def emit(self, record):
        message = record.getMessage().strip()
        if message and message.strip('- \n\r\t'):
            self.text = (self.text + '\n' + message).strip()[-4096:]


def build_payload(config, command, version, exc, errors, run_id):
    """Describe the actual process outcome, retaining nonfatal errors as warnings."""
    code = 0
    if isinstance(exc, SystemExit):
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    elif isinstance(exc, KeyboardInterrupt):
        code = 130
    elif exc is not None:
        code = 1
    failure = code != 0
    detail = errors
    command_stderr = getattr(exc, 'stderr', '') if exc else ''
    if isinstance(command_stderr, bytes):
        command_stderr = command_stderr.decode('utf-8', errors='replace')
    if command_stderr:
        detail = (detail + '\n' + command_stderr).strip()[-4096:]
    error = ''
    if failure:
        error = (errors or f'Process exited with code {code}') if isinstance(exc, SystemExit) else (str(exc) or type(exc).__name__)
    return {
        'status': 'failure' if failure else 'success',
        'title': config['title'],
        'name': config['title'],
        'job': config['title'],
        'exit_code': code,
        'warning': bool(errors) and not failure,
        'error': error[-4096:],
        'stderr': detail,
        'command': command,
        'version': version,
        'run_id': run_id,
        'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def publish_report(config, payload):
    """Use a killable worker to bound DNS/connect/publish time; keep credentials off argv."""
    result = subprocess.run(
        [sys.executable, '-B', str(Path(__file__).resolve()), '--publish'],
        input=json.dumps({'config': config, 'payload': payload}),
        text=True, capture_output=True, timeout=config['timeout'],
    )
    if result.returncode != 0:
        # Worker/library output could contain broker details; do not copy it to logs.
        raise RuntimeError('MQTT publish failed; check broker, authentication, TLS, and topic permissions')


class RunReporter:
    """Publish one final outcome without changing existing operations or exit behavior."""

    def __init__(self, config, command, version, dry_run=False):
        self.config = config
        self.command = command
        self.version = version
        self.dry_run = dry_run
        self.run_id = str(uuid.uuid4())
        self.errors = ErrorCapture()
        self.error_logger = None

    def __enter__(self):
        return self

    def attach(self, error_logger):
        self.error_logger = error_logger
        error_logger.addHandler(self.errors)

    def __exit__(self, exc_type, exc, traceback):
        if self.error_logger is not None:
            self.error_logger.removeHandler(self.errors)
        if not self.config:
            return False
        logger = logging.getLogger('SnapBeforeWatchTower')
        if self.dry_run:
            logger.info('[DRY-RUN] MQTT final report suppressed')
            return False
        try:
            payload = build_payload(self.config, self.command, self.version, exc, self.errors.text, self.run_id)
            publish_report(self.config, payload)
            logger.info('MQTT final %s report published', payload['status'])
        except subprocess.TimeoutExpired:
            logger.error('MQTT report timed out; delivery is unconfirmed')
        except Exception:
            logger.error('MQTT report failed; check broker, authentication, TLS, dependency, and topic permissions')
        return False


def worker():
    """Publish non-retained JSON with Paho; parent enforces the complete time budget."""
    from paho.mqtt import publish

    request = json.load(sys.stdin)
    config = request['config']
    auth = None
    if config['username']:
        auth = {'username': config['username']}
        if config['password']:
            auth['password'] = config['password']
    context = None
    if config['tls']:
        context = ssl.create_default_context(cafile=config['ca_file'])
        if config['cert_file']:
            context.load_cert_chain(config['cert_file'], config['key_file'])
    publish.single(
        config['topic'], payload=json.dumps(request['payload'], ensure_ascii=True),
        hostname=config['host'], port=config['port'], qos=config['qos'], retain=False,
        auth=auth, tls=context,
    )


if __name__ == '__main__':
    if sys.argv[1:] != ['--publish']:
        sys.exit('Internal MQTT worker; use SnapBeforeWatchTower.py -c CONFIG')
    try:
        worker()
    except Exception:
        sys.exit(1)
