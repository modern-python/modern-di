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
    uv run python planning/links.py

# Check every relative Markdown link and heading anchor. `mkdocs --strict` only sees
# docs/; architecture/ and planning/ live outside docs_dir and are read on GitHub.
check-links:
    uv run python planning/links.py

# Run pytest with NO coverage (targeted runs won't trip the gate). Passes args through.
test *args:
    uv run --no-sync pytest {{ args }}

# The gated full run: 100% line coverage required. CI runs this.
test-ci:
    uv run --no-sync pytest --cov=. --cov-report term-missing --cov-report xml --cov-fail-under=100

# Branch-coverage run (diagnostic; line coverage is the enforced gate, not branch).
test-branch:
    uv run --no-sync pytest --cov=. --cov-branch --cov-fail-under=100

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

# Print the planning change index (grouped by status) to stdout.
index:
    uv run python planning/index.py

# Validate planning bundles + decisions (frontmatter, lanes, spec links); CI runs this.
check-planning:
    uv run python planning/index.py --check
