"""DIY Interview Copilot — entry point."""
from __future__ import annotations

import os
import sys

if sys.version_info < (3, 10):
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    sys.stderr.write(
        f"\nDIY Copilot needs Python 3.10 or newer "
        f"(you are on {sys.version.split()[0]}).\n"
        "Some dependencies (pywhispercpp) use 3.10+ syntax.\n\n"
        "Fix:\n"
        "  brew install python@3.12\n"
        f'  cd "{_app_dir}"\n'
        "  rm -rf .venv && python3.12 -m venv .venv\n"
        "  source .venv/bin/activate && pip install -r requirements.txt\n\n"
    )
    sys.exit(1)

import _sslfix  # noqa: F401  -- must be imported before any HTTPS call

from PyQt6.QtWidgets import QApplication

from overlay import OverlayWindow
from settings import Settings


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DIY Copilot")
    settings = Settings.load()
    window = OverlayWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
