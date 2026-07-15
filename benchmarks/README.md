# Benchmarks

Two tiers, one scenario vocabulary. Numbers here are **guidance, not published
claims**; result files are generated artifacts and are never committed.

## Guard tier (`benchmarks/`, zero external deps)

Decomposes modern-di's resolve hot path so a regression points at a specific
cost. Runs in CI (informational, non-gating) and locally via `just bench`.

| ID | Scenario | Isolates |
|----|----------|----------|
| G1 | Transient resolve, single dep, warm container | pure wiring cost |
| G2 | Cached resolve, warm cache | cache-hit lookup |
| G3 | Deep chain, depth 6, uncached | per-edge wiring |
| G4 | Wide, one object with 10 sibling deps | fan-out |
| G5 | Cross-scope resolve, REQUEST -> APP dep | `find_container` traversal |
| G6 | `build_child_container(REQUEST)` | per-request setup |
| G7 | Full lifecycle: build REQUEST -> sync-init cached resolve -> `await close_async()` | real per-request cost incl. async teardown |

**Rules.** Containers are built/warmed in setup, never inside the timed call.
Cold-resolve scenarios (G1, G3, G4) use transient (uncached) providers so each
timed call does the full wiring. Every benchmark asserts the resolved graph is
correct. G7 is wall-clock only — instruction-count tooling cannot measure the
awaited teardown, and a single reused event loop keeps loop overhead out of the
signal as far as practical.

## Comparative tier (`benchmarks/comparative/`, isolated project)

modern-di vs dishka, that-depends, dependency-injector, wireup on the same
graph shape. Local-only (`just bench-compare`); never in CI. Deps are pinned in
`benchmarks/comparative/pyproject.toml`; the env is git-ignored.

| ID | Scenario | Guard equiv |
|----|----------|-------------|
| C1 | Transient resolve, single dep | G1 |
| C2 | Singleton resolve, warm | G2 |
| C3 | Deep chain, depth 6 | G3 |
| C4 | Request lifecycle: enter request scope -> sync-init resolve -> async-finalize on exit | G7 |

### Per-framework idiomatic mapping

Each framework uses its **natural** request-scope + resource-teardown idiom (not
modern-di's scope names forced onto it). C1-C3 are synchronous resolves for every
framework. C4 is not sync-vs-sync: modern-di resolves synchronously under an async
finalizer, while dishka / that-depends / dependency-injector / wireup all force an
awaited resolve — so C4 measures the whole request lifecycle, not an isolated
resolve.

| Framework (pin) | C1 transient | C2 singleton | C4 scoped + async teardown | C4 resolve |
|-----------------|--------------|--------------|----------------------------|------------|
| modern-di | `Factory` (uncached) | `Factory(cache=True)` | REQUEST `Factory(cache=CacheSettings(finalizer=async))`, `await close_async()` | **sync** |
| dishka 1.10.1 | `provide(cache=False)` | `provide` (cache default) | async-gen `@provide(REQUEST)`, `async with container()` | await |
| that-depends 4.0.2 | `Factory` | `Singleton` | async-gen `ContextResource`, `container_context` | await |
| dependency-injector 4.49.1 | `Factory` | `Singleton` | async-gen `Resource`, `init/shutdown_resources` | await |
| wireup 2.12.0 | `injectable(transient)` + scope | `injectable` (singleton default) | async-gen `injectable(scoped)`, async container | await |

**Caveat — C4 is not sync-vs-sync.** modern-di is the only framework that resolves
the connection **synchronously** while finalizing asynchronously; the other four
force an **awaited** resolve once the finalizer is async. C4 therefore measures the
whole request lifecycle (enter scope -> resolve -> async finalize) as wall-clock
under a shared event loop, not an isolated resolve. C1-C3 are true synchronous
resolves for every framework. wireup's transient/scoped resolves require an active
scope, entered once in setup so C1/C3 time only `scope.get`.

## Running

- `just bench` — guard tier (this repo's env).
- `just bench-compare` — comparative tier (isolated env; first run resolves deps).
