# Project Overview

## Project Type
This is a Python monorepo containing a dependency injection (DI) framework called `modern-di` and its integrations with popular web frameworks.

## Purpose
`modern-di` is a Python dependency injection framework that supports:
- Async and sync dependency resolution
- Scopes and granular context management
- Python 3.10+ support
- Fully typed and tested
- Integrations with `FastAPI`, `FastStream` and `LiteStar`

## Architecture
The project follows a monorepo structure with multiple packages:
1. `modern-di` - The core dependency injection framework
2. `modern-di-fastapi` - Integration with FastAPI
3. `modern-di-faststream` - Integration with FastStream
4. `modern-di-litestar` - Integration with LiteStar

Each package is independently versioned and published to PyPI.

## Technologies
- Python 3.10+
- uv for package management and virtual environments
- hatchling for building packages
- pytest for testing
- ruff for linting and formatting
- mypy for type checking
- mkdocs with Material theme for documentation
- GitHub Actions for CI/CD

# Building and Running

## Development Setup
1. Install dependencies:
   ```bash
   just install
   ```
   This command uses `uv` to install all dependencies for all packages.

## Development Commands
The project uses `just` (a command runner) for common development tasks:

### Linting and Formatting
```bash
just lint     # Format and fix code with ruff, then run mypy
just lint-ci  # Check formatting and types without making changes
```

### Testing
```bash
just test              # Run all tests
just test-core         # Run tests for the core package
just test-fastapi      # Run tests for FastAPI integration
just test-litestar     # Run tests for LiteStar integration
just test-faststream   # Run tests for FastStream integration
```

### Publishing
```bash
just publish <package-name>  # Build and publish a package to PyPI
```

## Manual Commands (without just)
If you don't have `just` installed, you can use uv directly:

### Install dependencies
```bash
uv lock --upgrade
uv sync --all-extras --all-packages --frozen
```

### Linting and formatting
```bash
uv run ruff format .
uv run ruff check . --fix
uv run mypy .
```

### Testing
```bash
uv run pytest                           # All tests
uv run --directory=packages/modern-di pytest                # Core tests
uv run --directory=packages/modern-di-fastapi pytest        # FastAPI tests
uv run --directory=packages/modern-di-litestar pytest       # LiteStar tests
uv run --directory=packages/modern-di-faststream pytest     # FastStream tests
```

# Development Conventions

## Code Style
- Line length: 120 characters
- Strict mypy type checking enabled
- Ruff is used for linting with most rules enabled except for a few explicitly ignored ones
- isort configuration for import sorting

## Testing Practices
- Both synchronous and asynchronous tests are supported
- Tests use pytest with coverage reporting
- Each package has its own test suite in a `tests_*` directory
- Tests follow a pattern of testing container behavior, provider resolution, and scope management

## Documentation
- Documentation is written in Markdown using MkDocs with Material theme
- Documentation is organized in a hierarchical structure covering quickstart, concepts, providers, integrations, testing, and development
- Code examples are included throughout the documentation

## Package Structure
- Each package follows the standard Python package structure
- Source code is in a directory named after the package (e.g., `modern_di`)
- Tests are in a separate directory (e.g., `tests_core`)
- Each package has its own `pyproject.toml` file for dependencies and metadata

## CI/CD
- GitHub Actions are used for continuous integration
- Separate workflows exist for linting, testing each package, and publishing
- Tests run on multiple Python versions (3.10 through 3.14)
- Publishing requires a PYPI_TOKEN secret

## Versioning
- Packages are independently versioned
- Version numbers follow semantic versioning
- Alpha releases are supported (as seen in the FastAPI integration dependency on `modern-di>=1.0.0alpha`)