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

# Run the python code blocks in docs/ as tests (Sybil, wired in conftest.py). Kept out of
# test-ci so doc examples never count toward library coverage. Passes args through.
test-docs *args:
    uv run --no-sync pytest docs {{ args }}

# Packages the integration pages import that no modern-di-<page> package depends on.
docs_integration_extras := "faststream[kafka,nats] aiogram-dialog"

# Run the framework pages under docs/integrations/ against the latest modern-di-<page> release for
# every page, with modern-di pinned to this checkout. Builds a throwaway venv, so uv.lock is untouched.
test-docs-integrations *args:
    #!/usr/bin/env sh
    set -eu
    dir="$(mktemp -d)"
    trap 'rm -rf "$dir"' EXIT
    echo "modern-di @ file://$PWD" > "$dir/overrides.txt"
    packages="$(ls docs/integrations/*.md | sed -e 's#.*/##' -e 's#[.]md$##' | grep -vx writing-integrations | sed 's#^#modern-di-#')"
    uv venv --quiet "$dir/venv"
    uv pip install --quiet --python "$dir/venv" --overrides "$dir/overrides.txt" \
        --editable . pytest pytest-asyncio sybil {{ docs_integration_extras }} $packages
    "$dir/venv/bin/python" -m pytest docs/integrations --docs-integrations {{ args }}

# Run each integration's own test suite and ty check against this checkout: clone its main, run its
# `just install`, then swap in this modern-di. Defaults to every page under docs/integrations/;
# pass page names (`just test-integrations grpc flask`) to pick some. Run before tagging a release.
test-integrations *names:
    #!/usr/bin/env sh
    set -u
    root="$PWD"
    dir="$(mktemp -d)"
    trap 'rm -rf "$dir"' EXIT
    echo "modern-di @ file://$root" > "$dir/overrides.txt"
    names="{{ names }}"
    [ -n "$names" ] || names="$(ls docs/integrations/*.md | sed -e 's#.*/##' -e 's#[.]md$##' | grep -vx writing-integrations)"
    failed=""
    for name in $names; do
        repo="modern-di-$name"
        log="$dir/$repo.log"
        if git clone --quiet --depth 1 "https://github.com/modern-python/$repo.git" "$dir/$repo" >"$log" 2>&1 \
            && (cd "$dir/$repo" && just install \
                && uv pip install --python .venv --overrides "$dir/overrides.txt" --editable "$root" \
                && uv run --no-sync pytest -p no:cacheprovider \
                && uv run --no-sync ty check) >>"$log" 2>&1; then
            echo "ok   $repo"
        else
            echo "FAIL $repo"
            tail -n 30 "$log" | sed 's#^#    #'
            failed="$failed $repo"
        fi
    done
    [ -z "$failed" ] || { echo "failed:$failed"; exit 1; }

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
