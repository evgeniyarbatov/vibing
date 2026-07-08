SHELL := /bin/bash
VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip3

.PHONY: all setup test run process clean

all: setup

## Create virtualenv and install Python dependencies
setup: $(VENV_DIR)
	@echo "✓ Setup complete. Run 'make run' to start the recorder."

$(VENV_DIR): requirements.txt
	uv venv $(VENV_DIR)
	uv pip install -r requirements.txt --quiet

## Run unit tests
test: setup
	$(VENV_DIR)/bin/pytest tests/ -v

## Run the recorder in the foreground
run: setup
	$(PYTHON) scripts/recorder.py

## Process existing audio files from recordings_dir (see config.json)
process: setup
	$(PYTHON) scripts/process.py

## Remove virtualenv and all captured data
clean:
	@echo "Removing virtualenv and data directories…"
	rm -rf $(VENV_DIR)
	rm -f logs/recorder.log
	@echo "Done. Run 'make setup' to reinstall."
