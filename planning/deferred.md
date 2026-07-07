# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## Free-threaded (nogil) safety of wiring-plan compilation — from 2026-06-14 audit (A-1)

`Factory._ensure_plan` builds the `WiringPlan` outside the container lock and publishes it to
`cache_item.wiring_plan` (`modern_di/providers/factory.py`). Under the GIL this is safe: the plan is a
deterministic function of the providers registry's state as of the version it was built against (a
`ProvidersRegistry.version` stamp, bumped on every `register`/`add_providers`/removal, is memoized
alongside the plan so a later registration invalidates it), so two threads that both see the same
`wiring_plan_version` build identical plans — at worst the work is repeated once — and the GIL ensures a
thread seeing a non-`None` `wiring_plan` also sees the fully-built (frozen) object.

Under free-threaded CPython that publication guarantee is lost: without a memory barrier a reader could
observe the non-`None` reference before the `WiringPlan`'s fields are visible and resolve against a
partially-constructed plan. (The WiringPlan refactor narrowed the window — one immutable-object publish
replaced the old set-`kwargs_compiled`-after-the-bucket-fields sequence — but did not add a barrier.)

**Revisit trigger:** if/when free-threading (PEP 703 / `--disable-gil`) support becomes a goal. Fix
options: build and publish `wiring_plan` under the existing container lock, or publish the reference
behind an explicit barrier/atomic. Until then, document modern-di as GIL-assuming for plan compilation.
See [2026-06-14 audit A-1](audits/2026-06-14-deep-audit-report.md).

## Opt-in DEBUG resolution tracing (ERR-8) — from 2026-07-05 3.0 UX research

A module-level `logging.getLogger("modern_di")` narrating resolution at DEBUG level: resolve start
(provider, scope, container), cache hit vs. creator call, override short-circuit, context reads, and
finalizer order at close — all dropped by default logging config. Field precedent: Uber Fx's event
narration, Koin's opt-in `logger(Level.DEBUG)`. Cost: one `isEnabledFor(DEBUG)` boolean per chokepoint
on the hot path plus 5-8 log statements through resolution code.

**Revisit trigger:** the first user issue that a resolution trace would have answered.
See [2026-07-05 3.0 UX research, ERR-8](audits/2026-07-05-v3-ux-research-report.md).

## Shared conformance test suite for integration repos (INT-6) — from 2026-07-05 3.0 UX research

A reusable pytest contract suite, parametrized over each integration's app factory + setup function,
asserting the lifespan/scope/override/close invariants all seven sibling integrations currently
re-implement independently. Published outside core (modern-di-pytest or a conformance sibling) so core
stays zero-dependency; each sibling repo runs it in CI. Precedent:
`Microsoft.Extensions.DependencyInjection.Specification.Tests`; wireup #118 is the regression class it
prevents.

**Revisit trigger:** after INT-1 (`Container.add_providers`) and INT-2 (`resolve_dependency`) land in
core and the sibling repos migrate to those seams — the contract surface changes with them.
See [2026-07-05 3.0 UX research, INT-6](audits/2026-07-05-v3-ux-research-report.md).
