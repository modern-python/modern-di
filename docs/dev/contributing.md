# Contributing

This is an open source project, and we are open to new contributors.

## Getting started

1. Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/). modern-di supports
   Python 3.11 and later.
2. Clone the project:

    ```bash
    git clone https://github.com/modern-python/modern-di.git
    cd modern-di
    ```

3. Run `just install`. It runs `uv lock --upgrade`, then syncs every extra and the lint group, so
   you lint with the newest `ruff` and `ty`, as CI does. `uv.lock` is gitignored. Run it again in
   every new checkout or worktree before `just lint`.

## Running linters

`ruff` and `ty` do the static analysis. Run all checks with `just lint`, which also applies
`ruff`'s fixes and formatting.

## Running tests

Run all tests with `just test`. Run a subset with `just test <PATH> -k <NAME>`.

- `just test-ci` is the full run with coverage, and fails below 100% line and branch coverage of
  `modern_di`.
- `just test-race` runs only the thread-race tests. CI repeats them on free-threaded Python builds.
- `just bench` runs the guard-tier benchmarks, and `just bench-compare` the cross-framework ones.

## Working on the docs

The site is built from `docs/` with MkDocs. Before you open a pull request that touches it:

- `just test-docs` runs every Python block under `docs/` as a test, with Sybil. The framework
  pages under `docs/integrations/` are skipped there.
- `just test-docs-integrations` runs every page, the framework pages included, with each
  integration's latest release installed. It builds a throwaway virtualenv.
- `just docs-build` is the strict MkDocs build. Any warning fails it.

The writing rules are in `docs/agents/docs-style.md`.

## What CI runs

Every pull request runs `just lint-ci` and `just adr-check`, `just test-ci` and `just test-docs` on
Python 3.11 to 3.14 (3.15 as a pre-release), `just test-race --count=50` on the free-threaded
builds, `just test-docs-integrations`, `just docs-build`, and an offline link check of every
Markdown file.

## Submitting changes

1. Fork the repo and branch off `main`.
2. Make your change with tests, and keep 100% line and branch coverage of `modern_di`. The gate is
   `report.fail_under = 100` in `pyproject.toml`.
3. Run `just lint` and `just test` locally before pushing.
4. For a non-trivial change, the pull-request body is the spec. The template has Summary, Changes
   and Checklist sections.
5. Open a pull request upstream.
