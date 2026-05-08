# vibing

Press the **right Option key** to start recording. Press it again to stop. Your speech is transcribed, cleaned up, and copied to the clipboard — all locally, no cloud needed.

Inspired by [Vibing](https://vibingjustspeakit.github.io/Vibing/).

## Pipeline

```
mic → raw WAV → ffmpeg loudnorm → whisper small → ollama mistral-nemo → clipboard
```

| Step | Tool | Output |
|------|------|--------|
| Record | sounddevice (Python) | `data/raw-audio/TIMESTAMP.wav` |
| Normalize | ffmpeg `loudnorm` | `data/normalized-audio/TIMESTAMP.wav` |
| Transcribe | whisper `--model small` | `data/raw-transcript/TIMESTAMP.txt` |
| Clean up | ollama `mistral-nemo` | `data/clean-transcript/TIMESTAMP.txt` |
| Deliver | pbcopy + osascript | clipboard + macOS notification |

---

## Prerequisites

### 1. ffmpeg

```bash
brew install ffmpeg
```

### 2. Whisper

```bash
pip install openai-whisper
```

The first transcription downloads the `small` model (~244 MB) automatically.

### 3. Ollama + mistral-nemo

```bash
# Install ollama
brew install ollama

# Pull the model
ollama pull mistral-nemo

# Start the server (skip this step after installing the launchd service below)
ollama serve
```

### 4. Python 3.10+

```bash
brew install python
```

---

## Configuration

Edit **`config.json`** in the project root. Changes take effect on the next restart.

```json
{
  "ollama_model": "mistral-nemo",
  "ollama_prompt": "Clean up this voice transcription. ... {transcription}",
  "output_dir": "~/Documents/vibing"
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `ollama_model` | `mistral-nemo` | Any model available in your local ollama (`ollama list`) |
| `ollama_prompt` | *(see file)* | Prompt sent to ollama. Must contain `{transcription}` — that placeholder is replaced with the raw whisper output |
| `output_dir` | `data` | Root for all four output subdirectories. Relative paths are resolved from the project root; absolute paths are used as-is |

---

## Quick start (foreground, for testing)

```bash
make run
```

This runs the recorder in your terminal. You will see log output in real time.
Press **right Option** to start/stop recording.

---

## Install as a background service

The Makefile installs a **LaunchAgent** that starts at login and restarts automatically if it crashes.

```bash
make install
```

This:
1. Creates `.venv/` and installs Python dependencies.
2. Generates `~/Library/LaunchAgents/com.vibing.audio-recorder.plist` from the template.
3. Loads the service via `launchctl`.

### Grant Accessibility access (required)

`pynput` needs the Accessibility permission to read global keyboard events.

1. Open **System Settings → Privacy & Security → Accessibility**.
2. Click **+** and add `.venv/bin/python3` inside this project directory.
   - If running with `make run` from Terminal, add **Terminal** (or iTerm2) instead.

Without this step the key listener silently does nothing.

### Useful commands

| Command | What it does |
|---------|-------------|
| `make install` | Install & start the service |
| `make uninstall` | Stop & remove the service |
| `make start` | Start a stopped service |
| `make stop` | Stop a running service |
| `make restart` | Restart the service |
| `make status` | Show whether the service is running |
| `make logs` | Follow the live log (`recorder.log`) |
| `make run` | Run in the foreground (debugging) |
| `make clean` | Remove virtualenv and all captured data |

---

## Usage

| Action | Gesture |
|--------|---------|
| Start recording | Tap right Option key once |
| Stop recording | Tap right Option key again |

A macOS notification appears at each stage:
- **Recording…** — when recording starts
- **Processing…** — when processing begins
- **Transcription copied to clipboard ✓** — when done
- **Error: …** — if something goes wrong

The cleaned transcript is always saved to `data/clean-transcript/` even if you use the clipboard version.

---

## Troubleshooting

### No key events detected
→ Accessibility permission not granted. See [Grant Accessibility access](#grant-accessibility-access-required).

### whisper not found
→ Make sure `whisper` is on your `PATH`. The plist adds `/opt/homebrew/bin` and `/usr/local/bin`. If you installed whisper with pip into a non-standard location, add the path to the `EnvironmentVariables > PATH` entry in the generated plist at `~/Library/LaunchAgents/com.vibing.audio-recorder.plist`.

### ollama connection refused
→ Start ollama: `ollama serve` or install it as a service via `brew services start ollama`.

### First transcription is slow
→ Whisper downloads the `small` model (~244 MB) on first use. Subsequent runs are fast.

### Service keeps restarting
→ Check `recorder.error.log` for tracebacks. Common causes: missing dependency, mic not available, or accessibility permission not granted.

---

## File layout

```
vibing/
├── recorder.py                              # Main daemon
├── requirements.txt                         # Python deps
├── Makefile                                 # Install / management targets
├── com.vibing.audio-recorder.plist.template # LaunchAgent template
├── README.md
└── data/
    ├── raw-audio/          # Captured WAV files
    ├── normalized-audio/   # ffmpeg-normalized WAV files
    ├── raw-transcript/     # Raw whisper output
    └── clean-transcript/   # Ollama-cleaned transcripts
```
