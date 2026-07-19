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
| G8 | Cold first-resolve: build root container + compile + resolve, depth 6 | construction + first-compile cost |
| G9 | Context resolve: request value by type + APP dep, warm child | non-pure context-folding path |
| G10 | `validate()` on a depth-6 chain (isolated via `pedantic`) | graph-validation traversal, deep |
| G11 | `validate()` on a wide 10-sibling graph (isolated via `pedantic`) | graph-validation traversal, fan-out |
| G12 | Resolve a depth-6 chain with one unrelated override active | override front-guard (`fetch_override`) tax |
| G13 | Per-request cycle finalizing 10 cached resources (`close_sync`) | LIFO teardown at scale |

**Rules.** Containers are built/warmed in setup, never inside the timed call —
**except G8**, the cold scenario, which builds the root container *inside* the
timed call on purpose (its own file, `test_guard_cold.py`) so it measures the
one-time construction + graph compile the other scenarios amortize away.
Cold-resolve scenarios (G1, G3, G4) use transient (uncached) providers so each
timed call does the full wiring. G10/G11 use `benchmark.pedantic` with a
per-round setup that builds a fresh unvalidated container (untimed), so they
isolate `validate()` from construction — a fresh registry each round means every
round runs the full graph walk. Every benchmark asserts the resolved graph is
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
| C5 | Cold build + first resolve, depth 6 | G8 |
| C6 | Context: per-request runtime value by type + app dep | G9 |

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

### C5 cold and C6 context idioms

| Framework | C5 cold (build + first resolve) | C6 context (request value by type + app dep) |
|-----------|---------------------------------|----------------------------------------------|
| modern-di | `Container(groups=[...]) + resolve` | `ContextProvider` + `build_child(context=)` |
| dishka | `Provider + provide×6 + make_container + get` | `from_context` + `container(context=)` |
| that-depends | rebuild 6 `Factory` + `resolve_sync` | `fetch_context_item_by_type` + `container_context(global_context=)` |
| dependency-injector | `ChainContainer() + c0()` | `providers.Dependency` + `.override()` |
| wireup | `create_sync_container + enter_scope + get` | `enter_scope({RequestObj: value})`, registered placeholder |

**Caveat — C5 is not one axis.** The frameworks front-load wiring at different
points, so "cold" measures different things and the cells are **not** comparable
one-to-one: modern-di / dishka / wireup time a real per-container build (dishka
builds the graph; wireup `exec`-codegens a factory per provider);
dependency-injector's number is ~98% provider-graph **deepcopy** on
instantiation, not resolution; that-depends wires at **import** and has no
per-call build, so its cell is a `Factory`-reconstruction analog (6× `Factory.__init__`
+ resolve), not a container build. The honest reading is modern-di vs the
build-time codegen frameworks (dishka/wireup), where staying `exec`-free wins by
a wide margin. C5 aligns validation off (modern-di `validate=False`, dishka
`skip_validation=True`) so it isolates build+compile.

**Caveat — C6 is sync for all five** (a clean sync-vs-sync comparison, unlike
C4), timing the per-request "supply value + resolve" cycle. Two structural
notes: dependency-injector injects **by reference** (`providers.Dependency` +
`.override()`), not by type — a structural analog, not an equivalent; wireup
requires the runtime type **registered** as a scoped injectable with a raising
placeholder factory (its own integration idiom), the value then supplied via
`enter_scope`.

**No comparative validate() row.** `validate()` (G10/G11 in the guard tier) has
no comparative equivalent: dependency-injector and that-depends run no build-time
graph-validation pass, and for dishka and wireup validation is folded inside
`make_container` / `create_sync_container` with no isolation seam (and their C5
cold build already includes it). A cross-framework "validation cost" row would be
n/a for two frameworks and redundant for the others, so it is omitted.

## Running

- `just bench` — guard tier (this repo's env).
- `just bench-compare` — comparative tier (isolated env; first run resolves deps).
