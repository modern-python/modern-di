# Architecture

The living truth about what `modern-di` does **now** — one file per capability,
updated by hand whenever a change ships. The *why* and *how it got here* live in
[`../planning/changes/`](../planning/changes/) — and decisions deliberately taken,
including options rejected, in [`../planning/decisions/`](../planning/decisions/);
this directory is the present.

These files carry **no frontmatter** — they are prose, dated by git.

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

## Promotion rule

Shipping a change hand-edits the affected capability file(s) here to match the
new reality, in the same PR as the code. The change bundle stays in place under
[`../planning/changes/`](../planning/changes/) — no folder move.
