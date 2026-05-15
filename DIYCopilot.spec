# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DIY Interview Copilot.

Builds:
  * macOS   -> dist/DIY Copilot.app   (with mic-permission Info.plist)
  * Windows -> dist/DIY Copilot/DIY Copilot.exe
  * Linux   -> dist/DIY Copilot/DIY Copilot

Run via:  python build.py     (recommended)
   or:    pyinstaller --noconfirm --clean DIYCopilot.spec

It uses onedir (a folder), not onefile — pywhispercpp/sounddevice ship native
libraries that are far more reliable unpacked than from a onefile bundle.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

APP_NAME = "DIY Copilot"

# --- collect native deps (pywhispercpp + sounddevice ship binaries) ---
datas, binaries, hiddenimports = [], [], []
for pkg in ("pywhispercpp", "sounddevice"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Modules imported lazily / inside try-except — make sure they're included.
hiddenimports += ["truststore"]
if sys.platform == "darwin":
    hiddenimports += ["objc", "AppKit", "Foundation"]

# --- bundle the Whisper model if it's already downloaded ---
# (~/.diycopilot/models/ggml-*.bin). If present, the built app is fully
# self-contained; if not, the app still works and tells the user to run
# download_model.py.
user_models = Path.home() / ".diycopilot" / "models"
if user_models.is_dir():
    for f in sorted(user_models.glob("ggml-*.bin")):
        datas.append((str(f), "models"))

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — no terminal window
    disable_windowed_traceback=False,
    target_arch=None,       # build for the architecture you run this on
    # icon="icon.icns"/"icon.ico"  # add an icon file here if you make one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=None,  # set to "icon.icns" if you add one
        bundle_identifier="com.diycopilot.app",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            # macOS will silently deny mic access without this string:
            "NSMicrophoneUsageDescription":
                "DIY Copilot listens to interview audio to transcribe "
                "questions locally on your Mac.",
        },
    )
