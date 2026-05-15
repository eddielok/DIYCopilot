"""Always-on-top, frameless, draggable overlay window."""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

# The folder this app lives in — used so user-facing instructions point at the
# real location instead of a hardcoded path.
APP_DIR = Path(__file__).resolve().parent

import numpy as np
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QCursor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from _macos import make_overlay_persistent
from audio import AudioCapture, list_input_devices
from llm import build_messages, stream_completion
from platform_config import get_window_config
from settings import Settings, SettingsDialog
from transcriber import Transcriber


INTERROGATIVE_CUES = re.compile(
    r"\b(what|why|how|when|where|who|which|tell me|describe|walk me|can you|"
    r"could you|would you|should|do you|have you|are you|explain|share|"
    r"give me|talk about)\b",
    re.IGNORECASE,
)


def looks_like_question(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.endswith("?"):
        return True
    return bool(INTERROGATIVE_CUES.search(t))


class Bridge(QObject):
    """Marshals worker-thread events onto the GUI thread."""

    transcript_appended = pyqtSignal(str)
    answer_started = pyqtSignal()
    answer_delta = pyqtSignal(str)
    answer_done = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)


class OverlayWindow(QWidget):
    HEADER_HEIGHT = 32

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.bridge = Bridge()
        self._drag_offset: Optional[QPoint] = None
        self._capture: Optional[AudioCapture] = None
        self._transcriber = Transcriber(model_name=settings.whisper_model)
        self._llm_stop = threading.Event()
        self._listening = False

        self._build_ui()
        self._wire_bridge()

        # Window flags are platform-dependent — see platform_config.py.
        # On macOS we must NOT use Qt.Tool (it auto-hides the window when the
        # app loses focus); on Windows the Tool flag is useful. The exact
        # config is chosen by the "Platform" setting (default: auto-detect).
        self._native_applied = False
        self._win_cfg = get_window_config(getattr(settings, "platform_mode", "auto"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(440, 480)
        self._place_top_right()
        self._apply_window_prefs()

        # In-app shortcut to toggle listening (cmd+shift+space)
        QShortcut(QKeySequence("Ctrl+Shift+Space"), self, activated=self.toggle_listening)
        QShortcut(QKeySequence("Meta+Shift+Space"), self, activated=self.toggle_listening)
        self.space_shortcut = QShortcut(QKeySequence("Space"), self, activated=self.toggle_listening)
        self.space_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.space_shortcut.setAutoRepeat(False)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (drag handle)
        header = QWidget(self)
        header.setFixedHeight(self.HEADER_HEIGHT)
        header.setObjectName("header")
        header.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(10, 0, 6, 0)
        hlay.setSpacing(8)

        title = QLabel("DIY Copilot")
        title.setObjectName("title")
        hlay.addWidget(title)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("dot_idle")
        hlay.addWidget(self.status_dot)

        self.status_label = QLabel("idle")
        self.status_label.setObjectName("status")
        hlay.addWidget(self.status_label)

        hlay.addStretch(1)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("iconbtn")
        self.settings_btn.setFixedWidth(28)
        self.settings_btn.clicked.connect(self.open_settings)
        hlay.addWidget(self.settings_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("iconbtn")
        self.close_btn.setFixedWidth(28)
        self.close_btn.setToolTip("Quit DIY Copilot")
        self.close_btn.clicked.connect(self.quit_app)
        hlay.addWidget(self.close_btn)

        # Body
        body = QWidget(self)
        body.setObjectName("body")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(12, 10, 12, 12)
        blay.setSpacing(8)

        # Source row
        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        src_row.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self._refresh_devices()
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        src_row.addWidget(self.source_combo, 1)
        self.listen_btn = QPushButton("Listen")
        self.listen_btn.setCheckable(True)
        self.listen_btn.setObjectName("listen")
        self.listen_btn.clicked.connect(self.toggle_listening)
        src_row.addWidget(self.listen_btn)
        blay.addLayout(src_row)

        # Question label
        q_label = QLabel("Question")
        q_label.setObjectName("section")
        blay.addWidget(q_label)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("transcript")
        self.transcript.setFixedHeight(80)
        blay.addWidget(self.transcript)

        # Answer label
        a_label = QLabel("Answer")
        a_label.setObjectName("section")
        blay.addWidget(a_label)
        self.answer = QTextEdit()
        self.answer.setReadOnly(False)  # let user copy/edit
        self.answer.setObjectName("answer")
        blay.addWidget(self.answer, 1)

        # Footer row — clear + quit
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("ghostbtn")
        self.clear_btn.clicked.connect(self._clear_panes)
        footer.addWidget(self.clear_btn)
        footer.addStretch(1)
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("quit")
        self.quit_btn.clicked.connect(self.quit_app)
        footer.addWidget(self.quit_btn)
        blay.addLayout(footer)

        root.addWidget(header)
        root.addWidget(body, 1)

        self.setStyleSheet(
            """
            #header {
                background: rgba(22, 24, 30, 235);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            #body {
                background: rgba(22, 24, 30, 225);
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QLabel { color: #e6e6e6; font-size: 12px; }
            #title { font-weight: 600; }
            #section { color: #9aa0a6; font-size: 11px; text-transform: uppercase;
                       letter-spacing: 0.6px; margin-top: 2px; }
            #dot_idle { color: #5f6368; font-size: 14px; }
            #dot_listening { color: #34d399; font-size: 14px; }
            #dot_thinking { color: #fbbf24; font-size: 14px; }
            #dot_error { color: #f87171; font-size: 14px; }
            QTextEdit#transcript, QTextEdit#answer {
                background: rgba(255,255,255,0.04);
                color: #f3f4f6;
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 8px;
                font-size: 13px;
                padding: 8px;
            }
            QTextEdit#answer { font-size: 13.5px; line-height: 1.45; }
            QComboBox {
                background: #2b2f3a;
                color: #f3f4f6;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                padding: 4px 8px;
                min-height: 22px;
            }
            QComboBox:hover { border: 1px solid rgba(255,255,255,0.25); }
            QComboBox QAbstractItemView {
                background: #20242e;
                color: #f3f4f6;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 4px;
                outline: none;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QComboBox QAbstractItemView::item {
                color: #f3f4f6;
                background: transparent;
                padding: 5px 8px;
                min-height: 20px;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #2563eb;
                color: #ffffff;
            }
            QPushButton#listen {
                background: #2563eb; color: white; border: none;
                border-radius: 6px; padding: 5px 14px; font-weight: 600;
            }
            QPushButton#listen:checked { background: #dc2626; }
            QPushButton#iconbtn {
                background: transparent; color: #d1d5db; border: none;
                font-size: 14px;
            }
            QPushButton#iconbtn:hover { color: white; }
            QPushButton#quit {
                background: rgba(220,38,38,0.18); color: #fca5a5;
                border: 1px solid rgba(220,38,38,0.45);
                border-radius: 6px; padding: 4px 16px; font-weight: 600;
            }
            QPushButton#quit:hover { background: #dc2626; color: white; }
            QPushButton#ghostbtn {
                background: transparent; color: #9aa0a6;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px; padding: 4px 12px;
            }
            QPushButton#ghostbtn:hover { color: #f3f4f6; border-color: rgba(255,255,255,0.3); }
            """
        )

    def _refresh_devices(self) -> None:
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem("(default input)")
        for name in list_input_devices():
            self.source_combo.addItem(name)
        if self.settings.audio_device:
            idx = self.source_combo.findText(self.settings.audio_device)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        self.source_combo.blockSignals(False)

    def _place_top_right(self) -> None:
        screen = self.screen()
        geo = screen.availableGeometry() if screen else None
        if geo is None:
            return
        x = geo.right() - self.width() - 24
        y = geo.top() + 24
        self.move(x, y)

    # ---------- window preferences ----------
    def _apply_window_prefs(self) -> None:
        """Apply platform window config + always-on-top + opacity from settings."""
        # Re-resolve the platform config in case the Platform setting changed.
        self._win_cfg = get_window_config(getattr(self.settings, "platform_mode", "auto"))
        on_top = getattr(self.settings, "always_on_top", True)
        was_visible = self.isVisible()
        # Toggling these flags detaches/reattaches the window, so we re-show after.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        self.setWindowFlag(Qt.WindowType.Tool, self._win_cfg.use_tool_flag)
        opacity_pct = getattr(self.settings, "opacity", 100)
        self.setWindowOpacity(max(0.4, min(1.0, opacity_pct / 100)))
        if was_visible:
            self.show()
            # Re-show recreated the native window — re-apply native tweaks.
            self._native_applied = False
            self._apply_native_overlay()

    def _apply_native_overlay(self) -> None:
        """Ask macOS to keep the window over all Spaces / fullscreen apps.

        Only runs when the active platform config calls for it (macOS) and
        the user has 'always on top' enabled.
        """
        if getattr(self, "_native_applied", False):
            return
        if not self._win_cfg.use_macos_native:
            return
        if getattr(self.settings, "always_on_top", True):
            if make_overlay_persistent(self):
                self._native_applied = True

    def showEvent(self, ev):  # noqa: D401
        super().showEvent(ev)
        # winId() / NSWindow only exist once the window is shown.
        self._apply_native_overlay()

    # ---------- dragging ----------
    def mousePressEvent(self, ev):  # noqa: D401
        if ev.button() == Qt.MouseButton.LeftButton and ev.position().y() <= self.HEADER_HEIGHT:
            self._drag_offset = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_offset is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_offset)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag_offset = None
        self.unsetCursor()

    # ---------- bridge wiring ----------
    def _wire_bridge(self) -> None:
        self.bridge.transcript_appended.connect(self._on_transcript_appended)
        self.bridge.answer_started.connect(self._on_answer_started)
        self.bridge.answer_delta.connect(self._on_answer_delta)
        self.bridge.answer_done.connect(self._on_answer_done)
        self.bridge.error.connect(self._on_error)
        self.bridge.status.connect(self._set_status)

    # ---------- listening lifecycle ----------
    def toggle_listening(self) -> None:
        if self._listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self) -> None:
        # Make sure the Whisper model is on disk before we start — otherwise
        # every sentence would fail with the same error.
        if not self._transcriber.is_ready():
            self._set_status("model missing", dot="dot_error")
            self.answer.setPlainText(
                f"⚠ Whisper model '{self._transcriber.model_name}' isn't "
                f"downloaded yet.\n\n"
                f"In Terminal, run this once (it's resumable):\n\n"
                f'    cd "{APP_DIR}"\n'
                f"    source .venv/bin/activate\n"
                f"    python download_model.py {self._transcriber.model_name}\n\n"
                f"Then press Listen again."
            )
            self.listen_btn.setChecked(False)
            return

        device = self.source_combo.currentText()
        if device.startswith("("):
            device = ""
        self._capture = AudioCapture(
            device=device,
            on_utterance=self._on_utterance_worker,
            on_error=lambda msg: self.bridge.error.emit(msg),
        )
        self._capture.start()
        self._listening = True
        self.listen_btn.setChecked(True)
        self.listen_btn.setText("Stop")
        self._set_status("listening", dot="dot_listening")

    def _stop_listening(self) -> None:
        if self._capture:
            self._capture.stop()
            self._capture = None
        self._llm_stop.set()
        self._listening = False
        self.listen_btn.setChecked(False)
        self.listen_btn.setText("Listen")
        self._set_status("idle", dot="dot_idle")

    # ---------- worker callbacks (NOT on GUI thread) ----------
    def _on_utterance_worker(self, audio: np.ndarray) -> None:
        """Runs in the audio thread. Transcribe, then maybe answer."""
        try:
            text = self._transcriber.transcribe(audio)
        except Exception as exc:
            self.bridge.error.emit(f"Transcription failed: {exc}")
            return
        if not text:
            return
        self.bridge.transcript_appended.emit(text)
        if looks_like_question(text):
            self._kick_off_answer(text)

    def _kick_off_answer(self, question: str) -> None:
        self._llm_stop.set()  # cancel any in-flight stream
        self._llm_stop = threading.Event()
        stop_event = self._llm_stop
        self.bridge.answer_started.emit()

        messages = build_messages(
            question=question,
            resume=self.settings.resume,
            job_description=self.settings.job_description,
            style=self.settings.style,
        )

        def run() -> None:
            stream_completion(
                api_key=self.settings.deepseek_api_key,
                model=self.settings.deepseek_model,
                messages=messages,
                on_delta=lambda d: self.bridge.answer_delta.emit(d),
                on_done=lambda: self.bridge.answer_done.emit(),
                on_error=lambda m: self.bridge.error.emit(m),
                stop_check=stop_event.is_set,
            )

        threading.Thread(target=run, name="LLMStream", daemon=True).start()

    # ---------- GUI-thread slots ----------
    def _on_transcript_appended(self, text: str) -> None:
        self.transcript.setPlainText(text)

    def _on_answer_started(self) -> None:
        self.answer.clear()
        self._set_status("thinking…", dot="dot_thinking")

    def _on_answer_delta(self, delta: str) -> None:
        cursor = self.answer.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(delta)
        self.answer.setTextCursor(cursor)

    def _on_answer_done(self) -> None:
        if self._listening:
            self._set_status("listening", dot="dot_listening")
        else:
            self._set_status("idle", dot="dot_idle")

    def _on_error(self, msg: str) -> None:
        self._set_status("error", dot="dot_error")
        # show in answer pane so it's visible — non-blocking
        self.answer.setPlainText(f"⚠ {msg}")

    def _set_status(self, text: str, dot: str = "dot_idle") -> None:
        self.status_label.setText(text)
        self.status_dot.setObjectName(dot)
        # re-apply stylesheet so the new objectName takes effect
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    # ---------- source change ----------
    def _on_source_changed(self, text: str) -> None:
        if text.startswith("("):
            self.settings.audio_device = ""
        else:
            self.settings.audio_device = text
        self.settings.save()
        if self._listening:
            self._stop_listening()
            self._start_listening()

    # ---------- settings ----------
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, list_input_devices(), self)
        if dlg.exec():
            new = dlg.result_settings()
            # preserve hotkey
            new.hotkey = self.settings.hotkey
            self.settings = new
            self.settings.save()
            # if the whisper model changed, drop the cached model
            if new.whisper_model != self._transcriber.model_name:
                self._transcriber = Transcriber(model_name=new.whisper_model)
            self._refresh_devices()
            self._apply_window_prefs()
            QMessageBox.information(self, "Saved", "Settings saved.")

    # ---------- panes ----------
    def _clear_panes(self) -> None:
        self.transcript.clear()
        self.answer.clear()

    # ---------- cleanup ----------
    def quit_app(self) -> None:
        """Stop listening, cancel any stream, and fully exit the application."""
        self._stop_listening()
        self._llm_stop.set()
        self.close()
        QApplication.quit()

    def closeEvent(self, ev):  # noqa: D401
        self._stop_listening()
        self._llm_stop.set()
        ev.accept()
        QApplication.quit()
