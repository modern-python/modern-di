# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di` is a **zero-dependency** Python dependency injection framework that wires up object graphs from type annotations, manages lifetimes via hierarchical scopes, and supports both sync and async finalizers. Framework integrations (FastAPI, FastStream, LiteStar, Typer) and the pytest integration (`modern-di-pytest`) live in **separate repositories** and are published as separate PyPI packages.

## Commands

This project uses `just` (task runner) and `uv` (package manager).

```bash
just install      # uv lock --upgrade && uv sync --all-extras --frozen --group lint
just lint         # eof-fixer + ruff format + ruff check --fix + ty check
just lint-ci      # same checks without auto-fixing (used in CI)
just test         # uv run pytest (with coverage by default)
just test-branch  # pytest with branch coverage
```

`just test` passes extra args to pytest:
```bash
just test tests/providers/test_factory.py
just test tests/providers/test_factory.py -k test_name
```

Without `just`:
```bash
uv run ruff format . && uv run ruff check . --fix && uv run ty check
uv run pytest
```

## Architecture

> Quick orientation. The authoritative, code-current account of each capability lives in [`architecture/`](architecture/).

### Scope hierarchy

`Scope` is an `IntEnum` with five levels: `APP=1 → SESSION=2 → REQUEST=3 → ACTION=4 → STEP=5`. Providers are bound to a scope; a provider can only be resolved from a container of the same or deeper (higher int) scope. Trying to resolve a REQUEST-scoped provider from an APP container raises a clear error.

### Container tree

`Container` is the central object. A root container is created with `Container(scope=Scope.APP, groups=[MyGroup])`. Child containers are created via `container.build_child_container(scope=Scope.REQUEST, context={...})`. Child containers share the parent's `providers_registry` and `overrides_registry` but have their own `cache_registry` and `context_registry`.

Pass `validate=True` to check the provider graph at container creation time — cycle detection plus transitive scope validation through aliases (via `effective_scope`); zero cost when disabled. Can also be called explicitly via `container.validate()`.

### Group and Provider declaration

`Group` is a namespace class (cannot be instantiated) used to declare providers as class-level attributes:

```python
class MyGroup(Group):
    my_service = providers.Factory(scope=Scope.APP, creator=MyService)
```

`Factory` parses the `creator`'s `__init__` type hints at declaration time via `types_parser.parse_creator()`. During resolution it looks up each parameter type in `providers_registry` and recursively resolves dependencies. There is no separate `Singleton` class — singleton behavior is `Factory(cache_settings=CacheSettings())`. Pass `kwargs={}` to supply static arguments that bypass type-based resolution. Pass `skip_creator_parsing=True` for callables whose signatures cannot be introspected.

`ContextProvider` is for runtime values injected at container creation time (e.g. a request object). `container_provider` is an auto-registered singleton that resolves to the `Container` itself.

### Resolution flow

1. `container.resolve(SomeType)` → looks up type in `providers_registry` → calls `resolve_provider(provider)`
2. `resolve_provider` checks `overrides_registry` first (returns override immediately if found)
3. Finds the container at the correct scope via `find_container(scope)`, an O(1) lookup in the precomputed `scope_map`
4. Checks `cache_registry`; if cached, returns immediately
5. Compiles kwargs: for each parsed parameter, finds a matching provider by type and resolves it recursively
6. Calls the creator, stores result in cache if `cache_settings` configured

### Registries

| Registry | Shared? | Purpose |
|---|---|---|
| `ProvidersRegistry` | Shared across all containers | type → provider mapping |
| `CacheRegistry` | Per-container | provider_id → cached instance |
| `ContextRegistry` | Per-container | type → runtime context object |
| `OverridesRegistry` | Shared across all containers | provider_id → override object (for testing) |

### Key files

- `modern_di/container.py` — Container class, the main entry point
- `modern_di/providers/factory.py` — Factory and CacheSettings (singleton pattern via caching + optional finalizer)
- `modern_di/providers/context_provider.py` — ContextProvider for runtime-injected values
- `modern_di/providers/container_provider.py` — auto-registered provider that resolves to the Container itself
- `modern_di/types_parser.py` — Signature introspection engine (parses type hints for DI wiring)
- `modern_di/suggester.py` — `close_matches`, the shared difflib fuzzy-match used by registry type suggestions and factory kwarg "did you mean"
- `modern_di/scope.py` — Scope enum
- `modern_di/group.py` — Group base class for provider namespaces
- `modern_di/exceptions.py` — exception class hierarchy (`ModernDIError` → `ContainerError`/`ResolutionError`/`RegistrationError` subclasses); each error message is an inline f-string in the class that raises it

### Testing patterns

- Create a `Group` subclass with providers as class attributes, pass to `Container(groups=[...])`
- Use `container.resolve_provider(provider)` (by reference) or `container.resolve(SomeType)` (by type)
- For overrides: `container.override(provider, mock_obj)` / `container.reset_override(provider)`
- For scope chain tests: `app_container.build_child_container(scope=Scope.REQUEST)`
- `asyncio_mode = "auto"` in pytest config — async test functions work without extra markers
- Downstream projects can install **`modern-di-pytest`** to expose DI dependencies as pytest fixtures. It ships two callables: `modern_di_fixture(type_or_provider)` for single fixtures and `expose(*groups)` to bulk-generate one fixture per provider across one or more `Group` subclasses (duplicate attribute names raise `ValueError`). The package itself does **not** depend on `modern-di-pytest`; the integration lives in a sibling repository (`modern-python/modern-di-pytest`).

## Workflow

Planning uses a portable two-axis convention — `architecture/` (repo root) is
the living **truth home** and promotion target; `planning/changes/` holds the
per-change bundles. **Start at the
[Quick path](planning/README.md#quick-path-start-here)** in
`planning/README.md` to choose a lane, create a bundle, and ship — that file
is the authoritative spec. Run `just check-planning` to validate bundles and
`just index` to print the change listing. The `## Architecture` section above
is quick orientation; `architecture/` holds the authoritative account.

- **Cutting a release (maintainers)** is tag-driven via
  [`.github/workflows/release.yml`](.github/workflows/release.yml): write the
  notes at `planning/releases/<version>.md` (used verbatim as the GitHub Release
  body), then push a bare semver tag off green `main` —
  `git tag 2.19.2 && git push origin 2.19.2`. The workflow runs `just publish`
  (the tag sets the version via `uv version`; no `pyproject.toml` bump) to PyPI,
  then creates the GitHub Release — PyPI first, so a failed publish creates no
  Release. Pre-releases use the PEP 440 form (`2.0.0rc1`, not `2.0.0-alpha.5`).
  PyPI is irreversible; there is no CI gate (a tag is the commitment point).

## Code Style

- Line length: 120 characters
- `ruff` with `select = ["ALL"]` and minimal ignores; `ty` for type checking
- Coverage excludes `TYPE_CHECKING` blocks
- Design principle: conservative feature set; resolution is sync-only (async was removed in 2.x); no global state
