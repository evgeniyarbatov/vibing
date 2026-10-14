# Uses uv (https://docs.astral.sh/uv) for dependency management — uv sync creates/updates .venv; run commands via uv run, no manual activation.
SHELL := /bin/bash

.DEFAULT_GOAL := help

.PHONY: all setup test run process lock help

all: setup

## Create virtualenv and install Python dependencies
setup:
	uv sync --dev
	@echo "✓ Install complete. Run 'make run' to start the recorder."

## Run unit tests
test: setup
	uv run pytest tests/ -v
## Run the recorder in the foreground
run: setup
	uv run python scripts/recorder.py
## Process existing audio files from recordings_dir (see config.json)
process: setup
	uv run python scripts/process.py
## Update uv.lock
lock:
	uv lock
## Remove virtualenv and all captured data
## Show this help
help:
	@echo "setup   - create/update .venv and install dependencies"
	@echo "test    - run unit tests"
	@echo "run     - run the recorder in the foreground"
	@echo "process - process existing audio files"
	@echo "lock    - update uv.lock"
