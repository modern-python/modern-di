---
summary: Declined inlining Container._scope_map at the four resolver navigation sites — the measured ~24% cross-scope win requires bypassing find_container, a blessed extension point, and silently relocates cached-singleton and finalizer ownership for any Container subclass that overrides it.
---

# Declined: inlining `_scope_map` at the resolver navigation sites

**Decision:** The compiled resolvers keep calling `_navigate` →
`Container.find_container` for a cross-scope hop. The `_scope_map` lookup is not
inlined into the closures.

## Context

Same-scope dependencies skip navigation via an int compare, but every
*cross-scope* node pays a `_navigate` frame plus a `find_container` frame. Four
of the inventory's lenses independently proposed replacing the ternary at the
four navigation sites with an inlined `container._scope_map.get(scope)`, falling
back to `_navigate` only on a miss — the same hand-inlined-memo-hit pattern
already used for `resolver_for` and `fetch_cache_item`. Measured cross-scope
resolve 185.4 → 140.7 ns (**-24%**), with a flat same-scope control.

## Decision & rationale

The measurement is real and was reproduced. It is declined on the invariant, not
the number.

**The invariant audits a function body while the code being changed is a
dispatch.** Every formulation justified itself by what `find_container`'s body
does. But `find_container` is a public method on a subclassable class, and
`Container.__init__` builds children via `self.__class__`, so a subclass is
carried down the whole container tree. Inlining the hit path means a subclass
that overrides `find_container` is **silently bypassed** — its override runs on
the miss path only. `unittest.mock.patch.object` makes this visible directly:
calls recorded on the override go from `['APP', 'APP']` to `[]`.

**The consequence is worse than a missed hook.** The container returned by
navigation is the one whose `cache_registry` receives the singleton. Bypassing an
override that redirects navigation therefore relocates *cached-instance
ownership*, so a different container's `close_async()` runs that instance's
finalizer. That is a lifecycle bug, not a perf regression, and nothing in the
suite would catch it.

**It contradicts a standing decision.** `find_container` is a blessed extension
point;
[`2026-07-15-provider-facing-seam-declined.md`](2026-07-15-provider-facing-seam-declined.md)
rests on that seam existing. Demoting it is a design change, and it should be
argued on its own terms rather than absorbed as a side effect of an optimisation.

**It also failed the gates as submitted**: coverage 99% (two unreachable lines
where the fallback never fires) and `lint-ci` red, at +20 lines with none
deleted, and six new rules a maintainer must hold. `ContextProvider` would still
call `find_container`, leaving two navigation conventions in one codebase.

## Revisit trigger

`find_container` stops being an extension point — an explicit decision that
`Container` subclasses may not redirect navigation, with the lifecycle
consequence above stated and accepted. Then this becomes a plain inlining and the
measured 24% is available.
