# No `enter_scope` alias for `build_child_container`

**Decision:** `build_child_container` is the only scope-entry spelling; no `enter_scope` alias, no
rename.

**Why:** peers name the operation by intent (wireup `enter_scope`, .NET `CreateScope`), and
`build_child_container` names the mechanism. In modern-di the mechanism is the concept: a child
container is a real object with its own cache and context, and "enter scope" vocabulary would hide
the model the docs teach. A second spelling of the most-written call after `resolve()` also runs
against the conservative feature set. If discoverability turns out to be a problem, a vocabulary
table mapping `enter_scope` / `CreateScope` to `build_child_container` is the cheaper fix.
