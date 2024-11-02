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

test *args:
    uv run pytest {{ env_var_or_default("TESTS_PATH", ".") }} {{ args }}

test-all *args:
    uv run pytest {{ args }}

publish package:
    rm -rf dist
    uv build --package {{package}}
    uv publish --token $PYPI_TOKEN
