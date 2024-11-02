default: install lint test

install:
    uv lock --upgrade
    uv sync --all-extras --all-packages --frozen

lint:
    uv run ruff format .
    uv run ruff check . --fix
    uv run mypy .

lint-ci:
    uv run ruff format . --check
    uv run ruff check . --no-fix
    uv run mypy .

_test *args:
    uv run pytest $TEST_PATH --cov=$TEST_PATH --cov-report term-missing {{ args }}

test *args:
    @TEST_PATH=. just _test {{ args }}

test-core *args:
    @TEST_PATH=packages/modern-di just _test {{ args }}

test-fastapi *args:
    @TEST_PATH=packages/modern-di-fastapi just _test {{ args }}

publish package:
    rm -rf dist
    uv build --package {{package}}
    uv publish --token $PYPI_TOKEN
