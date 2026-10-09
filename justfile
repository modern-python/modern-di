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

# CI lint (no autofix) — the same checks as `lint`.
lint-ci:
    uv run eof-fixer . --check
    uv run ruff format --check
    uv run ruff check --no-fix
    uv run ty check

adr_check_source := "https://raw.githubusercontent.com/modern-python/.github/main/tests/test_adr_citations.py"

# Tracks main on purpose: the shared check is unpinned.
adr-check:
    #!/usr/bin/env sh
    set -eu
    dir="$(mktemp -d .adr-check.XXXXXX)"
    trap 'rm -rf "$dir"' EXIT
    curl -fsSL "{{ adr_check_source }}" -o "$dir/test_adr_citations.py"
    uv run --no-sync pytest --rootdir=. --noconftest -o addopts= "$dir/test_adr_citations.py"

# Run pytest with NO coverage (targeted runs won't trip the gate). Passes args through.
test *args:
    uv run --no-sync pytest {{ args }}

# Run the thread_race tests only, selected by marker across the whole suite. Passes args through.
test-race *args:
    uv run --no-sync pytest -m thread_race {{ args }}

# The gated full run: 100% line and branch coverage of modern_di required. CI runs this.
test-ci:
    uv run --no-sync pytest --cov --cov-report term-missing --cov-report xml

# Run the guard-tier benchmark suite (zero-dep; pytest-benchmark). Excludes the
# comparative tier, whose deps live in benchmarks/comparative and are not in this env.
bench:
    uv run --no-sync pytest benchmarks/ --ignore=benchmarks/comparative --benchmark-only

# Comparative cross-framework benchmarks (isolated env: dishka, that-depends,
# dependency-injector, wireup + editable modern-di). First run resolves deps.
bench-compare:
    uv run --project benchmarks/comparative pytest benchmarks/comparative/ --benchmark-only

# Run the comparative tier N times and print the published markdown ratio table.
# This is what generates the table in docs/introduction/performance.md — never hand-assemble it.
bench-report runs="5":
    uv run --no-sync python benchmarks/report.py --runs {{ runs }}

# Build + publish to PyPI. Version comes from the git tag ($GITHUB_REF_NAME); no pyproject bump.
# Auth via PyPI Trusted Publishing (OIDC); uv publish auto-detects the CI id-token.
publish:
    rm -rf dist
    uv version $GITHUB_REF_NAME
    uv build
    uv publish

# Build the docs site, failing on broken links / nav warnings; CI runs this on every PR.
docs-build:
    uvx --with-requirements docs/requirements.txt mkdocs build --strict
