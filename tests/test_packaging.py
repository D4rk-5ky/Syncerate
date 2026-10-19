from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    """Protect the reproducible standalone PyInstaller build definition."""

    def test_spec_builds_onefile_syncerate_and_collects_runtime_packages(self):
        spec = (PROJECT_ROOT / "Syncerate.spec").read_text(encoding="utf-8")
        self.assertIn('collect_submodules("pexpect")', spec)
        self.assertIn('collect_submodules("paho.mqtt")', spec)
        self.assertIn('name="Syncerate"', spec)
        self.assertIn("EXE(", spec)
        self.assertNotIn("COLLECT(", spec)

    def test_build_requirements_pin_packager_and_runtime_dependencies(self):
        requirements = (PROJECT_ROOT / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertIn("PyInstaller==6.22.2", requirements)
        self.assertIn("pyinstaller-hooks-contrib==2026.7", requirements)
        self.assertIn("pexpect==4.9.0", requirements)
        self.assertIn("paho-mqtt==2.1.0", requirements)

    def test_build_script_cleans_generated_output_and_verifies_executable(self):
        script_path = PROJECT_ROOT / "build-pyinstaller.sh"
        script = script_path.read_text(encoding="utf-8")
        self.assertTrue(script_path.stat().st_mode & 0o111)
        self.assertIn("set -euo pipefail", script)
        self.assertIn('rm -rf -- "$BUILD_ROOT" "$FINAL_DIST"', script)
        self.assertIn('PYTHON_BIN="${PYTHON_BIN:-python3}"', script)
        self.assertIn('"$PYTHON_BIN" -m PyInstaller', script)
        self.assertIn('EXPECTED_VERSION="0.4.50"', script)
        self.assertIn('EXPECTED_VERSION_OUTPUT="$(basename "$EXECUTABLE") $EXPECTED_VERSION"', script)
        self.assertIn('[[ "$VERSION_OUTPUT" != "$EXPECTED_VERSION_OUTPUT" ]]', script)
        self.assertIn('"$EXECUTABLE" --help', script)
        self.assertIn('BUILD_ROOT="$PROJECT_ROOT/.build"', script)
        self.assertIn('WORK_DIR="$BUILD_ROOT/pyinstaller-work"', script)
        self.assertIn('STAGING_DIST="$BUILD_ROOT/pyinstaller-dist"', script)
        self.assertIn('FINAL_DIST="$PROJECT_ROOT/dist"', script)
        self.assertIn('mkdir -p -- "$WORK_DIR" "$STAGING_DIST" "$FINAL_DIST"', script)
        self.assertIn('--distpath "$STAGING_DIST"', script)
        self.assertIn('install -m 0755 -- "$STAGED_EXECUTABLE" "$EXECUTABLE"', script)
        self.assertIn("mapfile -d '' -t DIST_ENTRIES", script)
        self.assertIn('${#DIST_ENTRIES[@]} != 2', script)
        self.assertIn('DIST_README="$FINAL_DIST/README.md"', script)
        self.assertIn('Final dist contains exactly two files', script)
        self.assertIn('!dist/README.md', (PROJECT_ROOT / '.gitignore').read_text(encoding='utf-8'))
        self.assertIn('.build/', (PROJECT_ROOT / '.gitignore').read_text(encoding='utf-8'))
        self.assertIn('trap cleanup_generated_build_dirs EXIT', script)


    def test_build_script_publishes_only_syncerate_and_readme_into_clean_dist(self):
        """Exercise the build wrapper with a fake PyInstaller frontend."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shutil.copy2(PROJECT_ROOT / "build-pyinstaller.sh", root / "build-pyinstaller.sh")
            shutil.copy2(PROJECT_ROOT / "Syncerate.spec", root / "Syncerate.spec")
            (root / "dist").mkdir()
            (root / "dist" / "old-file").write_text("stale", encoding="utf-8")

            fake_python = root / "fake-python"
            fake_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
    cat >/dev/null
    exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "PyInstaller" ]]; then
    shift 2
    distpath=""
    workpath=""
    while (( $# )); do
        case "$1" in
            --distpath) distpath="$2"; shift 2 ;;
            --workpath) workpath="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    mkdir -p -- "$distpath" "$workpath"
    cat > "$distpath/Syncerate" <<'INNER'
#!/usr/bin/env bash
case "${1:-}" in
    --version) echo "Syncerate 0.4.50" ;;
    --help) echo "help" ;;
    *) exit 0 ;;
esac
INNER
    chmod 0755 "$distpath/Syncerate"
    # Simulate unrelated PyInstaller output. The wrapper must not publish it.
    printf 'staging-only\n' > "$distpath/extra-file"
    exit 0
fi
exit 9
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = os.environ.copy()
            env["PYTHON_BIN"] = str(fake_python)
            result = subprocess.run(
                [str(root / "build-pyinstaller.sh")],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertEqual(sorted(p.name for p in (root / "dist").iterdir()), ["README.md", "Syncerate"])
            readme = (root / "dist" / "README.md").read_text(encoding="utf-8")
            self.assertIn("`dist/` is where the PyInstaller build puts the standalone executable.", readme)
            self.assertIn("The expected output is `dist/Syncerate`.", readme)
            self.assertIn("You create it by running `./build-pyinstaller.sh`.", readme)
            self.assertIn("Generated binaries should not be confused with the source files.", readme)
            self.assertTrue((root / "dist" / "Syncerate").stat().st_mode & 0o111)
            self.assertFalse((root / ".build").exists())


if __name__ == "__main__":
    unittest.main()
