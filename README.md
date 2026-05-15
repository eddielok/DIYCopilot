# DIY Interview Copilot

An always-on-top desktop overlay (macOS, Windows, Linux) that listens to your
interviewer in real time, transcribes their question with a local Whisper model,
and instantly streams a tailored answer from DeepSeek — grounded in your resume
and the job description.

```
┌────────── DIY Copilot ─────────── ⚙ ─ ✕ ┐
│ Source: [BlackHole 2ch ▾]   ● Listening │
│                                          │
│ Q: "Tell me about a time you led a…"     │
│                                          │
│ A: • Led migration of legacy billing…    │
│    • Cut costs 38% by consolidating…     │
│    • Mentored 4 engineers through…       │
│                                          │
│   [Full answer ▾]                        │
└──────────────────────────────────────────┘
```

## 1. One-time setup

### a. Capture system audio

For a *remote* interview the Copilot needs to "hear" the audio coming out of
your meeting app. Each OS does this differently. (For an *in-person* interview
you can skip all of this and just pick your microphone from the Source
dropdown.)

#### macOS — BlackHole

```bash
brew install blackhole-2ch
```

Then in **Audio MIDI Setup** create a **Multi-Output Device** containing your
speakers + BlackHole 2ch (set your speakers as the Primary Device, tick Drift
Correction on BlackHole). In Zoom/Meet/Teams set the **speaker** to that
Multi-Output (so you can still hear the interviewer), and pick **BlackHole 2ch**
as the Copilot's Source.

#### Windows — VB-CABLE

Install **VB-Audio Virtual Cable** (free) from <https://vb-audio.com/Cable/>.
After installing, two devices appear: *CABLE Input* (a playback device) and
*CABLE Output* (a recording device).

In Zoom/Teams, set the **speaker** to **CABLE Input**. To still hear the
interviewer yourself, open *Sound settings → Recording → CABLE Output →
Properties → Listen → "Listen to this device"* and route it to your real
speakers/headphones. Then pick **CABLE Output** as the Copilot's Source.

(Alternatively, if your sound card exposes *Stereo Mix*, you can enable that in
the Recording devices list and use it as the Source — no install needed.)

#### Linux — PulseAudio / PipeWire monitor

No extra software needed. Every output device has a built-in `.monitor` source
that taps whatever is playing. In the Copilot's Source dropdown, pick the entry
named **"Monitor of <your output device>"**. You hear audio normally because a
monitor is a passive tap. (`pavucontrol` is handy for confirming routing.)

Then set the **Platform** to match your OS in Settings → Window (or leave it on
Auto-detect).

### b. Python deps

**Requires Python 3.10 or newer** (pywhispercpp uses 3.10+ syntax). Check with
`python3 --version` (or `py --version` on Windows).

**macOS**

```bash
cd ~/Documents/claude/DIYCopilot
python3.12 -m venv .venv          # brew install python@3.12 if needed
source .venv/bin/activate
pip install -r requirements.txt
```

Needs the Xcode command-line tools for the whisper.cpp build:
`xcode-select --install`.

**Windows** (PowerShell)

```powershell
cd $HOME\Documents\claude\DIYCopilot
py -3.12 -m venv .venv            # install Python 3.12 from python.org if needed
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `pywhispercpp` fails to build, install the "Desktop development with C++"
workload from the Visual Studio Build Tools, then retry.

**Linux**

```bash
cd ~/Documents/claude/DIYCopilot
python3.12 -m venv .venv          # sudo apt install python3.12-venv if needed
source .venv/bin/activate
pip install -r requirements.txt
```

You may need build tools and PortAudio headers first:
`sudo apt install build-essential portaudio19-dev`.

The `pyobjc-framework-Cocoa` line in `requirements.txt` only installs on macOS
(it's gated by platform marker), so Windows/Linux installs skip it
automatically.

### b2. Download the Whisper model (one time)

The `base.en` model (~141 MB) must be downloaded once before first use. Use
the bundled **resumable** downloader — if your wifi is slow or drops, it picks
up where it left off instead of restarting:

```bash
source .venv/bin/activate
python download_model.py base.en
```

It's saved to `~/.diycopilot/models/` and the app loads it from there. Safe to
Ctrl+C and re-run.

### c. DeepSeek API key

Get one at <https://platform.deepseek.com>. Launch the app, click ⚙, paste the
key, paste your resume, paste the job description, save.

## 2. Run it

macOS / Linux:

```bash
source .venv/bin/activate
python main.py
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
python main.py
```

The overlay appears top-right, always on top. Drag it by the header.

- **Listen** — start/stop capturing audio
- **⌘⇧Space** — global hotkey to toggle Listen from any app
- **⚙** — open settings
- **✕** — quit

## 2b. Build a standalone app (optional)

To turn it into a double-clickable app (no terminal, no venv needed by the
end user):

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
python build.py
```

Output:

- **macOS** → `dist/DIY Copilot.app` — drag to /Applications. It's unsigned, so
  the first launch needs right-click → Open. macOS asks for Microphone
  permission on first listen (the bundled Info.plist declares why).
- **Windows** → `dist/DIY Copilot/DIY Copilot.exe` — the whole folder is the
  app; zip and share it.

PyInstaller does **not** cross-compile — build the `.app` on a Mac and the
`.exe` on Windows. If `~/.diycopilot/models/ggml-base.en.bin` exists at build
time it's bundled in, making the app fully self-contained; otherwise the
packaged app asks the user to download it on first run.

## 3. How it works

```
┌──────────┐  audio   ┌──────────────┐  text   ┌──────────────┐
│ BlackHole│ ───────▶ │ whisper.cpp  │ ──────▶ │  question?   │
│  or mic  │          │ (local STT)  │         │ end-of-speech│
└──────────┘          └──────────────┘         └──────┬───────┘
                                                      │ yes
                                              ┌───────▼────────┐
                                              │  DeepSeek API  │
                                              │  resume + JD   │
                                              │  + question    │
                                              └───────┬────────┘
                                                      │ stream
                                              ┌───────▼────────┐
                                              │   Overlay UI   │
                                              └────────────────┘
```

A question is detected when ~1.2 s of silence follows speech that ends with
`?` or with an interrogative cue word (`what / why / how / tell me / describe
/ walk me / can you …`).

## 4. Files

| File                 | What it does                                         |
| -------------------- | ---------------------------------------------------- |
| `main.py`            | Entry point — wires everything together              |
| `overlay.py`         | Always-on-top frameless PyQt overlay                 |
| `audio.py`           | sounddevice capture + simple end-of-utterance detect |
| `transcriber.py`     | pywhispercpp wrapper, runs in a worker thread        |
| `llm.py`             | DeepSeek streaming chat client                       |
| `settings.py`        | JSON-backed settings + PyQt settings dialog          |
| `platform_config.py` | Per-OS window behavior (macOS / Windows / Linux)     |
| `download_model.py`  | Resumable Whisper model downloader                   |
| `diagnose.py`        | Step-by-step pipeline diagnostics                    |
| `_sslfix.py`         | Routes HTTPS through the OS trust store (corp certs) |
| `_macos.py`          | macOS-native window tweaks (float over fullscreen)   |
| `~/.diycopilot/`     | Stored settings + Whisper models (never synced)      |

## 5. Privacy

Audio never leaves your machine — transcription is local. Only the resulting
text (transcript + your resume + JD + question) is sent to DeepSeek. Delete
`~/.diycopilot/settings.json` to wipe everything.

## 6. Legal / ethical note

Recording or transcribing a conversation may require the other party's consent
depending on your jurisdiction. Use responsibly.
