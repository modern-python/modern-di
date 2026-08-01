---
summary: The context-kwarg path in the Factory closures still pays ~5 Python frames per kwarg; a narrow -9.2% variant is unrefuted, while the full -16.2% inline needs a ruling that ContextProvider.scope and context_type are frozen after registration.
---

# Inline the context-kwarg path in the Factory closures

A `Factory` parameter backed by a `ContextProvider` is resolved per resolve
through `Factory._resolve_context_value`, which calls
`overrides_registry.fetch_override`, then `ContextProvider.fetch_context_value`,
which calls `find_container` and `ContextRegistry.find_context` — roughly five
Python frames per context kwarg, on the path every framework integration takes
for its per-request values.

## Why it is open

Measured on a REQUEST factory with one context kwarg: 312-329 ns → 225 ns
(**~-28%**) for the full inline; a narrower variant measured -9.2%. The work
splits into three parts of increasing invasiveness, and they do not stand or fall
together:

- **(i) Gate `fetch_override` on `has_overrides`.** `_resolve_context_value`
  calls `overrides_registry.fetch_override(...)` unconditionally, while all seven
  compiled closures gate the identical lookup behind `has_overrides` first.
  Measured ~-41 ns (-5.3%) on every no-overrides resolve. This part was **not
  refuted** — its invariant was verified by exhaustion — and it needs no ruling.
  It is a small PR on its own, not a blocked item.
- **(ii) Give the context hop the same-scope int-compare fast path** the Factory
  closures already have, instead of always calling `find_container`.
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
The obvious `_navigate`-based implementation of (ii) double-prepends the
resolution-step breadcrumb, and CI stays green while it does.

## Revisit trigger

A maintainer ruling that a `ContextProvider`'s `scope` **and** `context_type` are
fixed once it is registered — the same shape as the scope freeze, extended to
identity — **or** context kwargs showing up hot in a profile from a real
integration. Part (i) needs neither and can be picked up at any time.
