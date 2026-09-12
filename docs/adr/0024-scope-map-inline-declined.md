# `find_container` stays the navigation seam; `_scope_map` is not inlined

**Decision:** resolvers reach a cross-scope target through `_navigate` → `find_container`. The
`_scope_map` lookup is not inlined into the resolvers, although doing so measured −24% on a
cross-scope resolve.

**Why:** `find_container` is a public method on a subclassable class, and children are built via
`self.__class__`, so a subclass travels down the whole tree. Inlining the hit path silently bypasses
an override of it, and the container navigation returns is the one whose cache receives the
singleton and runs its finalizer, so a bypassed redirect relocates instance ownership: a lifecycle
bug nothing in the suite would catch. Demoting `find_container` from extension point would have to
be argued on its own terms, not absorbed as a side effect of an optimisation.
