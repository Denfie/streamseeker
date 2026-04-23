.PHONY: run help about download retry version install test clean

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
