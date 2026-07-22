# Uses uv (https://docs.astral.sh/uv) for dependency management — uv sync creates/updates .venv; run commands via uv run, no manual activation.
SHELL := /bin/bash

.PHONY: all install test run process clean lock help

all: install

## Create virtualenv and install Python dependencies
install:
	uv sync --dev
	@echo "✓ Install complete. Run 'make run' to start the recorder."

## Run unit tests
test: install
	uv run pytest tests/ -v
## Run the recorder in the foreground
run: install
	uv run python scripts/recorder.py
## Process existing audio files from recordings_dir (see config.json)
process: install
	uv run python scripts/process.py
## Update uv.lock
lock:
	uv lock
## Remove virtualenv and all captured data
clean:
	@echo "Removing virtualenv and data directories…"
	rm -rf .venv
	rm -f logs/recorder.log
	@echo "Done. Run 'make install' to reinstall."

## Show this help
help:
	@echo "install - create/update .venv and install dependencies"
	@echo "test    - run unit tests"
	@echo "run     - run the recorder in the foreground"
	@echo "process - process existing audio files"
	@echo "lock    - update uv.lock"
	@echo "clean   - remove virtualenv and captured data"
