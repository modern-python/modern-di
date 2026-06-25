default: install lint test

# Install/refresh deps: upgrade the lockfile, sync all extras + the lint group.
install:
    uv lock --upgrade
    uv sync --all-extras --frozen --group lint

# Autofix lint: eof-fixer, ruff format, ruff check --fix, ty type-check.
lint:
    uv run eof-fixer .
    uv run ruff format
    uv run ruff check --fix
    uv run ty check

# CI lint (no autofix) — same checks as `lint` plus the planning-bundle validator.
lint-ci:
    uv run eof-fixer . --check
    uv run ruff format --check
    uv run ruff check --no-fix
    uv run ty check
    uv run python planning/index.py --check

# Run pytest with NO coverage (targeted runs won't trip the gate). Passes args through.
test *args:
    uv run --no-sync pytest {{ args }}

# The gated full run: 100% line coverage required. CI runs this.
test-ci:
    uv run --no-sync pytest --cov=. --cov-report term-missing --cov-report xml --cov-fail-under=100

# Branch-coverage run (diagnostic; line coverage is the enforced gate, not branch).
test-branch:
    uv run --no-sync pytest --cov=. --cov-branch --cov-fail-under=100

# Run the benchmark suite only (pytest-benchmark).
bench:
    uv run --no-sync pytest benchmarks/ --benchmark-only

# Build + publish to PyPI. Version comes from the git tag ($GITHUB_REF_NAME); no pyproject bump.
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
