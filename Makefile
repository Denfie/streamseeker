.PHONY: run help about download retry version install install-dev test clean icons install-extension install-desktop-icon uninstall daemon-start daemon-stop

# Use the Python from the active virtualenv (if any) otherwise system python3.
PY ?= python3
CLI = $(PY) -m streamseeker

## Application commands
run:
	$(CLI)

help:
	$(CLI) list

about:
	$(CLI) about

version:
	$(CLI) --version

retry:
	$(CLI) retry

## Development commands
install:
	$(PY) -m pip install -e .

install-dev:
	$(PY) -m pip install -e '.[dev]'

test:
	$(PY) -m pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true

## Distribution (Paket H)
icons:
	$(PY) scripts/render_icons.py

install-extension:
	$(CLI) install-extension

install-desktop-icon:
	$(CLI) install-desktop-icon

uninstall:
	$(CLI) uninstall

## Daemon
daemon-start:
	$(CLI) daemon start

daemon-stop:
	$(CLI) daemon stop
