# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## Resolve-path perf headroom after the single-path compiled resolver — from the 2026-07-17 ship

The single-path compiled-closure resolver shipped (change
[`2026-07-16.02`](changes/2026-07-16.02-single-path-compiled-resolver.md), PR #334): the interpreted
recursion is gone, replaced by one per-provider compiled closure memoized on `ProvidersRegistry`. Against
main it is a clean win everywhere (guard tier: transient −37%, warm singleton −31%, deep-chain −61%, wide
−62%; no regression). The comparative tier now places modern-di **mid-pack and the only zero-dependency
pure-Python framework holding its own** — measured median-of-medians over 5 runs (py3.14, one machine,
run-to-run CV ±0-5%), as **modern-di ns (modern-di ÷ rival; >1 = modern-di slower)**:

| Scenario | modern-di | dishka (codegen) | dependency-injector (Cython) | that-depends (pure-py) | wireup (codegen) |
|---|---|---|---|---|---|
| C1 transient (2-node) | 542 ns | 1.30x | **0.81x** | 1.08x | 1.76x |
| C2 warm singleton | 292 ns | 1.19x | 4.76x | 3.45x | 2.99x |
| C3 deep chain (6) | 1291 ns | 1.93x | **0.57x** | **0.79x** | 1.29x |
| C4 async lifecycle | 33.0 µs | 1.04x | **0.19x** | **0.73x** | **0.71x** |

Bold = modern-di faster. It beats the Cython `dependency-injector` on 3 of 4, ties `dishka` on the async
lifecycle, and trails the two `exec`-codegen frameworks by 1.3-1.9x on transient/chain. Two levers remain:

- **C2 warm-singleton whole-aggregate memoization (highest leverage).** modern-di's warm hit (292 ns) is
  3-4.8x slower than the slot/memoized rivals (`dependency-injector` 61 ns C-level slot; `that-depends`
  85 ns lock-free slot; `wireup` 98 ns self-modifying closure) — it still pays the `resolver_for` dispatch
  + override front-guard + `fetch_cache_item` on every warm hit. The wireup technique — after first build,
  swap the cached provider's stored resolver to a bare `return value` closure — would make the warm hit
  near-free. It was deferred from `2026-07-16.02` as a Non-goal because it is **non-trivial in modern-di**
  (unlike wireup): the resolver is shared tree-wide on the registry while the cached value is
  per-container, so a bare swap is only sound for **APP-scoped** singletons (one value tree-wide), and it
  must be invalidated on runtime `override()`/`reset_override()` and on cache clear at container close —
  coupling the swap to those paths. **Attempted and dropped (2026-07-18, change
  [`2026-07-18.01`](changes/2026-07-18.01-warm-singleton-memo-swap.md)):** built the APP-scope-restricted
  swap with override/close/version-bump invalidation, fully tested (free-threaded 200/200, 100% cov).
  Measured **~1.6x** warm-hit reduction (median-of-stable, both tiers: guard g2 584→375 ns; comparative C2
  333→208 ns), which **flips modern-di ahead of dishka** (292 ns) but **misses the ≥2x / ≤146 ns bar**. Root
  cause: `resolve_provider`'s dispatch floor (`_warn_and_reopen_if_closed` frame + `resolver_for` dict.get +
  version check) is unremovable by the swap — unlike wireup, modern-di keeps the resolve→resolver_for
  dispatch, so "near-free" is not architecturally reachable. Dropped because a ~1.6x win did not justify a
  permanent cross-cutting invalidation invariant (a bypass resolver across override/close/add_providers, a
  second source of truth in `_warm_swapped`) against the conservative-feature-set principle. The attempt did
  produce two keepers: the explicit lifecycle contract in [`concurrency.md`](../architecture/concurrency.md)
  and the [DI-concurrency-contract research](audits/2026-07-18-di-concurrency-contract-report.md). The
  better next direction it revealed is the **dispatch-floor simplification** below, not this swap.
- **The codegen ceiling on C1/C3.** The remaining 1.3-1.9x behind `dishka`/`wireup` on transient/chain is
  the cost of staying `exec`-free: both inline dependency calls into generated source, removing the
  per-node closure-call frame that modern-di keeps. Closing it needs `exec` codegen, **rejected** for a
  zero-dependency library (competitor-perf audit §1/§4). So ~1.3-1.9x behind the codegen leaders on
  construction-heavy graphs is the accepted floor without `exec`; revisit only if that stance changes.

**Revisit trigger:** a user-reported warm-singleton bottleneck. The C2 swap was tried and dropped (above);
the codegen ceiling is a stance, not a task. The live next step is the dispatch-floor simplification below.
See the [competitor-perf research](audits/2026-07-16-competitor-perf-research-report.md) (the design
evidence: closures capture ~80-90% of the ceiling, `exec` buys 0-4% at fixed arity).

## Dispatch-floor simplification: invalidate-on-mutation instead of version-stamp-per-resolve — from the 2026-07-18 C2 attempt

The C2 swap tried to *add* a bypass layer and capped at ~1.6x because it could not remove
`resolve_provider`'s dispatch floor. The inverse — *removing* per-resolve work — is the better trifecta
(simpler + more readable + faster), and the explicit lifecycle contract now licenses it.

Today every `resolver_for` / `plan_for` call does `cached = dict.get(pid); if cached and cached[0] ==
version: return cached[1]` — a tuple-unpack + int-compare on the hot path (`providers_registry.py`), purely
to guard against a registry mutation that (per the now-explicit configure→resolve→close lifecycle) only
happens during single-threaded configure. **Refactor:** on `register` / `add_providers` / `_remove_providers`,
`clear()` the resolver + plan memos; store bare callables (drop the version tuple). The hot path becomes a
plain `self._resolvers.get(pid)`, recompile-on-miss.

- **Simpler + readable:** the memos become plain `dict[int, Callable]`; the invariant collapses to "the memo
  is valid until the registry changes, and changing it clears the memo," replacing the snapshot-version-before-build
  subtlety (a whole docstring paragraph today). Keep `_version` only for `is_validated` (validation
  freshness), decoupled from the memo.
- **Faster:** removes the per-resolve tuple-index + int-compare — part of the exact dispatch floor that
  capped C2. No new state (removes the version tuples).
- **Companion (optional):** post-3.0, `_warn_and_reopen_if_closed` collapses to an inlined `if self.closed:
  raise` (closed→error, which the [DI-concurrency research](audits/2026-07-18-di-concurrency-contract-report.md)
  validates against .NET's `ObjectDisposedException`) — one fewer dispatch frame.

**Needs (like C2):** a design pass, a free-threaded soundness check (`clear()` vs `get()` race only during
configure, which the contract puts out of bounds — verify), and a benchmark to confirm the win before
asserting a number.

**Revisit trigger:** the live next perf step; pick up when perf work resumes.

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
