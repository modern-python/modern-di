# Contributing
This is an open source project, and we are open to new contributors.

## Getting started
1. Make sure that you have [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/) installed.
2. Clone project:
```
git clone git@github.com:modern-python/modern-di.git   # or: git clone https://github.com/modern-python/modern-di.git
cd modern-di
```
3. Install dependencies by running `just install`

## Running linters
`Ruff` and `ty` are used for static analysis.

Run all checks by command `just lint`

## Running tests
Run all tests by command `just test`. Run a subset with `just test <PATH> -k <NAME>`.

CI runs the coverage-enforcing recipe `just test-ci` along with `just lint-ci`.

## Submitting changes
1. Fork the repo and branch off `main`.
2. Make your change with tests; keep **100% line coverage** (CI runs `just test-ci` with `--cov-fail-under=100`).
3. Run `just lint` and `just test` locally before pushing (CI runs the non-fixing variants `just lint-ci` / `just test-ci`).
4. For non-trivial changes, see the [planning convention](https://github.com/modern-python/modern-di/blob/main/planning/README.md).
5. Open a pull request upstream.
