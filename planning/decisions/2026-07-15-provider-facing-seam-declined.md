---
status: accepted
summary: Decline a provider-facing seam (ResolutionContext view / promoting Container internals) — one Container implementation makes it a hypothetical seam, the crossings are 3 core-internal reaches, and the supported/internal split is already documented.
supersedes: null
superseded_by: null
---

# No provider-facing seam on Container

**Decision:** Do not extract a `ResolutionContext` view handed to providers, nor
promote `Container`'s provider-facing members into a new declared interface
(Candidate 3 from the 2026-07-15 architecture review). Providers keep resolving
against the `Container` directly; the existing `# noqa: SLF001` reaches stay.

## Context

`Container` presents two interfaces through one class: a user-facing one
(`resolve`, `validate`, `override`, `set_context`, `build_child_container`,
`close`) and an undeclared provider-facing one. The review read the built-in
providers reaching past the seam into privates as friction and proposed either a
narrow `ResolutionContext` object handed to `resolve`, or promoting the members
providers need into a documented internal interface.

Exploration sharpened the picture:

- **The crossings are 3, not 5, and all core-internal.** `Factory._lock` (only
  to pass to `CacheItem.get_or_create`), `Factory._warn_and_reopen_if_closed`,
  and `ContextProvider._warn_and_reopen_if_closed` — built-in providers touching
  a sibling core class. (The review's "five" predated candidate 1's
  `Factory.resolve` reorder.)
- **The split is already documented.** `docs/providers/advanced-api.md` blesses
  `find_container(scope)` as "the primitive a custom `AbstractProvider.resolve`
  calls," and marks `_lock` / `_scope_map` / `parent_container` as "internal —
  no stability guarantee, do not build on them."
- **`_warn_and_reopen_if_closed` is transitional.** 3.0 changes closed-container
  behaviour from warn-and-reopen to raise, so that reach changes regardless.

Options on the table: (a) a `ResolutionContext` view narrowing what a provider
can touch; (b) minimal — bless a small provider-facing contract so custom
providers aren't forced into "do not build on" internals; (c) decline.

## Decision & rationale

Chose (c). The deciding evidence: **there is one `Container` implementation**.
Custom providers are a supported, open-ended extension point (many adapters),
but they all resolve against the same single collaborator — so a
`ResolutionContext` abstraction would be one interface with one implementation.
By the project's standing rule (one adapter = hypothetical seam, two = a real
one), the seam is hypothetical on the axis that matters. This is the same
reasoning that declined the grpc introspection seam
([2026-07-14-grpc-registry-introspection-declined](2026-07-14-grpc-registry-introspection-declined.md)).

Reinforcing it: option (a) would change `AbstractProvider.resolve(container)` —
the documented public extension contract — to `resolve(ctx)`, breaking every
custom provider, a large blast radius to formalize a boundary only core code
crosses today. The 3 crossings are core-touching-core, and the docs already
declare which members are supported (`find_container`) versus internal
(`_lock`); the `# noqa: SLF001` markers are honest labels, not a leak. The one
genuine gap — a custom-provider author has no *supported* way to do Factory-grade
singleton locking / closed-state handling — is real but unrequested, and
`_warn_and_reopen_if_closed` is itself changing at 3.0, so building for it now
would formalize a mechanism about to move.

## Revisit trigger

A **second `Container` implementation** appears (making `ResolutionContext` a
real two-adapter seam), **or** a real custom-provider author is blocked needing
the "do not build on" internals (`_lock` / closed-state handling) to do
Factory-grade work — at which point blessing a minimal provider-facing contract
(option b) becomes the migration path.
