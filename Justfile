default: install lint test

install:
    uv lock --upgrade
    uv sync --all-extras --all-packages --frozen

lint path=".":
    uv run ruff format {{ path }}
    uv run ruff check {{ path }} --fix
    uv run mypy {{ path }}

lint-ci path=".":
    uv run ruff format {{ path }} --check
    uv run ruff check {{ path }} --no-fix
    uv run mypy {{ path }}

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
