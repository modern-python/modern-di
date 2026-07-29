# Architecture

The living truth about what `modern-di` does **now** — one file per capability,
updated by hand whenever a change ships. This directory is the present; the *why*
of a specific change is its PR body, and decisions deliberately taken — including
options rejected — live in [`../planning/decisions/`](../planning/decisions/).

These files carry **no frontmatter** — they are prose, dated by git.

**The boundary against `docs/`.** `architecture/` answers *how is it built, and
why that way*. [`docs/`](../docs/) answers *how do I use it*. A fact a user needs
belongs in `docs/`; a fact only a maintainer needs belongs here. Where both must
state the same rule, each states it at its own altitude — that restatement is the
point, not duplication to be removed. A runnable block a user would copy is usage,
not mechanism: it belongs in `docs/`, and a page here keeps only the invariant it
was demonstrating.

**One owner per concept.** That altitude argument works between `architecture/`
and `docs/` because they have different audiences. Two capability pages have the
*same* audience, so restatement between them is just two places to update. Each
concept is owned by exactly one page; every other page gets a one-line
cross-link — see [containers.md](containers.md#validate) pointing at
[validation.md](validation.md) for the shape.

## Capabilities

- [scopes.md](scopes.md) — the `Scope` hierarchy and the resolution rule.
- [containers.md](containers.md) — the `Container`, its registries, child
  containers, and lifecycle.
- [providers.md](providers.md) — `Group`, `Factory`/caching, `ContextProvider`,
  `Alias`.
- [resolution.md](resolution.md) — how `resolve()` wires dependencies from type
  hints.
- [validation.md](validation.md) — `validate()` cycle and scope checks.
- [testing-and-overrides.md](testing-and-overrides.md) — overrides and the
  `modern-di-pytest` integration.
- [concurrency.md](concurrency.md) — thread-safety and free-threaded (PEP 703)
  support, at Beta.
- [glossary.md](glossary.md) — the project's ubiquitous language.
- [integration-kit.md](integration-kit.md) — framework-agnostic primitives for
  building a framework integration adapter.

## Promotion rule

Shipping a change hand-edits the affected capability file(s) here to match the
new reality, **in the same PR as the code** — reviewed with the diff, never
applied as a separate post-merge step. That hand-edit is what keeps this
directory true.
