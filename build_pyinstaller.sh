#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
EXPECTED_VERSION="0.4.29"

"$PYTHON_BIN" - <<'PY'
missing = []
for module_name in ("PyInstaller", "pexpect", "paho.mqtt"):
    try:
        __import__(module_name)
    except ImportError:
        missing.append(module_name)
if missing:
    raise SystemExit(
        "Missing PyInstaller build dependencies: "
        + ", ".join(missing)
        + ". Install requirements-build.txt first."
    )
PY

rm -rf -- build dist

"$PYTHON_BIN" -m PyInstaller --clean --noconfirm Syncerate.spec

EXECUTABLE="$PROJECT_ROOT/dist/Syncerate"
if [[ ! -f "$EXECUTABLE" ]]; then
    echo "PyInstaller did not create $EXECUTABLE" >&2
    exit 1
fi
if [[ ! -x "$EXECUTABLE" ]]; then
    echo "PyInstaller output is not executable: $EXECUTABLE" >&2
    exit 1
fi

VERSION_OUTPUT="$($EXECUTABLE --version)"
if [[ "$VERSION_OUTPUT" != "Syncerate.py $EXPECTED_VERSION" ]]; then
    echo "Unexpected standalone version output: $VERSION_OUTPUT" >&2
    exit 1
fi

"$EXECUTABLE" --help >/dev/null

printf 'Built and verified: %s\n' "$EXECUTABLE"
