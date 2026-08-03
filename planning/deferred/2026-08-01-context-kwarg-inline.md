---
summary: Only the compile-time fold is left: parts (i) and (ii) shipped, and (iii) still needs a ruling that ContextProvider.scope and context_type are frozen after registration -- what it is worth on its own has never been measured apart from the full inline.
---

# Inline the context-kwarg path in the Factory closures

A `Factory` parameter backed by a `ContextProvider` is resolved per resolve
through `Factory._resolve_context_value`, which calls
`ContextProvider.fetch_context_value`, which calls `find_container` and
`ContextRegistry.find_context` — three Python frames per context kwarg when the
resolving container is already at the provider's scope (four before the hop's
int compare shipped, five before the override guard), on the path every framework
integration takes for its per-request values.

## Why it is open

Measured on a REQUEST factory with one context kwarg: 312-329 ns → 225 ns
(**~-28%**) for the full inline; a narrower variant measured -9.2%. The work
splits into three parts of increasing invasiveness, and they do not stand or fall
together:

- **(i) Gate `fetch_override` on `has_overrides`.** ~~`_resolve_context_value`
  calls `overrides_registry.fetch_override(...)` unconditionally.~~ **Shipped.**
  Measured -41.1 ns (-5.98%) on the no-overrides path, with the override-active
  path also improving slightly (-4.4 ns). It needed no ruling and was never
  blocked. (ii) has since shipped too; only (iii) remains.
- **(ii) Give the context hop the same-scope int-compare fast path** the Factory
  closures already have, instead of always calling `find_container`. **Shipped
  (2026-08-03).** It needed no ruling. Measured **-2.5%** on `g9_context`
  (~707 → ~690 ns, four A/B/A runs: -3.05, -1.29, -3.98, -1.94%, all negative,
  against 0.4-1.7% baseline drift). That percentage is **not** comparable to the
  -9.2% recorded above for the narrow variant: this one is measured on
  `g9_context` at ~707 ns, that one on a ~312-329 ns benchmark. In absolute terms
  (ii) is worth ~17 ns, which with (i)'s -41 ns puts the pair at roughly -18% of
  that original baseline — so the narrow variant's target is already met, and
  what (iii) adds on its own has not been measured apart from the full inline.
  Since the timing sits close to the harness's own drift, the suite asserts the
  *structural* claim instead: `test_same_scope_context_hop_does_not_call_find_container`.
  The predicted `_navigate` trap was confirmed and avoided — a plain int compare,
  never `_navigate`, which prepends a resolution step the caller then prepends
  again; `test_scope_error_through_a_context_kwarg_carries_one_breadcrumb_step`
  pins that and was verified to fail against the double-prepending shape.
- **(iii) Fold the bindings at compile time**, capturing `cp.context_type`,
  `cp.scope`, `cp.provider_id` and `absent_disposition(item)` into the closure
  instead of re-reading them per resolve.

Part (iii) is what is actually blocked. It freezes `cp.scope` and
`cp.context_type` in the closure, and an adversarial review showed that a
`Group` subclass declared after first resolve could restamp a shared
`ContextProvider`'s scope, so the inline would inject an APP-scoped value into a
REQUEST-scoped parameter — silently, with the whole suite green. That specific
hazard has since been closed at its source by `ProviderScopeFrozenError`
(scope is frozen once the provider is registered), which removes the
demonstrated counterexample but does **not** by itself license the capture:
`context_type` is still mutable in principle, and no rule yet says a
`ContextProvider`'s identity is fixed at registration.

The submitted prototype also failed the gates: +12 executable statements,
coverage 100% → 99% (eight new uncovered lines, five in the cold cached copy),
and two *new* ruff violations (`C901` 15>10, `PLR0912` 14>12) on the hot closure.
The obvious `_navigate`-based implementation of (ii) double-prepended the
resolution-step breadcrumb while CI stayed green — no longer true since (ii)
shipped with `test_scope_error_through_a_context_kwarg_carries_one_breadcrumb_step`,
which turns that shape red.

## Revisit trigger

A maintainer ruling that a `ContextProvider`'s `scope` **and** `context_type` are
fixed once it is registered — the same shape as the scope freeze, extended to
identity — **or** context kwargs showing up hot in a profile from a real
integration. That ruling is now the only gate: parts (i) and (ii) have shipped,
so (iii) is all that remains. What it is worth on its own is unmeasured — the
-28% above is the full inline, (i) and (ii) included.
