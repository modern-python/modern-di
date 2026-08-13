# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di` is a **zero-dependency** Python dependency injection framework that wires up object graphs from type annotations, manages lifetimes via hierarchical scopes, and supports both sync and async finalizers. Framework integrations (aiohttp, FastAPI, FastStream, Litestar, Starlette, Typer, Flask, gRPC, Celery, arq, taskiq, aiogram) and the pytest integration (`modern-di-pytest`) live in **separate repositories** and are published as separate PyPI packages.

## Commands

This project uses `just` (task runner) and `uv` (package manager). The
[`Justfile`](Justfile) is the source of truth for recipes — run `just --list`
or read it for every recipe and its intent. The non-obvious essentials:

- `just test [args]` — pytest, **no coverage**; targeted runs won't trip the
  gate. Passes args through: `just test tests/providers/test_factory.py -k <substring>`.
- `just test-ci` — the **gated** full run (100% line coverage); this is what CI runs.
- `just lint` (autofix) / `just lint-ci` (no autofix; also validates planning bundles).
- `just check-planning` validates `planning/deferred/` + `planning/decisions/` frontmatter; `just index` prints that listing.

## Architecture

- **Scope** — `IntEnum`, `APP=1 → SESSION=2 → REQUEST=3 → ACTION=4 → STEP=5`. A provider resolves only from a container of the same or deeper (higher-int) scope; otherwise a clear error is raised.
- **Container** — the central object. Root: `Container(scope=Scope.APP, groups=[MyGroup])`; children via `container.build_child_container(scope=Scope.REQUEST, context={...})`. Children share the parent's providers/overrides registries; cache/context are per-container. Pass `validate=True` (or call `container.validate()`) for cycle + transitive-scope checks.

There is no separate capability-page home for behavior detail — it lives in the code and its
`INVARIANT:`-marked tests. Before writing prose about a capability, run the admission check in
[`planning/README.md`](planning/README.md#where-a-fact-goes).

### Key files

Every module under `modern_di/` except the package `__init__.py` re-exports. If
you add a module, add it here.

- `modern_di/container.py` — Container class, the main entry point
- `modern_di/resolver_compiler.py` — the **single resolve path**: one flat closure compiled per provider, memoized on the registry. Each resolver front-guards its own override, navigates its scope once, and inlines the kwargs build and creator call to hold the per-node frame budget at 1 — the rationale lives in `test_resolve_costs_exactly_one_resolver_frame_per_node`, so **do not extract a helper from these closures**. A new provider type must add a branch here or `compile_resolver` raises
- `modern_di/wiring.py` — `WiringPlan`: partitions a creator's parsed parameters into provider / static / context buckets plus `unwireable`. A pure function of its inputs (no cache, scope, or live context), so it runs outside the container lock and is exercisable without a Container
- `modern_di/providers/factory.py` — Factory and CacheSettings (singleton pattern via caching + optional finalizer)
- `modern_di/providers/context_provider.py` — ContextProvider for runtime-injected values
- `modern_di/providers/container_provider.py` — auto-registered provider that resolves to the Container itself
- `modern_di/providers/alias.py` — Alias: re-exports a registered type under another name; transparent to scope via the `redirect_target` hook
- `modern_di/providers/abstract.py` — `AbstractProvider`, the base every provider type extends, and the `provider_id` counter that keys every registry and memo
- `modern_di/types.py` — the `UNSET` sentinel (`UnsetType`) that separates "not passed" from "explicitly `None`", plus the shared TypeVars. Load-bearing on the resolve path: it is the miss marker for both the override lookup and the cache slot
- `modern_di/types_parser.py` — Signature introspection engine (parses type hints for DI wiring)
- `modern_di/dependency_graph.py` — the one static graph walk (`DependencyGraph.walk`), consumed by `validate()` and the runtime cycle guard. Explicit-stack, never recursive: a caller runs it inside a `RecursionError` handler near CPython's stack limit. It walks `WiringPlan.edges`, so what `validate()` traverses is exactly what `resolve()` follows
- `modern_di/registries/` — the four registries: `providers_registry` (type → provider, plus the shared plan/resolver memos) and `overrides_registry` are shared tree-wide; `cache_registry` and `context_registry` are per-container
- `modern_di/integrations.py` — the integration kit: Layer 1 (`bind`, `classify_connection`) derives a child container's scope/context from `ContextProvider`s; Layer 2 (`Marker`, `from_di`, `parse_markers`, `resolve_markers`) is the `Annotated`-marker injector. Neither layer wraps `build_child_container`
- `modern_di/suggester.py` — what a suggestion *is* (the `Suggestion` record) and how to *find* one: `suggest(requested_type, providers)` owns the policy (hierarchy hints, typo matching, cap, ordering); `close_matches` is the shared difflib primitive (also used by `UnknownFactoryKwargError`). Carries no formatting
- `modern_di/scope.py` — Scope enum
- `modern_di/group.py` — Group base class for provider namespaces
- `modern_di/exceptions.py` — exception class hierarchy (`ModernDIError` → `ContainerError`/`ResolutionError`/`RegistrationError` subclasses). Each error owns its own message: the raise site passes only structured keyword attrs, and the class's `__init__` renders the f-string and stores those attrs. Every concrete class sets a `docs_slug` (its page under `docs/troubleshooting/`, appended by `__str__` as a trailing `See: <url>` line, enforced by `tests/test_docs_slug_census.py`). This file owns **every glyph**: `_render_chain` (the arrow tree, shared by breadcrumbs and cycles) and `_render_suggestions` (the "did you mean" block). Callers pass facts, never formatting. **Add a message, a glyph, or a class here — never at the raise site.**

### Testing patterns

- Create a `Group` subclass with providers as class attributes → `Container(groups=[...])`
- `container.resolve_provider(provider)` (by reference) or `container.resolve(SomeType)` (by type)
- Overrides: `container.override(provider, mock_obj)` / `container.reset_override(provider)`
- Scope chains: `app_container.build_child_container(scope=Scope.REQUEST)`
- `asyncio_mode = "auto"` — async test functions work without extra markers
- The **`modern-di-pytest`** integration (a sibling repo/package, not a dependency here)

## Workflow

**The spec for a change is its PR body**, not a committed file.
`.github/PULL_REQUEST_TEMPLATE.md` carries the shape (why, design, non-goals,
verification); it is reviewed with the diff. There is no change file and no lane
to choose. A trivial PR (typo, dep bump, formatter) deletes the template and
ships a conventional-commit title.

Two things outlive the PR and are committed under `planning/`: an alternative
**rejected** with reasoning goes to `planning/decisions/`, and real work **not
scheduled** goes to `planning/deferred/` (self-contained, with a revisit
trigger). There is no separate truth-home directory — the living truth about
behaviour is the code and its `INVARIANT:`-marked tests, and a behaviour change
is reviewed with the diff, not promoted to a page. See
[`planning/README.md`](planning/README.md) for the full convention, including
the admission check that decides where a given fact belongs; it is a documented
local deviation from `planning-convention` 2.2.0.

- **Cutting a release (maintainers)** is tag-driven via
  [`.github/workflows/release.yml`](.github/workflows/release.yml): write the
  notes at `planning/releases/<version>.md` from
  [`planning/_templates/release.md`](planning/_templates/release.md) (used
  verbatim as the GitHub Release body; `docs/changelog.md` links to the
  directory rather than republishing it), then push a bare-semver-**named** tag
  off green `main` —
  `git tag -m "modern-di 2.19.2" 2.19.2 && git push origin 2.19.2`. Only the tag
  *name* must be bare semver (that is what the workflow matches); the tag object
  itself may be annotated or signed, and `-m` is required whenever
  `tag.gpgsign`/`tag.forceSignAnnotated` is set — without it `git tag` aborts
  with `fatal: no tag message?`. The workflow runs `just publish`
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
  cross-file rationale lives in an `INVARIANT:` test docstring or
  `planning/decisions/`.

## Vocabulary

A term is listed only when there is a synonym to reject, or a meaning subtle enough that code and
docs must agree on it.

- **Container** — owns the registries and resolves within a scope. *Avoid:* injector.
- **Provider** — a declaration of *how to produce* a dependency; the recipe, not the value. *Avoid:* service,
  dependency.
- **Scope** — one band in the container hierarchy. *Avoid:* lifetime, layer.
- **Group** — a non-instantiable namespace class declaring providers. *Avoid:* module.
- **Resolution** — producing a value from its provider. *Avoid:* injection (reserve that for passing a resolved
  value into a handler).
- **Override** — a test-time replacement of a resolved value. *Avoid:* mock, patch (an override supplies a
  concrete value; it does not wrap or spy).
- **Bound type** — the type a provider is registered under. *Avoid:* registered type, return type.
- **Wiring plan** — the partition of a creator's parameters by how each is satisfied. *Avoid:* compiled kwargs.
- **Finalizer** — a cleanup callback on a cached provider, run LIFO at close. *Avoid:* teardown, destructor.
- **Connection** — the framework object a unit of work carries. *Avoid:* request (too HTTP-specific).
