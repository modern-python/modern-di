# Declined: inlining `_scope_map` at the resolver navigation sites

**Decision:** the compiled resolvers keep calling `_navigate` → `Container.find_container` for a
cross-scope hop. The `_scope_map` lookup is not inlined into the closures.

Four independent lenses proposed replacing the ternary at the four navigation sites with an inlined
`container._scope_map.get(scope)`, falling back to `_navigate` on a miss — the same
hand-inlined-memo-hit pattern already used for `resolver_for` and `fetch_cache_item`. **Measured**
cross-scope resolve 185.4 → 140.7 ns (**-24%**), with a flat same-scope control. Reproduced, and
declined on the invariant rather than the number.

**The argument audits a function body while the code being changed is a dispatch.** `find_container`
is a public method on a subclassable class, and `Container.__init__` builds children via
`self.__class__`, so a subclass is carried down the whole tree. Inlining the hit path means a
subclass that overrides `find_container` is **silently bypassed** — its override runs on the miss
path only; `unittest.mock.patch.object` shows calls recorded on the override going from
`['APP', 'APP']` to `[]`.

**The consequence is worse than a missed hook.** The container returned by navigation is the one
whose `cache_registry` receives the singleton, so bypassing an override that redirects navigation
relocates *cached-instance ownership* — a different container's `close_async()` then runs that
instance's finalizer. That is a lifecycle bug, and nothing in the suite would catch it. It also
contradicts a standing decision: `find_container` is a blessed extension point that
[the provider-facing seam decline](0012-provider-facing-seam-declined.md) rests on, and demoting it
should be argued on its own terms, not absorbed as a side effect of an optimisation.

It also failed the gates as submitted: coverage 99% (two unreachable lines where the fallback never
fires) and `lint-ci` red, at +20 lines with none deleted, six new rules for a maintainer to hold,
and `ContextProvider` still calling `find_container` — two navigation conventions in one codebase.

**Revisit trigger:** `find_container` stops being an extension point — an explicit decision that
`Container` subclasses may not redirect navigation, with the lifecycle consequence above stated and
accepted. Then this becomes a plain inlining and the measured 24% is available.
