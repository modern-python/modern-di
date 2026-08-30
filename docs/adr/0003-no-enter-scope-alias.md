# No `enter_scope` alias for `build_child_container`

**Decision:** `build_child_container` remains the single scope-entry spelling; no `enter_scope`
alias and no rename.

Every peer names this operation by intent — wireup `enter_scope({Type: obj})`, .NET
`CreateScope()`, dishka's callable container — and `build_child_container` names the mechanism and
is the longest scope-entry spelling in the studied field. Rejected anyway: in modern-di the
mechanism *is* the concept. Child containers are real, user-visible objects with their own cache and
context registries, and "enter scope" vocabulary would hide exactly the mental model the docs work
to teach. A second spelling of the most-written call after `resolve()` also conflicts with the
conservative-feature-set constraint, with wireup's serial renames as the cautionary precedent.

**Revisit trigger:** recurring user feedback that scope entry is hard to discover — issues asking
"how do I enter a request scope". Closing the migrant-familiarity gap in the docs, with a
vocabulary-table row mapping `enter_scope` / `CreateScope` to `build_child_container`, is the
cheaper response and has not been written yet.
