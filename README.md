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

# Start the server
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
| `output_dir` | `~/Documents/vibing` | Root for all four output subdirectories. Relative paths are resolved from the project root; absolute paths are used as-is |

---

## Quick start

```bash
make run
```

Runs the recorder in your terminal. Log output appears in real time and is also written to `logs/recorder.log`. Press **right Option** to start/stop recording. Stop with `Ctrl-C`.

### Grant Accessibility access (required)

`pynput` needs the Accessibility permission to read global keyboard events.

1. Open **System Settings → Privacy & Security → Accessibility**.
2. Click **+** and add `.venv/bin/python3` inside this project directory.
   - If running from Terminal, add **Terminal** (or iTerm2) instead.

Without this step the key listener silently does nothing.

### Makefile targets

| Command | What it does |
|---------|-------------|
| `make run` | Start the recorder in the foreground |
| `make logs` | Follow the live log (`logs/recorder.log`) |
| `make test` | Run the test suite |
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
→ Make sure `whisper` is on your `PATH`. If you installed it into a non-standard location, add it to your shell's `PATH` before running `make run`.

### ollama connection refused
→ Start ollama: `ollama serve` or install it as a service via `brew services start ollama`.

### First transcription is slow
→ Whisper downloads the `small` model (~244 MB) on first use. Subsequent runs are fast.

---

## File layout

```
vibing/
├── scripts/
│   └── recorder.py       # Main script
├── logs/
│   └── recorder.log      # Written at runtime (gitignored)
├── config.json           # User configuration
├── requirements.txt      # Python deps
├── Makefile
└── README.md
```
