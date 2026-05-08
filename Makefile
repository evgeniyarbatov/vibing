SHELL        := /bin/bash
PLIST_NAME   := com.vibing.audio-recorder
PLIST_DEST   := $(HOME)/Library/LaunchAgents/$(PLIST_NAME).plist
VENV_DIR     := .venv
PYTHON       := $(VENV_DIR)/bin/python3
PIP          := $(VENV_DIR)/bin/pip3

.PHONY: all setup test install uninstall start stop restart status logs run clean

all: setup

# ── Development ────────────────────────────────────────────────────────────────

## Create virtualenv and install Python dependencies
setup: $(VENV_DIR)
	@echo "✓ Setup complete. Run 'make install' to register the launchd service."

$(VENV_DIR): requirements.txt
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements.txt --quiet

## Run unit tests
test: setup
	$(VENV_DIR)/bin/pytest tests/ -v

## Run the recorder directly in the foreground (useful for debugging)
run: setup
	$(PYTHON) recorder.py

# ── Service management ─────────────────────────────────────────────────────────

## Install and start the launchd service (runs at login, auto-restarts on crash)
install: setup
	@echo "Installing launchd service…"
	@sed \
		-e "s|{{PROJECT_DIR}}|$(CURDIR)|g" \
		-e "s|{{PYTHON}}|$(CURDIR)/$(PYTHON)|g" \
		-e "s|{{HOME}}|$(HOME)|g" \
		$(PLIST_NAME).plist.template > $(PLIST_DEST)
	@# Unload first in case it was already loaded
	@launchctl unload $(PLIST_DEST) 2>/dev/null || true
	launchctl load $(PLIST_DEST)
	@echo ""
	@echo "✓ Service installed and running."
	@echo ""
	@echo "⚠  IMPORTANT: Grant Accessibility access so the daemon can read global key events."
	@echo "   System Settings → Privacy & Security → Accessibility"
	@echo "   Add: $(CURDIR)/$(PYTHON)  (or the Terminal app when running 'make run')"
	@echo ""
	@echo "   Run 'make logs' to follow the log."

## Stop and remove the launchd service
uninstall:
	@launchctl unload $(PLIST_DEST) 2>/dev/null && echo "Service stopped." || true
	@rm -f $(PLIST_DEST) && echo "Plist removed." || true

## Start the service (if already installed)
start:
	launchctl load $(PLIST_DEST)

## Stop the service
stop:
	launchctl unload $(PLIST_DEST)

## Restart the service
restart: stop start

## Show whether the service is running
status:
	@launchctl list | grep $(PLIST_NAME) \
		&& echo "Service is running." \
		|| echo "Service is NOT running."

## Follow the live log
logs:
	@tail -f recorder.log

# ── Cleanup ────────────────────────────────────────────────────────────────────

## Remove virtualenv and all captured data (keeps installed plist)
clean:
	@echo "Removing virtualenv and data directories…"
	rm -rf $(VENV_DIR)
	rm -f recorder.log recorder.error.log
	rm -rf data/
	@echo "Done. Run 'make setup' to reinstall."
