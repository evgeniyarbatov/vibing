#!/usr/bin/env python3
"""
Audio recorder daemon — configurable hotkey toggles recording.

Pipeline: record → ffmpeg loudnorm → whisper small → ollama → clipboard
"""

import datetime
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time

import numpy as np
import requests
import scipy.io.wavfile as wavfile
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard

# ---------------------------------------------------------------------------
# Base directory & config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

_CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
_DEFAULTS: dict = {
    "whisper_model": "small",
    "ollama_model": "mistral-nemo",
    "ollama_prompt": (
        "Clean up this voice transcription. Fix punctuation and capitalization. "
        "Remove filler words (um, uh, like, you know, so). Do not change the meaning, "
        "add information, or summarize. Return only the cleaned text with no preamble "
        "or explanation.\n\nTranscription:\n{transcription}"
    ),
    "ollama_filename_prompt": (
        "Give a short, descriptive filename for this transcript. "
        "Use lowercase with underscores, no extension, max 5 words. "
        "Reply with ONLY the filename, nothing else.\n\nTranscript:\n{transcript}"
    ),
    "output_dir": "~/Documents/vibing",
    "hotkey": "alt_r",
}


def _load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        return _DEFAULTS.copy()
    with open(_CONFIG_PATH) as f:
        user = json.load(f)
    return {**_DEFAULTS, **user}


def _resolve_output_dir(raw: str) -> str:
    """Expand ~ and resolve relative paths against PROJECT_DIR."""
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        return os.path.join(PROJECT_DIR, expanded)
    return expanded


def _parse_hotkey(name: str) -> keyboard.Key:
    """Map a pynput Key name string to a Key enum value."""
    try:
        return keyboard.Key[name]
    except KeyError:
        raise ValueError(
            f"Unknown hotkey '{name}'. "
            "Use a pynput Key name, e.g. 'alt_r', 'alt_l', 'cmd', 'f13'."
        )


cfg = _load_config()

DATA_DIR = _resolve_output_dir(cfg["output_dir"])
RAW_AUDIO_DIR = os.path.join(DATA_DIR, "raw-audio")
NORM_AUDIO_DIR = os.path.join(DATA_DIR, "normalized-audio")
RAW_TRANSCRIPT_DIR = os.path.join(DATA_DIR, "raw-transcript")
CLEAN_TRANSCRIPT_DIR = os.path.join(DATA_DIR, "clean-transcript")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = os.path.join(PROJECT_DIR, "logs", "recorder.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed config
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16_000       # Hz — whisper works best at 16 kHz
CHANNELS = 1
BLOCK_SIZE = 1024
MIN_DURATION_SEC = 0.5

OLLAMA_URL = "http://localhost:11434/api/generate"

_MAX_RETRIES = 3
_CHUNK_WORDS = 300

_whisper_model: WhisperModel | None = None


def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(cfg["whisper_model"], device="auto", compute_type="int8")
    return _whisper_model

# ---------------------------------------------------------------------------
# State (GIL makes bool/list.append atomic enough for our use)
# ---------------------------------------------------------------------------
is_recording = False
audio_buffer: list[np.ndarray] = []

# ---------------------------------------------------------------------------
# macOS helpers
# ---------------------------------------------------------------------------

def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def normalize_audio(input_path: str, output_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-af", "loudnorm", output_path],
        capture_output=True,
        check=True,
    )


def transcribe(audio_path: str, output_dir: str) -> str:
    model = _get_whisper_model()
    segments, _ = model.transcribe(audio_path)
    text = " ".join(seg.text.strip() for seg in segments)
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    out_path = os.path.join(output_dir, stem + ".txt")
    with open(out_path, "w") as f:
        f.write(text)
    return out_path


def _ollama_post(payload: dict, timeout: int) -> dict:
    """POST to Ollama with exponential-backoff retries on timeout/connection errors."""
    delay = 1
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as exc:
            last_exc = exc
            log.warning(
                "Ollama timeout (attempt %d/%d), retrying in %ds…",
                attempt, _MAX_RETRIES, delay,
            )
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            log.warning(
                "Ollama connection error (attempt %d/%d), retrying in %ds…",
                attempt, _MAX_RETRIES, delay,
            )
        if attempt < _MAX_RETRIES:
            time.sleep(delay)
            delay *= 2
    raise last_exc


def _chunk_text(text: str, max_words: int) -> list[str]:
    """Split text into chunks of at most max_words, breaking on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for sent in sentences:
        words = len(sent.split())
        if count + words > max_words and current:
            chunks.append(" ".join(current))
            current, count = [sent], words
        else:
            current.append(sent)
            count += words
    if current:
        chunks.append(" ".join(current))
    return chunks


def clean_with_ollama(raw_text: str) -> str:
    words = raw_text.split()
    chunks = _chunk_text(raw_text, _CHUNK_WORDS) if len(words) > _CHUNK_WORDS else [raw_text]
    if len(chunks) > 1:
        log.info("Cleaning in %d chunks (%d words total).", len(chunks), len(words))
    cleaned: list[str] = []
    for chunk in chunks:
        prompt = cfg["ollama_prompt"].format(transcription=chunk)
        result = _ollama_post(
            {"model": cfg["ollama_model"], "prompt": prompt, "stream": False},
            timeout=120,
        )
        cleaned.append(result["response"].strip())
    return " ".join(cleaned)


def filename_from_ollama(clean_text: str) -> str:
    # Truncate to keep the filename prompt fast regardless of transcript length
    prompt = cfg["ollama_filename_prompt"].format(transcript=clean_text[:500])
    result = _ollama_post(
        {"model": cfg["ollama_model"], "prompt": prompt, "stream": False},
        timeout=60,
    )
    raw = result["response"].strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return slug or "transcript"


# ---------------------------------------------------------------------------
# Processing thread
# ---------------------------------------------------------------------------

def process_recording(timestamp: str, frames: list[np.ndarray]) -> None:
    try:
        log.info("Processing started.")

        audio_data = np.concatenate(frames, axis=0)
        duration = len(audio_data) / SAMPLE_RATE
        if duration < MIN_DURATION_SEC:
            log.warning("Recording too short (%.2fs), skipping.", duration)
            return

        # 1. Save raw audio
        raw_path = os.path.join(RAW_AUDIO_DIR, f"{timestamp}.wav")
        wavfile.write(raw_path, SAMPLE_RATE, audio_data)
        log.info("Raw audio: %s (%.1fs)", raw_path, duration)

        # 2. Normalize
        norm_path = os.path.join(NORM_AUDIO_DIR, f"{timestamp}.wav")
        normalize_audio(raw_path, norm_path)
        log.info("Normalized: %s", norm_path)

        # 3. Transcribe
        transcript_path = transcribe(norm_path, RAW_TRANSCRIPT_DIR)
        with open(transcript_path) as f:
            raw_text = f.read().strip()
        log.info("Raw transcript (%d chars)", len(raw_text))

        if not raw_text:
            return

        # 4. Clean up
        clean_text = clean_with_ollama(raw_text)
        slug = filename_from_ollama(clean_text)
        clean_path = os.path.join(CLEAN_TRANSCRIPT_DIR, f"{slug}.txt")
        counter = 1
        while os.path.exists(clean_path):
            clean_path = os.path.join(CLEAN_TRANSCRIPT_DIR, f"{slug}_{counter}.txt")
            counter += 1
        with open(clean_path, "w") as f:
            f.write(clean_text)
        log.info("Clean transcript: %s", clean_path)

        # 5. Clipboard
        copy_to_clipboard(clean_text)

        # 6. Clean up audio files now that transcript is safely written
        for path in (raw_path, norm_path):
            try:
                os.remove(path)
            except OSError as exc:
                log.warning("Could not remove audio file %s: %s", path, exc)

        log.info("Done.")

    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode()[:120]
        log.error("Subprocess error: %s", stderr)
    except Exception as exc:  # noqa: BLE001
        log.error("Processing failed: %s", exc)


# ---------------------------------------------------------------------------
# Recording toggle
# ---------------------------------------------------------------------------

def toggle_recording() -> None:
    global is_recording, audio_buffer

    if not is_recording:
        audio_buffer = []
        is_recording = True
        log.info("Recording started.")
    else:
        is_recording = False
        frames = audio_buffer[:]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log.info("Recording stopped.")
        threading.Thread(
            target=process_recording,
            args=(timestamp, frames),
            daemon=True,
        ).start()


# ---------------------------------------------------------------------------
# Audio callback (runs on sounddevice thread)
# ---------------------------------------------------------------------------

def audio_callback(
    indata: np.ndarray, frames: int, time_info: object, status: object
) -> None:
    if status:
        log.debug("Audio status: %s", status)
    if is_recording:
        audio_buffer.append(indata.copy())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for _d in [RAW_AUDIO_DIR, NORM_AUDIO_DIR, RAW_TRANSCRIPT_DIR, CLEAN_TRANSCRIPT_DIR]:
        os.makedirs(_d, exist_ok=True)

    hotkey = _parse_hotkey(cfg["hotkey"])
    log.info(
        "Vibing ready — model=%s hotkey=%s output_dir=%s",
        cfg["ollama_model"],
        cfg["hotkey"],
        DATA_DIR,
    )
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=audio_callback,
        blocksize=BLOCK_SIZE,
    )
    stream.start()

    # Track whether another key was pressed while the hotkey was held,
    # to avoid triggering on hotkey+<something> combos.
    other_pressed = [False]

    def on_press(key: object) -> None:
        if key != hotkey:
            other_pressed[0] = True

    def on_release(key: object) -> None:
        if key == hotkey:
            if not other_pressed[0]:
                toggle_recording()
            other_pressed[0] = False

    try:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        log.info("Vibing stopped.")


if __name__ == "__main__":
    main()
