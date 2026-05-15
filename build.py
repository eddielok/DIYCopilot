"""Build DIY Copilot into a native application.

  macOS    ->  dist/DIY Copilot.app
  Windows  ->  dist/DIY Copilot/DIY Copilot.exe
  Linux    ->  dist/DIY Copilot/DIY Copilot

Usage:
    source .venv/bin/activate          (Windows: .venv\\Scripts\\Activate.ps1)
    pip install -r requirements-build.txt
    python build.py

Notes:
  * Run this on the OS you want to build for — PyInstaller does not
    cross-compile. Build the .app on a Mac, the .exe on Windows.
  * If ~/.diycopilot/models/ggml-base.en.bin exists, it gets bundled into the
    app so it's fully self-contained. Otherwise run `python download_model.py`
    first, or the packaged app will ask the user to download it.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SPEC = ROOT / "DIYCopilot.spec"


def main() -> int:
    if not SPEC.exists():
        print(f"Spec file not found: {SPEC}")
        return 1

    # Prefer running PyInstaller as a module so it uses the active venv.
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed in this environment.\n")
        print("Install the build dependency first:")
        print("    pip install -r requirements-build.txt\n")
        return 1

    # Friendly heads-up about the Whisper model.
    model_dir = Path.home() / ".diycopilot" / "models"
    models = sorted(model_dir.glob("ggml-*.bin")) if model_dir.is_dir() else []
    if models:
        print(f"Bundling Whisper model(s): {', '.join(m.name for m in models)}")
    else:
        print("No Whisper model found in ~/.diycopilot/models/.")
        print("The app will still build, but on first run it will ask the user")
        print("to download one. To bundle it now, Ctrl+C and run:")
        print("    python download_model.py base.en\n")

    print("Running PyInstaller…\n")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("\nBuild failed — see the PyInstaller output above.")
        return result.returncode

    dist = ROOT / "dist"
    print("\n" + "=" * 56)
    if sys.platform == "darwin":
        app = dist / "DIY Copilot.app"
        print(f"✓ Built: {app}")
        print("  • Drag it into /Applications.")
        print("  • First launch: right-click → Open (it's unsigned, so")
        print("    Gatekeeper warns once; after that it opens normally).")
        print("  • macOS will ask for Microphone permission on first listen.")
    elif sys.platform.startswith("win"):
        exe = dist / "DIY Copilot" / "DIY Copilot.exe"
        print(f"✓ Built: {exe}")
        print("  • The whole 'DIY Copilot' folder is the app — zip and share")
        print("    it, or make a shortcut to the .exe.")
        print("  • Windows SmartScreen may warn once (unsigned build).")
    else:
        print(f"✓ Built: {dist / 'DIY Copilot'}")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
