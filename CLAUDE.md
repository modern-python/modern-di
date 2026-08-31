# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di` is a **zero-dependency** Python dependency injection framework; [`CONTEXT.md`](CONTEXT.md)
opens with what it does and owns the vocabulary — read it before naming a concept in code, a test
name, or an issue title. Every framework integration (`ls docs/integrations/`) lives in a **separate
repository** and ships as a separate PyPI package, `modern-di-pytest` included.

## Commands

`just` (task runner) and `uv` (package manager). The [`Justfile`](justfile) is the source of truth —
`just --list`, or read it; every recipe carries its intent as a comment. The one thing it does not
say: nothing validates Markdown links outside `docs/`. `just docs-build` runs `mkdocs --strict` over
the site only, and root Markdown, `.github/`, and `docs/agents/` are unchecked.

## Architecture

- **Scope** — `IntEnum`, `APP=1 → SESSION=2 → REQUEST=3 → ACTION=4 → STEP=5`. A provider resolves only
  from a container of the same or deeper (higher-int) scope; otherwise a clear error is raised.
- **Container** — the central object. A child (`build_child_container`) shares the parent's
  providers/overrides registries; cache and context are per-container. `container.validate()` (cycle +
  transitive-scope checks) is the only thing that validates.

Behavior detail has no prose home — it lives in the code and its `INVARIANT:`-marked tests. Before
writing prose about a capability, run the admission check in **Where a fact goes** below.

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

**The spec for a change is its PR body**, not a committed file.
`.github/PULL_REQUEST_TEMPLATE.md` carries the shape (why, design, non-goals,
verification); it is reviewed with the diff. There is no change file and no lane
to choose. A trivial PR (typo, dep bump, formatter) deletes the template and
ships a conventional-commit title.

Two things outlive the PR, and there are exactly two places to put them: an
alternative **rejected** with reasoning becomes an ADR in [`docs/adr/`](docs/adr/)
(`NNNN-slug.md`, sequential), and real work **not scheduled** becomes a GitHub
issue. There is no third state, and no separate truth-home directory — a
behaviour change is reviewed with the diff, not promoted to a page.

### Where a fact goes

Four homes, one owner each:

| Home | Holds |
|---|---|
| `modern_di/` | anything readable from the module — the default |
| a named test | an **invariant**: must stay true, and a change could silently break it |
| `docs/adr/` | a rejected alternative, with the reasoning that would otherwise be re-litigated |
| `docs/` | anything a user needs |

Before writing a line anywhere:

> Can an agent get this by reading `modern_di/`? → **don't write it.**
> Would a wrong change here fail a test? → it belongs **in the test**, not in prose.
> Does a user need it? → **`docs/`**.
> Otherwise it does not get written.

**Prose about mechanism has no home. There is no file to add a paragraph to.** This file included:
it is always loaded, so a line that restates a docstring, a justfile comment, or `pyproject.toml`
costs every turn and rots in two places at once.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches;
a sibling test may be the one that trips. `tests/test_invariant_census.py` owns and enforces that
shape. Both ADRs and `INVARIANT:` docstrings ratchet: nothing prunes a record once its call is
settled. Keeping them lean is a standing habit.

## Code Style

- Design principle: conservative feature set; **resolution** is sync-only (async resolution was removed
  in 2.x), though **finalizers** may still be sync or async (`close_sync`/`close_async`); no global state
- Docstrings: public API documents the contract; internal helpers get a one-line contract, plus at most
  1–2 lines for a genuinely non-obvious constraint. Never narrate implementation or justify code to a
  reviewer — cross-file rationale lives in an `INVARIANT:` test docstring or an ADR under `docs/adr/`
- `ruff` (`select = ["ALL"]`) and `ty` are configured in `pyproject.toml` and run by `just lint`

## Agent skills

- **Issues and specs** — GitHub Issues on `modern-python/modern-di`, via `gh`:
  [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)
- **Triage labels** — the five canonical roles: [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)
- **Domain docs** — single-context, `CONTEXT.md` + `docs/adr/`: [`docs/agents/domain.md`](docs/agents/domain.md)
- **Cutting a release** (maintainers) — [`docs/agents/release.md`](docs/agents/release.md)
