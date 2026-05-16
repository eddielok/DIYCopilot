"""Audio capture + end-of-utterance detection.

Reads 16 kHz mono float32 audio from a sounddevice input, runs a tiny RMS-based
VAD, and emits whole utterances (numpy float32 arrays) whenever the speaker
finishes talking.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd  # type: ignore
except Exception:  # pragma: no cover - native dep may not be installed yet
    sd = None  # type: ignore


SAMPLE_RATE = 16_000
BLOCK_SECS = 0.05  # 50 ms blocks
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_SECS)

# tuning knobs
SILENCE_RMS = 0.008          # below this => silence
MIN_VOICED_SECS = 0.4        # ignore micro-noises
DEFAULT_END_OF_UTT_SILENCE = 0.7  # default trailing silence => utterance ends
MAX_UTTERANCE_SECS = 25.0    # hard cap
PREROLL_BLOCKS = 6           # 6 * 50ms = 300ms — kept before voice triggers
                             # so we don't clip the first word


def list_input_devices() -> list[str]:
    """Return human-readable names of input-capable devices."""
    if sd is None:
        return []
    names: list[str] = []
    try:
        for d in sd.query_devices():
            if d.get("max_input_channels", 0) > 0:
                names.append(d["name"])
    except Exception:
        pass
    # de-dup, keep order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _resolve_device(name_substr: str) -> Optional[int]:
    """Find a device index whose name contains `name_substr` (case-insensitive)."""
    if sd is None or not name_substr:
        return None
    name_substr = name_substr.lower()
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and name_substr in d["name"].lower():
                return i
    except Exception:
        return None
    return None


class AudioCapture:
    """Background thread that yields utterances via a callback.

    Usage:
        cap = AudioCapture(device="BlackHole", on_utterance=fn)
        cap.start()
        ...
        cap.stop()
    """

    def __init__(
        self,
        device: str,
        on_utterance: Callable[[np.ndarray], None],
        on_error: Optional[Callable[[str], None]] = None,
        end_of_utt_silence: float = DEFAULT_END_OF_UTT_SILENCE,
    ):
        self.device = device
        self.on_utterance = on_utterance
        self.on_error = on_error or (lambda _msg: None)
        self.end_of_utt_silence = end_of_utt_silence
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ----- lifecycle -----
    def start(self) -> None:
        if sd is None:
            self.on_error("sounddevice is not installed")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="AudioCapture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None

    # ----- worker -----
    def _run(self) -> None:
        device_index = _resolve_device(self.device) if self.device else None
        buffer: list[np.ndarray] = []
        preroll: list[np.ndarray] = []  # last few blocks of silence/quiet audio
        voiced_secs = 0.0
        silence_secs = 0.0
        in_utterance = False

        def callback(indata, frames, time_info, status):  # noqa: ANN001
            if status:
                # xruns happen — keep going
                pass
            # mono float32
            audio = indata[:, 0] if indata.ndim > 1 else indata
            self._inbox.append(audio.copy())

        self._inbox: list[np.ndarray] = []

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                channels=1,
                dtype="float32",
                device=device_index,
                callback=callback,
            ):
                while not self._stop.is_set():
                    if not self._inbox:
                        time.sleep(0.01)
                        continue
                    block = self._inbox.pop(0)
                    rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2) + 1e-12))
                    is_voice = rms > SILENCE_RMS

                    if in_utterance:
                        buffer.append(block)
                        if is_voice:
                            voiced_secs += BLOCK_SECS
                            silence_secs = 0.0
                        else:
                            silence_secs += BLOCK_SECS

                        total_secs = (voiced_secs + silence_secs)
                        if (
                            silence_secs >= self.end_of_utt_silence
                            and voiced_secs >= MIN_VOICED_SECS
                        ) or total_secs >= MAX_UTTERANCE_SECS:
                            audio = np.concatenate(buffer) if buffer else np.zeros(0, dtype=np.float32)
                            buffer = []
                            preroll = []
                            voiced_secs = 0.0
                            silence_secs = 0.0
                            in_utterance = False
                            try:
                                self.on_utterance(audio)
                            except Exception as exc:  # don't kill the thread
                                self.on_error(f"on_utterance error: {exc}")
                    else:
                        # Always retain a rolling pre-roll buffer of the most
                        # recent few blocks; when voice triggers, prepend them
                        # to the utterance so the very first phoneme isn't
                        # cut off.
                        preroll.append(block)
                        if len(preroll) > PREROLL_BLOCKS:
                            preroll.pop(0)
                        if is_voice:
                            in_utterance = True
                            buffer = list(preroll)
                            preroll = []
                            voiced_secs = BLOCK_SECS
                            silence_secs = 0.0
        except Exception as exc:
            self.on_error(f"audio stream error: {exc}")
