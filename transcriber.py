"""Local Whisper transcription via pywhispercpp.

The model file is expected to already exist at
~/.diycopilot/models/ggml-<name>.bin — download it once with:

    python download_model.py base.en

We deliberately do NOT let pywhispercpp auto-download, because its downloader
isn't resumable and gets re-triggered on every utterance if it fails.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import numpy as np

MODELS_DIR = Path.home() / ".diycopilot" / "models"


def _bundled_models_dir() -> Path | None:
    """When packaged by PyInstaller, bundled data lives under sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "models"
    return None


def _find_model_file(model_name: str) -> Path | None:
    """Look for ggml-<name>.bin in the user dir first, then a bundled copy."""
    fname = f"ggml-{model_name}.bin"
    candidates = [MODELS_DIR / fname]
    bundled = _bundled_models_dir()
    if bundled is not None:
        candidates.append(bundled / fname)
    for path in candidates:
        if path.exists() and path.stat().st_size > 1_000_000:
            return path
    return None


class ModelNotDownloaded(RuntimeError):
    """Raised when the Whisper .bin file isn't on disk yet."""


class Transcriber:
    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        # If a load fails for a non-recoverable reason, remember it so we don't
        # spam retries (and downloads) on every single utterance.
        self._fatal_error: str | None = None

    def model_path(self) -> Path:
        """Resolved model file — bundled copy if found, else the user-dir path."""
        found = _find_model_file(self.model_name)
        return found if found is not None else MODELS_DIR / f"ggml-{self.model_name}.bin"

    def is_ready(self) -> bool:
        return _find_model_file(self.model_name) is not None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        if self._fatal_error is not None:
            raise ModelNotDownloaded(self._fatal_error)

        with self._lock:
            if self._model is not None:
                return

            path = self.model_path()
            if not self.is_ready():
                self._fatal_error = (
                    f"Whisper model not found.\n"
                    f"Download it once (resumable):\n"
                    f"    python download_model.py {self.model_name}"
                )
                raise ModelNotDownloaded(self._fatal_error)

            # Imported lazily so the app can boot even if the native dep
            # hasn't finished building yet.
            from pywhispercpp.model import Model  # type: ignore

            # Passing an explicit .bin path makes pywhispercpp load it directly
            # instead of trying to download by short name.
            self._model = Model(
                str(path),
                n_threads=4,
                print_realtime=False,
                print_progress=False,
            )

    def prewarm(self) -> None:
        """Load the model in a background thread so the first real
        transcription doesn't pay cold-start latency."""
        if self._model is not None or not self.is_ready():
            return

        def _go() -> None:
            try:
                self._ensure_loaded()
            except Exception:
                pass  # surfaced again on first real transcribe call

        threading.Thread(target=_go, name="WhisperPrewarm", daemon=True).start()

    def transcribe(self, audio: np.ndarray, initial_prompt: str = "") -> str:
        """Transcribe a float32 16 kHz mono numpy array into plain text.

        ``initial_prompt`` biases Whisper toward specific words/names — handy
        for company names, product names, or your interviewer's name so they
        come back spelled correctly.
        """
        if audio.size == 0:
            return ""
        self._ensure_loaded()
        assert self._model is not None
        kwargs: dict = {"language": "en"}
        if initial_prompt:
            # Trim to a reasonable size; Whisper's prompt window is ~224 tokens.
            kwargs["initial_prompt"] = initial_prompt[:800]
        segments = self._model.transcribe(audio.astype(np.float32), **kwargs)
        return " ".join(seg.text.strip() for seg in segments).strip()
