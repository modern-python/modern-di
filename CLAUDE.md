# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di` is a **zero-dependency** Python dependency injection framework that wires up object graphs from type annotations, manages lifetimes via hierarchical scopes, and supports both sync and async finalizers. Framework integrations (aiohttp, FastAPI, FastStream, Litestar, Starlette, Typer) and the pytest integration (`modern-di-pytest`) live in **separate repositories** and are published as separate PyPI packages.

## Commands

This project uses `just` (task runner) and `uv` (package manager). The
[`Justfile`](Justfile) is the source of truth for recipes — run `just --list`
or read it for every recipe and its intent. The non-obvious essentials:

- `just test [args]` — pytest, **no coverage**; targeted runs won't trip the
  gate. Passes args through: `just test tests/providers/test_factory.py -k test_name`.
- `just test-ci` — the **gated** full run (100% line coverage); this is what CI runs.
- `just lint` (autofix) / `just lint-ci` (no autofix; also validates planning bundles).
- `just check-planning` validates planning bundles; `just index` prints the change listing.

## Architecture

> Quick orientation only. The authoritative, code-current account of each capability lives in [`architecture/`](architecture/) — one file per capability. **When a change alters a capability's behavior, update the matching `architecture/<capability>.md` in the same PR** — that promotion is what keeps `architecture/` true; code that changes without it silently rots the truth home.

- **Scope** — `IntEnum`, `APP=1 → SESSION=2 → REQUEST=3 → ACTION=4 → STEP=5`. A provider resolves only from a container of the same or deeper (higher-int) scope; otherwise a clear error is raised.
- **Container** — the central object. Root: `Container(scope=Scope.APP, groups=[MyGroup])`; children via `container.build_child_container(scope=Scope.REQUEST, context={...})`. Children share the parent's providers/overrides registries; cache/context are per-container. Pass `validate=True` (or call `container.validate()`) for cycle + transitive-scope checks.

Where the detail lives — read the matching capability file before changing behavior:

| File | Covers |
|---|---|
| [architecture/scopes.md](architecture/scopes.md) | `Scope` hierarchy + the resolution rule |
| [architecture/containers.md](architecture/containers.md) | `Container`, registries, child containers, lifecycle/finalizers |
| [architecture/providers.md](architecture/providers.md) | `Group`, `Factory`/caching, `ContextProvider`, `Alias` |
| [architecture/resolution.md](architecture/resolution.md) | how `resolve()` wires deps from type hints |
| [architecture/validation.md](architecture/validation.md) | `validate()` cycle + scope checks |
| [architecture/testing-and-overrides.md](architecture/testing-and-overrides.md) | overrides + the `modern-di-pytest` integration |

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

- Create a `Group` subclass with providers as class attributes → `Container(groups=[...])`
- `container.resolve_provider(provider)` (by reference) or `container.resolve(SomeType)` (by type)
- Overrides: `container.override(provider, mock_obj)` / `container.reset_override(provider)`
- Scope chains: `app_container.build_child_container(scope=Scope.REQUEST)`
- `asyncio_mode = "auto"` — async test functions work without extra markers
- The **`modern-di-pytest`** integration (a sibling repo/package, not a dependency here) → [architecture/testing-and-overrides.md](architecture/testing-and-overrides.md)

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
- Design principle: conservative feature set; **resolution** is sync-only (async resolution was removed in 2.x), though **finalizers** may still be sync or async (`close_sync`/`close_async`); no global state
- Docstrings: public API documents the contract; internal helpers get a
  one-line contract, plus at most 1–2 lines for a genuinely non-obvious
  constraint. Never narrate implementation or justify code to a reviewer —
  cross-file rationale lives in `architecture/`.
