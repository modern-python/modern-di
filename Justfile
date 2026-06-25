default: install lint test

install:
    uv lock --upgrade
    uv sync --all-extras --frozen --group lint

lint:
    uv run eof-fixer .
    uv run ruff format
    uv run ruff check --fix
    uv run ty check

lint-ci:
    uv run eof-fixer . --check
    uv run ruff format --check
    uv run ruff check --no-fix
    uv run ty check

test *args:
    uv run --no-sync pytest {{ args }}

test-ci:
    uv run --no-sync pytest --cov=. --cov-report term-missing --cov-report xml --cov-fail-under=100

test-branch:
    uv run --no-sync pytest --cov=. --cov-branch --cov-fail-under=100

bench:
    uv run --no-sync pytest benchmarks/ --benchmark-only

publish:
    rm -rf dist
    uv version $GITHUB_REF_NAME
    uv build
    uv publish --token $PYPI_TOKEN

# Build the docs site, failing on broken links / nav warnings; CI runs this on every PR.
docs-build:
    uvx --with-requirements docs/requirements.txt mkdocs build --strict

# Print the planning change index (grouped by status) to stdout.
index:
    uv run python planning/index.py

# Validate planning bundles + decisions (frontmatter, lanes, spec links); CI runs this.
check-planning:
    uv run python planning/index.py --check
