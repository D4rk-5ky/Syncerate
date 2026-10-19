# Syncerate standalone build

- `dist/` is where the PyInstaller build puts the standalone executable.
- The expected output is `dist/Syncerate`.
- You create it by running `./build-pyinstaller.sh`.
- Generated binaries should not be confused with the source files.

**Source archive warning:** the bundled `dist/Syncerate` is a preserved older binary that reports version `0.4.29`, **not** version `0.4.50`. Do not treat it as the current application. Run `python3 Syncerate.py` from the source tree, or rebuild the executable with `./build-pyinstaller.sh` before running it. The build script will overwrite this README with the ordinary standalone-delivery instructions after a successful build.
