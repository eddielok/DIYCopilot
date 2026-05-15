"""macOS-native window tweaks for the overlay.

Qt alone can keep a window "on top", but on macOS that still isn't enough to:
  - stay visible when you switch to another app, and
  - appear over a *fullscreen* app (Zoom/Teams in fullscreen during a call).

Both need the underlying NSWindow's collectionBehavior + window level set,
which Qt doesn't expose. We do it with pyobjc. If pyobjc isn't installed (or
we're not on macOS), every function here is a graceful no-op.
"""
from __future__ import annotations

import sys


def is_macos() -> bool:
    return sys.platform == "darwin"


def make_overlay_persistent(widget) -> bool:
    """Make `widget`'s native window float over everything, on every Space.

    Returns True if the native tweaks were applied, False if skipped
    (not macOS, pyobjc missing, or the NSWindow wasn't ready yet).
    """
    if not is_macos():
        return False
    try:
        import objc
        from AppKit import (
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorStationary,
        )

        # widget.winId() returns a pointer to the NSView backing the widget.
        view = objc.objc_object(c_void_p=int(widget.winId()))
        nswindow = view.window()
        if nswindow is None:
            return False

        # Show on all Spaces, ride along with fullscreen apps, don't move
        # when Spaces change.
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        nswindow.setCollectionBehavior_(behavior)

        # Float above normal windows — and above fullscreen apps.
        # NSStatusWindowLevel == 25; high enough to clear fullscreen video apps.
        nswindow.setLevel_(25)
        return True
    except ImportError:
        sys.stderr.write(
            "[macos] pyobjc not installed — the overlay will stay on top of "
            "normal windows, but may not appear over fullscreen apps.\n"
            "        To enable that: pip install pyobjc-framework-Cocoa\n"
        )
        return False
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"[macos] could not apply native window tweaks: {exc}\n")
        return False
