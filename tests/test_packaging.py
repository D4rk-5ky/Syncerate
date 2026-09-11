from pathlib import Path
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
        script_path = PROJECT_ROOT / "build_pyinstaller.sh"
        script = script_path.read_text(encoding="utf-8")
        self.assertTrue(script_path.stat().st_mode & 0o111)
        self.assertIn("set -euo pipefail", script)
        self.assertIn("rm -rf -- build dist", script)
        self.assertIn('PYTHON_BIN="${PYTHON_BIN:-python3}"', script)
        self.assertIn('"$PYTHON_BIN" -m PyInstaller --clean --noconfirm Syncerate.spec', script)
        self.assertIn('EXPECTED_VERSION="0.4.27"', script)
        self.assertIn('"$EXECUTABLE" --help', script)


if __name__ == "__main__":
    unittest.main()
