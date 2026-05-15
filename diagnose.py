"""DIY Copilot — diagnostics.

Run this to check each piece of the pipeline independently:

    source .venv/bin/activate
    python diagnose.py

It will:
  1. List your audio input devices
  2. Record 6 seconds from your configured device and report the signal level
     (so you can SEE whether audio is actually reaching BlackHole)
  3. Load the Whisper model and transcribe what it recorded
  4. Send a test question to DeepSeek and print the answer
"""
from __future__ import annotations

import sys
import time

if sys.version_info < (3, 10):
    sys.stderr.write(
        f"\nDIY Copilot needs Python 3.10+ (you are on {sys.version.split()[0]}).\n"
        "Rebuild the venv:\n"
        "  brew install python@3.12\n"
        "  rm -rf .venv && python3.12 -m venv .venv\n"
        "  source .venv/bin/activate && pip install -r requirements.txt\n\n"
    )
    sys.exit(1)

import _sslfix  # noqa: F401  -- must be imported before any HTTPS call

import numpy as np


def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> int:
    from settings import Settings

    s = Settings.load()
    print(f"Loaded settings from ~/.diycopilot/settings.json")
    print(f"  audio_device   : {s.audio_device or '(default input)'}")
    print(f"  whisper_model  : {s.whisper_model}")
    print(f"  deepseek_model : {s.deepseek_model}")
    print(f"  api key set    : {'yes' if s.deepseek_api_key else 'NO — set it in Settings'}")
    print(f"  resume set     : {'yes' if s.resume else 'no'}")
    print(f"  JD set         : {'yes' if s.job_description else 'no'}")

    # ---- 1. devices -------------------------------------------------------
    section("1. AUDIO INPUT DEVICES")
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"  ✗ sounddevice not installed: {exc}")
        print("    Fix: pip install -r requirements.txt")
        return 1

    devices = sd.query_devices()
    input_devices = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    for i, d in input_devices:
        marker = ""
        if s.audio_device and s.audio_device.lower() in d["name"].lower():
            marker = "  <-- your configured device"
        print(f"  [{i}] {d['name']}  ({d['max_input_channels']} in){marker}")
    if not input_devices:
        print("  ✗ No input devices found at all.")
        return 1

    # ---- 2. record + level meter -----------------------------------------
    section("2. RECORD TEST  (6 seconds)")
    device_index = None
    if s.audio_device:
        for i, d in input_devices:
            if s.audio_device.lower() in d["name"].lower():
                device_index = i
                break
        if device_index is None:
            print(f"  ✗ Configured device '{s.audio_device}' not found — using default.")
    print(f"  Recording from: "
          f"{devices[device_index]['name'] if device_index is not None else '(default)'}")
    print("  >>> PLAY SOME AUDIO NOW (a YouTube video, talk out loud, etc.) <<<")
    print()

    SR = 16_000
    seconds = 6
    recorded = []
    try:
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                            device=device_index) as stream:
            for t in range(seconds):
                block, _ = stream.read(SR)
                mono = block[:, 0]
                recorded.append(mono)
                rms = float(np.sqrt(np.mean(mono ** 2) + 1e-12))
                bars = int(min(rms * 800, 50))
                level = "█" * bars
                state = "  (silent)" if rms < 0.008 else "  ✓ signal!"
                print(f"  {t+1}s  rms={rms:.4f} |{level:<50}|{state}")
    except Exception as exc:
        print(f"  ✗ Could not open audio stream: {exc}")
        return 1

    audio = np.concatenate(recorded) if recorded else np.zeros(0, dtype=np.float32)
    peak_rms = float(np.sqrt(np.mean(audio ** 2) + 1e-12))
    print()
    if peak_rms < 0.008:
        print("  ✗ NO AUDIO DETECTED. The signal stayed silent the whole time.")
        print("    This is almost certainly the problem. Checklist:")
        print("      - Is your system / meeting-app OUTPUT set to a device that")
        print("        includes BlackHole? (e.g. your 'Interview Audio' multi-output)")
        print("      - Was audio actually playing during the 6-second window?")
        print("      - In System Settings > Sound > Output, pick 'Interview Audio',")
        print("        play a video, and run this again.")
    else:
        print(f"  ✓ Audio captured fine (overall rms={peak_rms:.4f}).")

    # ---- 3. whisper -------------------------------------------------------
    section("3. WHISPER TRANSCRIPTION")
    from transcriber import Transcriber
    tr = Transcriber(model_name=s.whisper_model)
    if not tr.is_ready():
        print(f"  ✗ Whisper model '{s.whisper_model}' is not downloaded.")
        print(f"    Download it once (resumable, retries on flaky wifi):")
        print(f"        python download_model.py {s.whisper_model}")
    elif peak_rms < 0.008:
        print("  Model is present, but nothing was recorded to transcribe.")
    else:
        try:
            print(f"  Loading model from {tr.model_path()} …")
            t0 = time.time()
            text = tr.transcribe(audio)
            print(f"  Done in {time.time() - t0:.1f}s.")
            if text:
                print(f"  ✓ Transcript: \"{text}\"")
            else:
                print("  ⚠ Model ran but produced no text — audio may be too quiet/noisy.")
        except Exception as exc:
            print(f"  ✗ Whisper failed: {exc}")
            print("    Fix: pip install --force-reinstall pywhispercpp")

    # ---- 4. deepseek ------------------------------------------------------
    section("4. DEEPSEEK API")
    if not s.deepseek_api_key:
        print("  ✗ No API key configured. Open the app > ⚙ > paste your key.")
    else:
        try:
            from llm import build_messages, stream_completion
            msgs = build_messages(
                "Tell me about a time you solved a hard problem.",
                s.resume, s.job_description, s.style,
            )
            chunks: list[str] = []
            errors: list[str] = []
            print(f"  Model: {s.deepseek_model}")
            print("  Sending test question… streaming reply:\n")
            stream_completion(
                api_key=s.deepseek_api_key,
                model=s.deepseek_model,
                messages=msgs,
                on_delta=lambda d: (chunks.append(d), print(d, end="", flush=True)),
                on_done=lambda: None,
                on_error=lambda m: errors.append(m),
            )
            print("\n")
            if errors:
                print(f"  ✗ DeepSeek error: {errors[0]}")
            elif chunks:
                print(f"  ✓ DeepSeek responded ({len(''.join(chunks))} chars).")
            else:
                print("  ⚠ No content returned and no error — check your key/quota.")
        except Exception as exc:
            print(f"  ✗ DeepSeek call failed: {exc}")

    section("SUMMARY")
    print("  If step 2 showed NO signal  -> fix audio routing (most common).")
    print("  If step 3 failed            -> reinstall pywhispercpp.")
    print("  If step 4 failed            -> check API key / DeepSeek account balance.")
    print("  If all 4 passed             -> the app itself works; in the overlay,")
    print("    make sure the Source dropdown matches the device that passed step 2,")
    print("    press Listen, and speak a clear QUESTION (ending in '?').")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
