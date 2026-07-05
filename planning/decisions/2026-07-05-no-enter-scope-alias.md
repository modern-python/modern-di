---
status: accepted
summary: Rejected a Container.enter_scope() alias; build_child_container stays the single scope-entry spelling.
supersedes: null
superseded_by: null
---

# No enter_scope alias for build_child_container

**Decision:** `build_child_container` remains the single scope-entry spelling; no `enter_scope`
alias or rename.

## Context

The 2026-07-05 3.0 UX research (candidate API-3) noted every peer names this operation by intent —
wireup `enter_scope({Type: obj})`, .NET `CreateScope()`, dishka's callable container — while
`build_child_container` names the mechanism and is the longest scope-entry spelling in the studied
field. Options surfaced: add as permanent alias, add and deprecate the old name in 3.0, or reject.

## Decision & rationale

Rejected: in modern-di the mechanism is the concept. Child containers are real, user-visible
objects with their own cache and context registries — "enter scope" vocabulary would hide exactly
the mental model the docs work to teach. A second spelling of the most-written call after
`resolve()` conflicts with the conservative-feature-set constraint, and wireup's serial renames are
the cautionary precedent for renaming churn. The migrant-familiarity gap is closed in docs instead:
the accepted DOC-4 (FastAPI users page) and DOC-5 (cross-framework vocabulary table) carry the
"looking for enter_scope / CreateScope? It's build_child_container" mapping.

## Revisit trigger

Recurring user feedback that scope entry is hard to discover (e.g. issues asking "how do I enter a
request scope" that the docs mapping fails to deflect).
