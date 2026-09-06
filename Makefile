.PHONY: check dist install

check:
	uv run ruff check src tests tools
	uv run ruff format --check src tests tools
	uv run mypy
	uv run pytest -q

dist:
	uv build --no-build-isolation
	uv run python tools/homebrew.py bundle

install:
	./install.sh
