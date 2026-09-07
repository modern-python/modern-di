# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di` is a **zero-dependency** Python dependency injection framework; [`CONTEXT.md`](CONTEXT.md)
opens with what it does and owns the vocabulary — read it before naming a concept in code, a test
name, or an issue title. Every framework integration (`ls docs/integrations/`) lives in a **separate
repository** and ships as a separate PyPI package, `modern-di-pytest` included.

## Commands

`just` (task runner) and `uv` (package manager). The [`justfile`](justfile) is the source of truth —
`just --list`, or read it; every recipe carries its intent as a comment. The one thing it does not
say: nothing validates Markdown links outside `docs/`. `just docs-build` runs `mkdocs --strict` over
the site only, and root Markdown, `.github/`, and `docs/agents/` are unchecked.

## Architecture

- **Scope** — `IntEnum`, `APP=1 → SESSION=2 → REQUEST=3 → ACTION=4 → STEP=5`. A provider resolves only
  from a container of the same or deeper (higher-int) scope; otherwise a clear error is raised.
- **Container** — the central object. A child (`build_child_container`) shares the parent's
  providers/overrides registries; cache and context are per-container. `container.validate()` (cycle +
  transitive-scope checks) is the only thing that validates.

### Key files

Every module under `modern_di/` is named for what it does; read it. What a single-file read will
**not** tell you:

- `resolver_compiler.py` is the **single resolve path**, one flat closure compiled per provider. A new
  provider type must add a branch here or `compile_resolver` raises. Never extract a helper from those
  closures — the per-node frame budget is the point, and
  `test_resolve_costs_exactly_one_resolver_frame_per_node` says why.
- `exceptions.py` owns **every message and every glyph**. A raise site passes structured facts, never
  formatting; the class renders its own f-string and sets a `docs_slug` (its page under
  `docs/troubleshooting/`, enforced by `tests/test_docs_slug_census.py`). Add a message, a glyph, or a
  class here — never at the raise site.
- `registries/` — `providers_registry` (type → provider, plus the shared plan/resolver memos) and
  `overrides_registry` are shared tree-wide; `cache_registry` and `context_registry` are per-container.
- `dependency_graph.py` walks `WiringPlan.edges`, so what `validate()` traverses is exactly what
  `resolve()` follows. Explicit-stack, never recursive: a caller runs it inside a `RecursionError`
  handler near CPython's stack limit.
- `types.py` — `UNSET` is load-bearing on the resolve path: the miss marker for both the override
  lookup and the cache slot, separating "not passed" from "explicitly `None`".

### Testing patterns

A test declares a `Group` subclass with providers as class attributes → `Container(groups=[...])`, then
`container.resolve(SomeType)` or `resolve_provider(provider)`, with `override`/`reset_override` for
mocks. Scope chains come from `build_child_container`.

## Workflow

Real work **not scheduled** becomes a GitHub issue.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches;
a sibling test may be the one that trips. Nothing enforces that docstring shape; it is read at
review time.

## Code Style

- Design principle: conservative feature set; **resolution** is sync-only (async resolution was removed
  in 2.x), though **finalizers** may still be sync or async (`close_sync`/`close_async`); no global state
- Docstrings: public API documents the contract; internal helpers get a one-line contract, plus at most
  1–2 lines for a genuinely non-obvious constraint. Never narrate implementation or justify code to a
  reviewer — cross-file rationale lives in an `INVARIANT:` test docstring
- `ruff` (`select = ["ALL"]`) and `ty` are configured in `pyproject.toml` and run by `just lint`

## Agent skills

- **Issues and specs** — GitHub Issues on `modern-python/modern-di`, via `gh`:
  [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)
- **Triage labels** — the five canonical roles: [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)
- **Domain docs** — single-context, `CONTEXT.md` + `docs/adr/`: [`docs/agents/domain.md`](docs/agents/domain.md)
- **Cutting a release** (maintainers) — [`docs/agents/release.md`](docs/agents/release.md)
