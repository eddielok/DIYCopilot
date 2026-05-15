"""Persistent settings + the settings dialog."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from platform_config import PLATFORM_MODES

SETTINGS_DIR = Path.home() / ".diycopilot"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"


@dataclass
class Settings:
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    audio_device: str = ""  # substring match against sounddevice device name
    whisper_model: str = "base.en"
    resume: str = ""
    job_description: str = ""
    hotkey: str = "<cmd>+<shift>+<space>"
    style: str = "bullets_then_full"  # bullets_then_full | bullets | full
    always_on_top: bool = True
    opacity: int = 100  # window opacity percentage, 40–100
    platform_mode: str = "auto"  # auto | macos | windows | linux

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text())
                return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2))
        try:
            os.chmod(SETTINGS_PATH, 0o600)
        except OSError:
            pass


DIALOG_STYLE = """
    QDialog { background: #eceef1; }

    /* header / footer bars */
    #dlgHeader, #dlgFooter { background: #ffffff; }
    #dlgHeader { border-bottom: 1px solid #e2e5ea; }
    #dlgFooter { border-top: 1px solid #e2e5ea; }
    #dlgTitle { font-size: 17px; font-weight: 700; color: #14181f; }
    #dlgSub   { font-size: 12px; color: #6b7280; }

    /* scroll area */
    QScrollArea#scroll { border: none; background: #eceef1; }
    #content { background: #eceef1; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
    QScrollBar::handle:vertical {
        background: #c4c9d1; border-radius: 5px; min-height: 32px;
    }
    QScrollBar::handle:vertical:hover { background: #a8aeb8; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    /* cards */
    #card {
        background: #ffffff;
        border: 1px solid #e2e5ea;
        border-radius: 10px;
    }
    #cardTitle {
        font-size: 11px; font-weight: 700; color: #8a93a0;
        letter-spacing: 0.9px;
    }
    #fieldName { font-size: 13px; font-weight: 600; color: #1f2430; }
    #fieldDesc { font-size: 11px; color: #7b828c; }

    /* inputs */
    QLineEdit, QPlainTextEdit, QComboBox {
        background: #f7f8fa;
        color: #1f2430;
        border: 1px solid #d4d8df;
        border-radius: 7px;
        padding: 7px 10px;
        font-size: 13px;
        selection-background-color: #2563eb;
        selection-color: #ffffff;
    }
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
        border: 1px solid #2563eb;
        background: #ffffff;
    }
    QComboBox::drop-down { border: none; width: 22px; }
    QComboBox QAbstractItemView {
        background: #ffffff;
        color: #1f2430;
        border: 1px solid #d4d8df;
        selection-background-color: #2563eb;
        selection-color: #ffffff;
        outline: none;
    }

    /* buttons */
    QPushButton#btnPrimary {
        background: #2563eb; color: #ffffff;
        border: none; border-radius: 7px;
        padding: 8px 24px; font-weight: 600; font-size: 13px;
    }
    QPushButton#btnPrimary:hover  { background: #1d4ed8; }
    QPushButton#btnPrimary:pressed { background: #1e40af; }
    QPushButton#btnGhost {
        background: transparent; color: #4b5563;
        border: 1px solid #d4d8df; border-radius: 7px;
        padding: 8px 18px; font-size: 13px;
    }
    QPushButton#btnGhost:hover { background: #f1f3f5; color: #1f2430; }

    /* checkbox + slider */
    QCheckBox { font-size: 13px; color: #1f2430; spacing: 8px; }
    QCheckBox::indicator {
        width: 18px; height: 18px; border-radius: 5px;
        border: 1px solid #d4d8df; background: #f7f8fa;
    }
    QCheckBox::indicator:checked { background: #2563eb; border: 1px solid #2563eb; }
    QCheckBox::indicator:hover { border: 1px solid #2563eb; }
    QSlider::groove:horizontal {
        height: 4px; background: #d4d8df; border-radius: 2px;
    }
    QSlider::sub-page:horizontal { background: #2563eb; border-radius: 2px; }
    QSlider::handle:horizontal {
        width: 16px; height: 16px; margin: -7px 0;
        background: #ffffff; border: 1px solid #b9bfc8; border-radius: 8px;
    }
    QSlider::handle:horizontal:hover { border: 1px solid #2563eb; }
    #opacityValue { font-size: 12px; color: #4b5563; font-weight: 600; }
"""


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, audio_devices: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("DIY Copilot — Settings")
        self.setMinimumSize(560, 600)
        self.resize(600, 720)
        self._s = settings
        self.setStyleSheet(DIALOG_STYLE)

        # ---- build the input widgets ----
        self.key_edit = QLineEdit(settings.deepseek_api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-...")

        self.model_edit = QLineEdit(settings.deepseek_model)
        self.model_edit.setPlaceholderText("deepseek-chat")

        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)
        self.device_combo.addItem("")  # default
        for d in audio_devices:
            self.device_combo.addItem(d)
        if settings.audio_device:
            idx = self.device_combo.findText(settings.audio_device)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
            else:
                self.device_combo.setEditText(settings.audio_device)

        self.whisper_combo = QComboBox()
        for m in ("tiny.en", "base.en", "small.en", "medium.en"):
            self.whisper_combo.addItem(m)
        self.whisper_combo.setCurrentText(settings.whisper_model)

        self.style_combo = QComboBox()
        for label, value in (
            ("Bullets, then full answer", "bullets_then_full"),
            ("Bullets only", "bullets"),
            ("Full scripted answer", "full"),
        ):
            self.style_combo.addItem(label, value)
        idx = self.style_combo.findData(settings.style)
        if idx >= 0:
            self.style_combo.setCurrentIndex(idx)

        self.resume_edit = QPlainTextEdit(settings.resume)
        self.resume_edit.setPlaceholderText("Paste your resume here…")
        self.resume_edit.setMinimumHeight(120)

        self.jd_edit = QPlainTextEdit(settings.job_description)
        self.jd_edit.setPlaceholderText("Paste the job description here…")
        self.jd_edit.setMinimumHeight(120)

        self.platform_combo = QComboBox()
        for value, label in PLATFORM_MODES:
            self.platform_combo.addItem(label, value)
        idx = self.platform_combo.findData(settings.platform_mode)
        if idx >= 0:
            self.platform_combo.setCurrentIndex(idx)

        self.aot_check = QCheckBox("Keep the overlay above other windows")
        self.aot_check.setChecked(settings.always_on_top)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(40, 100)
        self.opacity_slider.setValue(max(40, min(100, settings.opacity)))
        self.opacity_value = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value.setObjectName("opacityValue")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value.setText(f"{v}%")
        )
        self._opacity_row = QWidget()
        _orl = QHBoxLayout(self._opacity_row)
        _orl.setContentsMargins(0, 0, 0, 0)
        _orl.setSpacing(10)
        _orl.addWidget(self.opacity_slider, 1)
        _orl.addWidget(self.opacity_value)

        # ---- header ----
        header = QWidget()
        header.setObjectName("dlgHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(22, 16, 22, 16)
        hl.setSpacing(2)
        title = QLabel("Settings")
        title.setObjectName("dlgTitle")
        sub = QLabel("Configure your interview copilot")
        sub.setObjectName("dlgSub")
        hl.addWidget(title)
        hl.addWidget(sub)

        # ---- scrollable content with grouped cards ----
        content = QWidget()
        content.setObjectName("content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(14)

        ai_card = self._card("AI PROVIDER")
        self._add_field(
            ai_card, "DeepSeek API key",
            "Your key from platform.deepseek.com. Stored locally, never synced.",
            self.key_edit,
        )
        self._add_field(
            ai_card, "DeepSeek model",
            "'deepseek-chat' is the standard choice.",
            self.model_edit,
        )
        cl.addWidget(ai_card)

        audio_card = self._card("AUDIO & TRANSCRIPTION")
        self._add_field(
            audio_card, "Audio input",
            "Where to listen. Pick 'BlackHole 2ch' for remote calls, "
            "or your mic for in-person.",
            self.device_combo,
        )
        self._add_field(
            audio_card, "Whisper model",
            "Local speech-to-text. Bigger = more accurate but slower. "
            "'base.en' is a good balance.",
            self.whisper_combo,
        )
        cl.addWidget(audio_card)

        answer_card = self._card("ANSWERS")
        self._add_field(
            answer_card, "Answer style",
            "How answers are formatted in the overlay.",
            self.style_combo,
        )
        self._add_field(
            answer_card, "Resume",
            "Pasted into every prompt so answers reflect your real experience.",
            self.resume_edit,
        )
        self._add_field(
            answer_card, "Job description",
            "The role you're interviewing for, so answers are tailored to it.",
            self.jd_edit,
        )
        cl.addWidget(answer_card)

        window_card = self._card("WINDOW")
        self._add_field(
            window_card, "Platform",
            "Which OS's window behavior to use. Auto-detect picks it from your "
            "system. macOS floats over Spaces & fullscreen apps; Windows keeps "
            "the overlay off the taskbar.",
            self.platform_combo,
        )
        self._add_field(
            window_card, "Always on top",
            "When on, the overlay floats above every other window — including "
            "your meeting app. Turn off to let it behave like a normal window.",
            self.aot_check,
        )
        self._add_field(
            window_card, "Window opacity",
            "Make the overlay see-through. Lower = more transparent — handy to "
            "keep an eye on what's behind it.",
            self._opacity_row,
        )
        cl.addWidget(window_card)
        cl.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("scroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        # ---- footer ----
        footer = QWidget()
        footer.setObjectName("dlgFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(22, 14, 22, 14)
        fl.setSpacing(10)
        fl.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnGhost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("btnPrimary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        fl.addWidget(cancel_btn)
        fl.addWidget(save_btn)

        # ---- assemble ----
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(header)
        outer.addWidget(scroll, 1)
        outer.addWidget(footer)

    # ---- layout helpers ----
    @staticmethod
    def _card(title: str) -> QFrame:
        """An empty rounded white card with an uppercase title; add fields via _add_field."""
        frame = QFrame()
        frame.setObjectName("card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 14, 16, 16)
        v.setSpacing(14)
        cap = QLabel(title)
        cap.setObjectName("cardTitle")
        v.addWidget(cap)
        return frame

    @staticmethod
    def _add_field(card: QFrame, name: str, description: str, widget: QWidget) -> None:
        """Stack a bold label + grey helper text + the input widget inside a card."""
        block = QVBoxLayout()
        block.setSpacing(4)
        lbl = QLabel(name)
        lbl.setObjectName("fieldName")
        desc = QLabel(description)
        desc.setObjectName("fieldDesc")
        desc.setWordWrap(True)
        block.addWidget(lbl)
        block.addWidget(desc)
        block.addWidget(widget)
        card.layout().addLayout(block)

    def result_settings(self) -> Settings:
        return Settings(
            deepseek_api_key=self.key_edit.text().strip(),
            deepseek_model=self.model_edit.text().strip() or "deepseek-chat",
            audio_device=self.device_combo.currentText().strip(),
            whisper_model=self.whisper_combo.currentText(),
            resume=self.resume_edit.toPlainText().strip(),
            job_description=self.jd_edit.toPlainText().strip(),
            hotkey=self._s.hotkey,
            style=self.style_combo.currentData() or "bullets_then_full",
            always_on_top=self.aot_check.isChecked(),
            opacity=self.opacity_slider.value(),
            platform_mode=self.platform_combo.currentData() or "auto",
        )
