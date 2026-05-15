"""Per-platform window configuration.

A frameless always-on-top overlay needs slightly different handling on each OS:

  * macOS  — must NOT use the Qt.Tool flag (it auto-hides the window whenever
             the app loses focus). Instead we apply NSWindow collection
             behavior so it floats over Spaces and fullscreen apps.
  * Windows — the Qt.Tool flag is fine and even useful: it keeps the window
             off the taskbar without auto-hiding. WindowStaysOnTopHint does
             the always-on-top part.
  * Linux  — a plain frameless always-on-top window; behavior varies by WM.

The user can force a specific platform's config from Settings, or leave it on
"auto" to detect from the running OS.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowConfig:
    key: str
    label: str
    # Qt.Tool: auto-hides on macOS (bad), hides from taskbar on Windows (good).
    use_tool_flag: bool
    # Apply pyobjc NSWindow tweaks (only meaningful on macOS).
    use_macos_native: bool
    notes: str


WINDOW_CONFIGS: dict[str, WindowConfig] = {
    "macos": WindowConfig(
        key="macos",
        label="macOS",
        use_tool_flag=False,
        use_macos_native=True,
        notes="No Tool flag (it auto-hides on macOS). Uses native NSWindow "
              "tweaks to float over Spaces and fullscreen apps.",
    ),
    "windows": WindowConfig(
        key="windows",
        label="Windows",
        use_tool_flag=True,
        use_macos_native=False,
        notes="Tool flag keeps the overlay off the taskbar without "
              "auto-hiding. Always-on-top is handled by Qt.",
    ),
    "linux": WindowConfig(
        key="linux",
        label="Linux",
        use_tool_flag=False,
        use_macos_native=False,
        notes="Plain frameless always-on-top window. Exact behavior depends "
              "on your window manager.",
    ),
}

# Modes the user can choose in Settings.
PLATFORM_MODES = [
    ("auto", "Auto-detect"),
    ("macos", "macOS"),
    ("windows", "Windows"),
    ("linux", "Linux"),
]


def detect_platform() -> str:
    """Return the OS key for the machine we're actually running on."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def resolve_platform(mode: str) -> str:
    """Turn a platform_mode ('auto' | 'macos' | 'windows' | 'linux') into a real OS key."""
    if mode in WINDOW_CONFIGS:
        return mode
    return detect_platform()


def get_window_config(mode: str) -> WindowConfig:
    """Return the WindowConfig to use for the given platform_mode."""
    return WINDOW_CONFIGS[resolve_platform(mode)]
