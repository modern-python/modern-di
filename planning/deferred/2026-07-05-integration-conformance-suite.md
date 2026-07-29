---
summary: A reusable pytest contract suite, parametrized over each integration's app factory and setup function, asserting the lifespan/scope/override/close invariants every sibling integration currently re-implements independently.
---

# Shared conformance test suite for integration repos

A reusable pytest contract suite, parametrized over each integration's app factory
plus its setup function, asserting the lifespan, scope, override, and close
invariants that the sibling integration repos currently re-implement one by one.

## Why it is open

Published outside core — in `modern-di-pytest` or a dedicated conformance sibling
— so that core stays zero-dependency. Each sibling repo runs it in CI.

Precedent: `Microsoft.Extensions.DependencyInjection.Specification.Tests` is
exactly this, and it is why MEDI's third-party containers behave uniformly.

The regression class it prevents is real and has escaped to production in the
field: wireup #118 — a raising-placeholder factory whose failure mode only
surfaced in a live app. A contract suite catches that shape before release rather
than after.

There is a second argument for it. Bundling integrations into core for
discoverability was considered and rejected (zero dependencies, conservative
feature set), with that-depends 4.0.2's clean-install failure as the evidence that
bundling erodes rather than guarantees uniformity. Uniformity across separately
published integrations has to come from a written contract plus a conformance
suite instead — this is that suite.

## Revisit trigger

After the core seams the suite would test against have settled and the sibling
repos have migrated onto them — the contract surface changes with them.
`Container.add_providers` has since landed as the integration registration seam
(see [`containers.md`](../../architecture/containers.md)), so this trigger is
partly tripped; check the remaining seam before starting.
