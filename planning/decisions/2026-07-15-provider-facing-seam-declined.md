---
summary: Decline a provider-facing seam (ResolutionContext view / promoting Container internals) — one Container implementation makes it a hypothetical seam, the crossings are core-internal (three then, one since the compiled resolver), and the supported/internal split is documented.
---

# No provider-facing seam on Container

**Decision:** Do not extract a `ResolutionContext` view handed to providers, nor
promote `Container`'s provider-facing members into a new declared interface
(Candidate 3 from the 2026-07-15 architecture review). Resolution runs against
the `Container` directly; the existing `# noqa: SLF001` reaches stay.

## Context

`Container` presents two interfaces through one class: a user-facing one
(`resolve`, `validate`, `override`, `set_context`, `build_child_container`,
`close`) and an undeclared provider-facing one. The review read the built-in
providers reaching past the seam into privates as friction and proposed either a
narrow `ResolutionContext` object handed to `resolve`, or promoting the members
providers need into a documented internal interface.

Exploration sharpened the picture, and the compiled resolver has since narrowed
it further:

- **The crossings are few, and all core-internal.** At decision time there were
  three: `Factory._lock` (only to pass to `CacheItem.get_or_create`), plus
  `_warn_and_reopen_if_closed` on `Factory` and on `ContextProvider` — built-in
  providers touching a sibling core class. (The review's "five" predated
  candidate 1's `Factory.resolve` reorder.) Today there is **one**:
  `ContextProvider` calling `container._prepare()`. The single-path compiled
  resolver dissolved `Factory.resolve` and `Alias.resolve` outright, so the
  lock and closed-state reaches moved out of the providers and into
  `resolver_compiler.py` — the compiler's business, ruled on separately in
  [2026-07-17-per-provider-compile-seam-declined](2026-07-17-per-provider-compile-seam-declined.md),
  not a provider-facing boundary.
- **The split is documented.** `docs/providers/advanced-api.md` blesses
  `find_container(scope)` — "the primitive the compiled resolvers use to locate
  the container at a provider's scope" — and marks `_lock` / `_scope_map` /
  `parent_container` as "internal — no stability guarantee, do not build on
  them."
- **Closed-state handling moved twice and settled.** 3.0 replaced
  warn-and-reopen with a hard raise; 3.1 made `open()` optional, so a root is
  open from construction and reuse after an explicit close warns and reopens.
  `_warn_and_reopen_if_closed` no longer exists in the tree; `_prepare()` is
  what remains of that reach.

Options on the table: (a) a `ResolutionContext` view narrowing what a provider
can touch; (b) minimal — bless a small provider-facing contract so custom
providers aren't forced into "do not build on" internals; (c) decline.

## Decision & rationale

Chose (c). The deciding evidence: **there is one `Container` implementation**.
Everything that resolves does so against the same single collaborator, so a
`ResolutionContext` abstraction would be one interface with one implementation.
By the project's standing rule (one adapter = hypothetical seam, two = a real
one), the seam is hypothetical on the axis that matters. This is the same
reasoning that declined the grpc introspection seam
([2026-07-14-grpc-registry-introspection-declined](2026-07-14-grpc-registry-introspection-declined.md)).

Reinforcing it: option (a) would have changed
`AbstractProvider.resolve(container)` — then the documented public extension
contract — to `resolve(ctx)`, a large blast radius to formalize a boundary only
core code crosses. The crossings are core-touching-core, and the docs already
declare which members are supported (`find_container`) versus internal
(`_lock`); the `# noqa: SLF001` markers are honest labels, not a leak.

The one genuine gap weighed at the time — that a custom-provider author had no
*supported* way to do Factory-grade singleton locking or closed-state handling —
has since dissolved from the other end rather than being closed. The provider
set is closed and subclassing `AbstractProvider` is not an extension point
([2026-07-17-custom-providers-retracted](2026-07-17-custom-providers-retracted.md)),
so there is no audience left for a provider-facing contract to serve.

## Revisit trigger

A **second `Container` implementation** appears, making `ResolutionContext` a
real two-adapter seam.

The original second limb — a real custom-provider author blocked on the "do not
build on" internals — is retired: the provider set is closed, so that author
does not exist. If the set ever reopens, the migration path is the polymorphic
`compile()` hook named in
[2026-07-17-per-provider-compile-seam-declined](2026-07-17-per-provider-compile-seam-declined.md),
not a provider-facing view of `Container`.
