.PHONY: run help about download retry version install test clean icons install-extension install-desktop-icon uninstall daemon-start daemon-stop

CLI = poetry run python -m streamseeker

## Application commands
run:
	$(CLI)

help:
	$(CLI) list

about:
	$(CLI) about

download:
	$(CLI) download

retry:
	$(CLI) retry

version:
	$(CLI) --version

## Development commands
install:
	poetry install

test:
	poetry run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true

## Distribution (Paket H)
icons:
	poetry run python scripts/render_icons.py

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
