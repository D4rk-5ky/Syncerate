#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
EXPECTED_VERSION="0.4.54"
BUILD_ROOT="$PROJECT_ROOT/.build"
WORK_DIR="$BUILD_ROOT/pyinstaller-work"
STAGING_DIST="$BUILD_ROOT/pyinstaller-dist"
FINAL_DIST="$PROJECT_ROOT/dist"
EXECUTABLE="$FINAL_DIST/Syncerate"
DIST_README="$FINAL_DIST/README.md"
STAGED_EXECUTABLE="$STAGING_DIST/Syncerate"

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

cleanup_generated_build_dirs() {
    rm -rf -- "$BUILD_ROOT"
}
trap cleanup_generated_build_dirs EXIT

# Generated PyInstaller work/staging belongs under .build/, never in dist/.
# dist/ is a delivery directory and is recreated from scratch for each build.
rm -rf -- "$BUILD_ROOT" "$FINAL_DIST"
mkdir -p -- "$WORK_DIR" "$STAGING_DIST" "$FINAL_DIST"

if find "$FINAL_DIST" -mindepth 1 -print -quit | grep -q .; then
    echo "Final dist directory is not empty before the build: $FINAL_DIST" >&2
    exit 1
fi

"$PYTHON_BIN" -m PyInstaller \
    --clean \
    --noconfirm \
    --workpath "$WORK_DIR" \
    --distpath "$STAGING_DIST" \
    Syncerate.spec

if [[ ! -f "$STAGED_EXECUTABLE" || -L "$STAGED_EXECUTABLE" ]]; then
    echo "PyInstaller did not create the expected regular executable: $STAGED_EXECUTABLE" >&2
    exit 1
fi
if [[ ! -x "$STAGED_EXECUTABLE" ]]; then
    echo "PyInstaller output is not executable: $STAGED_EXECUTABLE" >&2
    exit 1
fi

# Publish only the verified executable plus the explanatory README.
install -m 0755 -- "$STAGED_EXECUTABLE" "$EXECUTABLE"
cat > "$DIST_README" <<'README'
# Syncerate standalone build

- `dist/` is where the PyInstaller build puts the standalone executable.
- The expected output is `dist/Syncerate`.
- You create it by running `./build-pyinstaller.sh`.
- Generated binaries should not be confused with the source files.
README
chmod 0644 "$DIST_README"

mapfile -d '' -t DIST_ENTRIES < <(find "$FINAL_DIST" -mindepth 1 -maxdepth 1 -print0 | sort -z)
EXPECTED_README="$DIST_README"
if (( ${#DIST_ENTRIES[@]} != 2 )); then
    echo "Final dist directory must contain exactly two entries: $EXECUTABLE and $EXPECTED_README" >&2
    printf 'Found: %q\n' "${DIST_ENTRIES[@]}" >&2
    exit 1
fi

FOUND_EXECUTABLE=false
FOUND_README=false
for entry in "${DIST_ENTRIES[@]}"; do
    case "$entry" in
        "$EXECUTABLE") FOUND_EXECUTABLE=true ;;
        "$EXPECTED_README") FOUND_README=true ;;
        *)
            echo "Unexpected final dist entry: $entry" >&2
            exit 1
            ;;
    esac
done
if [[ "$FOUND_EXECUTABLE" != true || "$FOUND_README" != true ]]; then
    echo "Final dist directory is missing Syncerate or README.md" >&2
    exit 1
fi
if [[ ! -f "$EXECUTABLE" || -L "$EXECUTABLE" || ! -x "$EXECUTABLE" ]]; then
    echo "Final Syncerate output is not one regular executable: $EXECUTABLE" >&2
    exit 1
fi
if [[ ! -f "$DIST_README" || -L "$DIST_README" ]]; then
    echo "Final dist README is not one regular file: $DIST_README" >&2
    exit 1
fi

VERSION_OUTPUT="$($EXECUTABLE --version)"
EXPECTED_VERSION_OUTPUT="$(basename "$EXECUTABLE") $EXPECTED_VERSION"
if [[ "$VERSION_OUTPUT" != "$EXPECTED_VERSION_OUTPUT" ]]; then
    echo "Unexpected standalone version output: $VERSION_OUTPUT" >&2
    echo "Expected: $EXPECTED_VERSION_OUTPUT" >&2
    exit 1
fi

"$EXECUTABLE" --help >/dev/null

printf 'Built and verified: %s\n' "$EXECUTABLE"
printf 'Final dist contains exactly two files: %s and %s\n' "$EXECUTABLE" "$DIST_README"
