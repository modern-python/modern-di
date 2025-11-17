default: install lint test

install:
    uv lock --upgrade
    uv sync --all-extras --all-packages --frozen

install-ci package:
    uv lock --upgrade
    uv sync --all-extras --package {{ package }} --frozen

lint:
    uv run ruff format .
    uv run ruff check . --fix
    uv run mypy .

lint-ci:
    uv run ruff format . --check
    uv run ruff check . --no-fix
    uv run mypy .

test *args:
    uv run pytest {{ args }}

test-core *args:
    uv run --directory=packages/modern-di pytest {{ args }}

test-fastapi *args:
    uv run --directory=packages/modern-di-fastapi pytest {{ args }}

test-litestar *args:
    uv run --directory=packages/modern-di-litestar pytest {{ args }}

test-faststream *args:
    uv run --directory=packages/modern-di-faststream pytest {{ args }}

publish package:
    rm -rf dist
    uv version $GITHUB_REF_NAME
    uv build --package {{ package }}
    uv publish --token $PYPI_TOKEN
