#!/usr/bin/env python3
"""
Batch-process existing audio files through the vibing pipeline.

Reads audio files from config["recordings_dir"], runs each through
normalize → transcribe → clean, and writes results to the standard
output_dir subdirectories.
"""

import glob
import logging
import os
import subprocess
import sys

from recorder import (
    CLEAN_TRANSCRIPT_DIR,
    NORM_AUDIO_DIR,
    RAW_TRANSCRIPT_DIR,
    _load_config,
    _resolve_output_dir,
    clean_with_ollama,
    filename_from_ollama,
    normalize_audio,
    transcribe,
)

cfg = _load_config()

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "recorder.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = (
    "*.wav", "*.WAV",
    "*.mp3", "*.MP3",
    "*.m4a", "*.M4A",
    "*.flac", "*.FLAC",
    "*.ogg", "*.OGG",
    "*.aac", "*.AAC",
)


def find_audio_files(directory: str) -> list[str]:
    files: list[str] = []
    for pattern in AUDIO_EXTENSIONS:
        files.extend(glob.glob(os.path.join(directory, pattern)))
    return sorted(files)


def process_file(audio_path: str) -> None:
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    log.info("Processing: %s", audio_path)

    norm_path = os.path.join(NORM_AUDIO_DIR, stem + ".wav")
    normalize_audio(audio_path, norm_path)
    log.info("Normalized: %s", norm_path)

    transcript_path = transcribe(norm_path, RAW_TRANSCRIPT_DIR)
    with open(transcript_path) as f:
        raw_text = f.read().strip()
    log.info("Raw transcript (%d chars)", len(raw_text))

    if not raw_text:
        log.warning("Empty transcript, skipping: %s", audio_path)
        os.remove(norm_path)
        return

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

    os.remove(norm_path)


def main() -> None:
    for d in (NORM_AUDIO_DIR, RAW_TRANSCRIPT_DIR, CLEAN_TRANSCRIPT_DIR):
        os.makedirs(d, exist_ok=True)

    recordings_dir = _resolve_output_dir(cfg.get("recordings_dir", "~/Documents/voice-notes/raw-audio"))
    if not os.path.isdir(recordings_dir):
        log.error("recordings_dir not found: %s", recordings_dir)
        sys.exit(1)

    files = find_audio_files(recordings_dir)
    if not files:
        log.info("No audio files found in %s", recordings_dir)
        return

    log.info("Found %d file(s) in %s", len(files), recordings_dir)
    ok = failed = 0
    for path in files:
        try:
            process_file(path)
            ok += 1
        except subprocess.CalledProcessError as exc:
            log.error("ffmpeg error on %s: %s", path, (exc.stderr or b"").decode()[:120])
            failed += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Failed %s: %s", path, exc)
            failed += 1

    log.info("Done — %d succeeded, %d failed.", ok, failed)


if __name__ == "__main__":
    main()
