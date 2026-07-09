# Uses uv (https://docs.astral.sh/uv) for dependency management — uv sync creates/updates .venv; run commands via uv run, no manual activation.
SHELL := /bin/bash

.PHONY: all setup test run process clean lock help

all: setup

## Create virtualenv and install Python dependencies
setup:
	uv sync --dev
	@echo "✓ Setup complete. Run 'make run' to start the recorder."

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
clean:
	@echo "Removing virtualenv and data directories…"
	rm -rf .venv
	rm -f logs/recorder.log
	@echo "Done. Run 'make setup' to reinstall."

## Show this help
help:
	@echo "setup   - create/update .venv and install dependencies"
	@echo "test    - run unit tests"
	@echo "run     - run the recorder in the foreground"
	@echo "process - process existing audio files"
	@echo "lock    - update uv.lock"
	@echo "clean   - remove virtualenv and captured data"
