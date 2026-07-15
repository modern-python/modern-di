# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## Free-threaded (nogil) safety of wiring-plan compilation — from 2026-06-14 audit (A-1)

`Factory._plan` builds the `WiringPlan` outside any lock and publishes it via
`ProvidersRegistry.plan_for`, which stores it in the registry's `_plans` dict keyed by `provider_id`
(`modern_di/registries/providers_registry.py`). Under the GIL this is safe: the plan is a deterministic
function of the providers registry's state as of the version it was built against (a
`ProvidersRegistry.version` stamp, bumped on every `register`/`add_providers`/removal, is stored
alongside the plan and snapshotted *before* the build so a later registration invalidates it), so two
threads that both see the same stamp build identical plans — at worst the work is repeated once — and the
GIL ensures a thread seeing a stored `(version, plan)` entry also sees the fully-built (frozen) object.

Under free-threaded CPython that guarantee is lost on two counts: concurrent `dict.__setitem__` on the
shared `_plans` dict is itself a data race (a resize can corrupt it), and without a memory barrier a
reader could observe the stored reference before the `WiringPlan`'s fields are visible and resolve
against a partially-constructed plan.

**Revisit trigger:** if/when free-threading (PEP 703 / `--disable-gil`) support becomes a goal. Fix
options: build and publish under the registry's own `_lock` (co-located with the `_providers`/`_version`
mutations the plan reads, and deadlock-safe since plan-building is pure lookup that never re-enters
`register`), or publish the reference behind an explicit barrier/atomic. Until then, document modern-di
as GIL-assuming for plan compilation.
See [2026-06-14 audit A-1](audits/2026-06-14-deep-audit-report.md).

## Opt-in DEBUG resolution tracing (ERR-8) — from 2026-07-05 3.0 UX research

A module-level `logging.getLogger("modern_di")` narrating resolution at DEBUG level: resolve start
(provider, scope, container), cache hit vs. creator call, override short-circuit, context reads, and
finalizer order at close — all dropped by default logging config. Field precedent: Uber Fx's event
narration, Koin's opt-in `logger(Level.DEBUG)`. Cost: one `isEnabledFor(DEBUG)` boolean per chokepoint
on the hot path plus 5-8 log statements through resolution code.

**Revisit trigger:** the first user issue that a resolution trace would have answered.
See [2026-07-05 3.0 UX research, ERR-8](audits/2026-07-05-v3-ux-research-report.md).

## Eager warm-up of cached providers (API-8 / INT-3) — from 2026-07-05 3.0 UX research

A `container.init_cache()`-style method (name open: warm_up/prebuild/init_cached — one decision for
both research items) resolving every provider with cache settings at the container's scope, in
declaration order, respecting overrides; finalizers still run LIFO at close. Closes the gap that
`validate()` checks wiring but never calls creators, so a bad DB URL in a `Factory(cache=True)`
creator surfaces on the first request instead of at boot. Field precedent: Spring eager singletons,
Koin `createdAtStart`, that-depends/dependency-injector `init_resources()`. Purely additive,
sync-only by construction. Note: the from-that-depends guide currently editorializes "no equivalent
needed" — shipping this reverses that documented stance.

**Revisit trigger:** the first user/integration request for startup fail-fast (or when a sibling
integration wants a warm-up hook next to `open()`/`validate()` in its lifespan setup).
See [2026-07-05 3.0 UX research, items 13-14](audits/2026-07-05-v3-ux-research-report.md).

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

## Framework-default status: the beachhead — from 2026-06-18 adoption research (A1)

The research's central thesis: adoption compounds by *being depended upon inside a host framework*
(the Pydantic finding — 466k dependent repos, won transitively via anchor projects), not by feature
count. The play is to become the path-of-least-resistance DI inside one host framework, so that
framework's users adopt modern-di without ever shopping for a container.

**Pick Litestar + FastStream, not FastAPI.** FastAPI is saturated by its own `Depends`; Litestar and
FastStream have less DI incumbency and modern-di already ships integrations for both. Target: a
referenced mention of `modern-di-litestar` / `modern-di-faststream` in those frameworks' own
ecosystem / third-party docs. Outreach is maintainer-driven.

**Revisit trigger:** when there is data to choose with — see the download-figures gap below. Note the
live tension: the org launch playbook's Show HN post opens with a FastAPI story (for relatability,
not targeting). Reconcile before launch.
See [2026-06-18 adoption research, §5](audits/2026-06-18-adoption-strategy-report.md).

## Make the integrations "blessed-ready" — from 2026-06-18 adoption research (A2)

One-import setup, a single canonical "recommended DI" example per framework, lifespan wiring handled
for the user, sub-5-minute onboarding. The integration's own README is the conversion surface — a
framework will only bless what a newcomer can adopt in one sitting. Never audited; worth doing now
that there are 12 integrations, and worth pairing with the `@inject` asymmetry (7 of 12 integrations
require it, 4 do not — see the report's §1).

**Revisit trigger:** before any A1 outreach. Blessing requests fail against a rough on-ramp.
See [2026-06-18 adoption research, §1](audits/2026-06-18-adoption-strategy-report.md).

## Reference templates as funnels — from 2026-06-18 adoption research (A3)

Frameworks and blog posts link to *starters*, not to libraries. The org has
`fastapi-sqlalchemy-template` and `litestar-sqlalchemy-template` — but **no FastStream or Typer
template**, and FastStream is half the A1 beachhead.

**Revisit trigger:** alongside A1 — the template is the thing the beachhead framework's docs would
actually link to.
See [2026-06-18 adoption research, §5](audits/2026-06-18-adoption-strategy-report.md).

## Get listed where newcomers look — from 2026-06-18 adoption research (A4)

`awesome-dependency-injection-in-python`, each host framework's third-party/ecosystem page, and rival
comparison pages (dishka publishes an `alternatives.html`). Zero-cost, durable discovery surfaces.
Drafted as §6 of the org launch playbook; never executed.

**Revisit trigger:** the launch window.
See [2026-06-18 adoption research, §5](audits/2026-06-18-adoption-strategy-report.md).

## Publish the benchmarks page — from 2026-06-18 adoption research (B3)

The `benchmarks/` suite (guard + comparative tiers) and its `benchmarks/README.md` methodology now
exist, but there is **no public benchmarks page in the mkdocs nav**. The "fast + zero-dependency"
story is currently unevidenced in public.

**Verify every number before publishing.** The research caught rivals shipping unverified
vendor-self-reported perf claims; modern-di must not join them. Anything published needs a
reproducible method stated alongside it.

**Revisit trigger:** when the benchmark suite is stable enough that a published number won't need
retracting.
See [2026-06-18 adoption research](audits/2026-06-18-adoption-strategy-report.md).

## Size the DI market with real download data — from 2026-06-18 adoption research (evidence gap)

The research verified **no PyPI download figures for any framework** — its own single biggest gap, and
the reason A1's beachhead choice currently rests on intuition. Pull real download trends for
`modern-di`, `dishka`, `dependency-injector`, `wireup`, `svcs`, `that-depends` (and the integration
packages), then revisit the beachhead call with data.

**Revisit trigger:** before committing outreach effort to a beachhead framework.
See [2026-06-18 adoption research, open questions](audits/2026-06-18-adoption-strategy-report.md).

## Core accommodation for validate-by-default vs. integration-supplied context — from 2026-07-14 docs work

`Container(groups=[...], validate=True)` runs `validate()` inside `__init__`, before an integration's
`setup_di()` registers its connection `ContextProvider`s (`fastapi.Request`, `taskiq.TaskiqMessage`, …).
So a `Factory` that depends **by type** on the framework's request/message object raises
`ArgumentResolutionError` at construction — the provider is not wired yet. This is a papercut today
(opt into `validate=False`), but becomes a **default footgun once 3.0 runs `validate()` by default at
root construction**: every integration user with such a factory breaks unless they opt out and lose
validation.

Shipped remedy is a **docs recommendation** — type the parameter `FrameworkType | None = None` so
validation skips it while the integration still injects the real value at runtime (change
[2026-07-14.05](changes/2026-07-14.05-optional-context-types-under-validate.md)). That works but leans
on every user remembering the idiom. Core alternatives explored and set aside: (1) **defer `validate()`**
to `open()`/first-resolve so the graph is complete when it runs — zero boilerplate, but shifts error
timing and reinterprets the 3.0 "validate at construction" promise; (2) **integrations contribute their
connection providers at construction** as an includable `Group` — graph complete, validation stays
eager, but needs an idempotent `add_providers` (it currently raises `DuplicateProviderTypeError` on a
re-registered type); (3) **`setup_di` owns build + validate** — one validate knob, but changes the
integration signature.

**Revisit trigger:** when 3.0's validate-by-default is being finalized — decide whether the docs
recommendation suffices or a core accommodation (approach 1 or 2) is warranted so integration users do
not have to opt into the `| None` idiom.
See change [2026-07-14.05](changes/2026-07-14.05-optional-context-types-under-validate.md).
