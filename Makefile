SHELL    := /bin/bash
VENV_DIR := .venv
PYTHON   := $(VENV_DIR)/bin/python3
PIP      := $(VENV_DIR)/bin/pip3

.PHONY: all setup test run logs clean

all: setup

## Create virtualenv and install Python dependencies
setup: $(VENV_DIR)
	@echo "✓ Setup complete. Run 'make run' to start the recorder."

$(VENV_DIR): requirements.txt
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements.txt --quiet

## Run unit tests
test: setup
	$(VENV_DIR)/bin/pytest tests/ -v

## Run the recorder in the foreground
run: setup
	$(PYTHON) scripts/recorder.py

## Follow the live log
logs:
	@tail -f logs/recorder.log

## Remove virtualenv and all captured data
clean:
	@echo "Removing virtualenv and data directories…"
	rm -rf $(VENV_DIR)
	rm -f logs/recorder.log logs/recorder.error.log
	rm -rf data/
	@echo "Done. Run 'make setup' to reinstall."
