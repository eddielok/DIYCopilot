"""Resumable Whisper model downloader.

pywhispercpp's built-in downloader restarts from 0% on any network hiccup.
This one resumes where it left off and retries automatically, so a slow or
flaky connection won't make you start over.

Usage:
    source .venv/bin/activate
    python download_model.py            # downloads base.en (default)
    python download_model.py small.en   # or pick another size

Models are saved to ~/.diycopilot/models/ and the app loads them from there.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

MODELS_DIR = Path.home() / ".diycopilot" / "models"
BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VALID = ("tiny.en", "base.en", "small.en", "medium.en", "tiny", "base", "small", "medium")
MAX_RETRIES = 1000          # effectively "keep trying" — Ctrl+C to stop
RETRY_WAIT = 3              # seconds between retries


def _human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def download(model_name: str = "base.en") -> Path:
    if model_name not in VALID:
        print(f"Unknown model '{model_name}'. Choose from: {', '.join(VALID)}")
        sys.exit(1)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"ggml-{model_name}.bin"
    url = f"{BASE_URL}/{fname}"
    dest = MODELS_DIR / fname
    part = MODELS_DIR / (fname + ".part")

    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"✓ Model already present: {dest} ({_human(dest.stat().st_size)})")
        return dest

    print(f"Downloading {fname}")
    print(f"  from: {url}")
    print(f"  to  : {dest}")
    print("  (resumable — safe to Ctrl+C and re-run; it picks up where it stopped)\n")

    total: int | None = None
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}

        try:
            with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as r:
                if r.status_code not in (200, 206):
                    print(f"  HTTP {r.status_code} — retrying in {RETRY_WAIT}s…")
                    time.sleep(RETRY_WAIT)
                    continue

                # Work out the full file size
                if r.status_code == 206:
                    # "Content-Range: bytes 1000-140999999/141000000"
                    cr = r.headers.get("Content-Range", "")
                    if "/" in cr:
                        total = int(cr.rsplit("/", 1)[1])
                else:
                    have = 0  # server ignored Range — restart cleanly
                    cl = r.headers.get("Content-Length")
                    total = int(cl) if cl else None

                mode = "ab" if have else "wb"
                last_print = 0.0
                with open(part, mode) as f:
                    downloaded = have
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_print >= 0.5:
                            last_print = now
                            if total:
                                pct = downloaded / total * 100
                                bars = int(pct / 2)
                                print(
                                    f"\r  [{'█' * bars}{' ' * (50 - bars)}] "
                                    f"{pct:5.1f}%  {_human(downloaded)} / {_human(total)}",
                                    end="",
                                    flush=True,
                                )
                            else:
                                print(f"\r  {_human(downloaded)} downloaded", end="", flush=True)
            print()  # newline after progress bar

            # Did we get the whole thing?
            final_size = part.stat().st_size
            if total is None or final_size >= total:
                part.rename(dest)
                print(f"\n✓ Done: {dest} ({_human(dest.stat().st_size)})")
                return dest
            else:
                print(f"  Connection ended early at {_human(final_size)} — resuming…")
                time.sleep(RETRY_WAIT)

        except (requests.RequestException, OSError) as exc:
            done = part.stat().st_size if part.exists() else 0
            print(f"\n  Network hiccup ({exc.__class__.__name__}) at {_human(done)} — "
                  f"resuming in {RETRY_WAIT}s… (attempt {attempt})")
            time.sleep(RETRY_WAIT)

    print("Gave up after many retries. Check your internet connection and re-run.")
    sys.exit(1)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "base.en"
    try:
        download(name)
    except KeyboardInterrupt:
        print("\n\nStopped. Re-run the same command to resume from where you left off.")
        sys.exit(130)
