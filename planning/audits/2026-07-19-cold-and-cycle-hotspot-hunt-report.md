# Cold / cycle hotspot hunt: profiling paths the C1-C4 audits under-exercise

Where does modern-di spend time on paths the existing benchmark tiers and the
competitor-perf audit did **not** mine — the one-time cold first-resolve
(compile), the realistic per-request cycle (build child -> resolve -> close),
and a deeper line-level look at the C1-C4 steady state? Commissioned as a
token-frugal, profiler-driven search for **new** optimization opportunities not
already in `planning/deferred.md`. The trigger was that the shipped perf work
(single-path compiled resolver #334, dispatch-floor #347, `_next_deeper` memo
#348) has repeatedly mined C1-C4 steady state, so a fresh hotspot is likelier to
hide in the paths those benchmarks never time.

## Method

`cProfile` + `pstats` over three driver shapes reusing the guard/comparative
graph definitions (`Dep`/`Service`, chain-6, cached REQUEST connection). Output
filtered to `modern_di` for the per-target summaries, then re-run unfiltered on
the standout target to attribute stdlib cost. The one headline candidate was
then validated with a throwaway monkeypatch (no repo change) under wall-clock
`perf_counter`, not cProfile, to get a profiler-overhead-free magnitude. Every
candidate was cross-checked against `deferred.md` so only **new** findings are
filed here; known items get a one-line cross-ref.

**Interpreter caveat:** run on CPython **3.10 x86_64** (the repo's `--no-sync`
default venv on this machine), not the M2 / py3.14 of
`.superpowers/plans/benchmark-results.md`. Absolute microseconds are
interpreter-specific; read the **ratios and the call attribution**, which hold
across versions because the finding is structural (a duplicated call), not
constant-factor. Drivers: session scratchpad `profile_hotspots.py` (git-ignored,
not committed).

## Per-target profile summary

Times are total wall for the profiled loop; per-cycle in the prose.

### Cold first-resolve (fresh `Container(groups=[...])` + first `resolve()`)

Per-cycle figures here are **under cProfile** (roughly 2x inflated by profiler
overhead — the same chain-6 cold cycle is 99.8 µs on clean wall-clock, see
Candidate 1); read them for relative attribution, not as absolutes.

| Graph | per cold cycle | top `modern_di` frame (cumtime share) |
|---|---|---|
| transient (2-node) | ~78 µs | `_compile_transient_factory` (72%) |
| chain-6 | ~230 µs | `_compile_transient_factory` (89%) |
| build-only (ctor, no resolve) | ~15 µs | `container.__init__` + `group.get_named_providers` |

Cold is dominated by the **one-time compiled-closure build**, not container
construction (build-only is ~15 µs of the 230 µs). Unfiltered attribution of the
chain-6 cold run is decisive: **`inspect.signature` and its callees are 2.57 s of
4.57 s = ~56% of total cold time** (`_signature_from_callable` 2.57 s cum,
`_signature_from_function` 0.97 s, `Parameter.__init__` 0.31 s,
`_signature_bound_method` 0.32 s, `unwrap` 0.21 s, `get_annotations` 0.13 s).
Every bit of it is triggered by `_positional_names` (`resolver_compiler.py:33`),
which calls `inspect.signature(f._creator)` at compile — see Candidate 1.

### Realistic request cycle (`build_child_container` + resolve cached REQUEST conn + `close_sync`)

~11.7 µs/cycle, spread across three areas (tottime, `modern_di` only):

- **Construction** — `container.__init__` 0.135 (cum 0.197) + `build_child_container` 0.056. The child-alloc trio (RLock / CacheRegistry / ContextRegistry). *Already banked.*
- **Resolve (cold-miss cache path)** — `resolve` 0.101, `get_or_create` 0.084, `build_kwargs` 0.083, `fetch_cache_item` 0.066, `resolve_provider` 0.054, `mark_created` / `resolver_for` / lambda / `_call_creator` ~0.02 each.
- **Close** — `CacheItem.close_sync` 0.073 (cum 0.210) + `CacheRegistry.close_sync` 0.054 (cum 0.269) + `container.close_sync` 0.026 + `_clear` 0.022.

No single dominant frame; the cycle is genuinely distributed. The largest lever
(construction) is the already-banked lazy-alloc trio. See Candidates 2-3 for the
two small new observations.

### Deeper C1-C4 steady state (warm container, resolve-only loop)

- **C1 transient / C3 chain-6:** `resolve_positional` (`resolver_compiler.py:95`) + its arg listcomp (`:107`) are ~76% of resolve time (C3: 0.590 + 0.221 tottime, called 6x/resolve recursively). This **is** the per-node closure-call frame — the codegen ceiling. *Already banked / stance.*
- **C2 warm singleton:** `resolve_provider` 0.081 + `resolve` 0.056 + `fetch_cache_item` 0.034 + `resolver_for` 0.034 — the dispatch floor. *Already banked (C2 swap dropped).*

Nothing new at line granularity here; the audits' function-level picture holds.

## Candidate NEW hotspots

### Candidate 1 — compile-time `inspect.signature` duplication (RECOMMEND: ship)

- **Where:** `resolver_compiler.py:48-52`, inside `_positional_names`:
  ```python
  if names and any(
      p.kind is inspect.Parameter.POSITIONAL_ONLY for p in inspect.signature(f._creator).parameters.values()
  ):
      return None
  ```
- **Cost:** ~56% of cold first-resolve (chain-6), one full `inspect.signature`
  build per provider-with-params, every compile.
- **Why it is pure waste:** `parse_creator` (`types_parser.py:91`) **already**
  calls `inspect.signature(creator)` at Factory construction and **already
  inspects positional-only params** — `_parse_parameter` (`:62-72`) silently
  drops a positional-only-with-default param from `param_hints`, which is exactly
  the shift `_positional_names` re-detects. The information the compile-time call
  recovers was in hand at construction and thrown away.
- **Fix hypothesis:** `parse_creator` records a `bool` (e.g.
  `has_dropped_positional_only`, True iff it dropped such a param) alongside
  `param_hints`; `Factory` stores it; `_positional_names` consults the flag
  instead of calling `inspect.signature`. **Same decision, zero behavior change**,
  the entire `inspect.signature` subtree leaves the compile path.
- **Measured ceiling (validated, monkeypatch, wall-clock):** chain-6 cold
  first-resolve **99.8 µs -> 41.2 µs, −59% (2.4x)**. The real flag-based fix
  lands just under this ceiling (it still does one bool check).
- **Risk:** low. Compile-time only; **no resolve hot-path change** (unlike the
  banked lazy-alloc trio, this adds no per-resolve branch). Touch surface:
  `_positional_names`, `parse_creator`'s return shape, `Factory` storage. TDD:
  a positional-only-with-default creator must still take the kwargs path (the
  existing correctness case the branch guards) — assert the flag reproduces it.
- **Who benefits:** startup / short-lived processes (serverless cold start, CLI,
  test suites building many fresh containers) and every app's first-resolve of
  each provider. It does **not** help steady state (compile is memoized per
  registry). Framed honestly, this is a **cold-path / startup** win, plus a
  genuine simplification (removes a redundant introspection), not a throughput
  win.

### Candidate 2 — double closed-check per `resolve_provider` (OBSERVE, do not action)

`resolve_provider` (`container.py:200`) calls `self._warn_and_reopen_if_closed()`
on entry, and the compiled resolver **also** re-checks `if target.closed:`
(`resolver_compiler.py:104`/`:130`). For a same-scope resolve (`target is self`,
the common case) that is two closed-checks per resolve. Cheap (~0.015 tottime)
and behavior-sensitive: the two checks are on different containers for
cross-scope resolves, and the whole `_warn_and_reopen` shim is transitional — it
becomes a hard `ContainerClosedError` in 3.0, at which point this collapses
naturally. **Not worth touching before the 3.0 change lands.**

### Candidate 3 — `inspect.isawaitable` per sync close (OBSERVE, reject)

`CacheItem.close_sync` (`cache_registry.py:71`) calls `inspect.isawaitable(result)`
on every finalizer run even when `is_async_finalizer` is already known False.
Considered skipping it, **rejected**: it is the safety net that catches a
sync-typed finalizer that actually returns a coroutine (would otherwise leak an
un-awaited awaitable). Close is not the cycle's dominant cost. Keep.

## Already-banked (cross-refs, not re-filed)

- **Child-container construction trio** (RLock ~214 ns, CacheRegistry ~217 ns,
  ContextRegistry ~189 ns) — the cycle's construction cost.
  `deferred.md` "Child-container construction: lazy-allocation leads". Net win
  untested because it adds a resolve hot-path branch; unchanged by this hunt.
- **`resolve_positional` per-node closure frame** (C1/C3 steady state) — the
  `exec`-free codegen ceiling. `deferred.md` "The codegen ceiling on C1/C3";
  rejected stance, not a task.
- **C2 warm-singleton dispatch floor** — `deferred.md` C2 memo-swap, tried and
  dropped 2026-07-18 (`planning/changes/2026-07-18.01`).

## Recommendation

**Ship Candidate 1** as a `planning/changes/` bundle (small lane): a clean ~2.4x
cold first-resolve win that is also a simplification, with no resolve hot-path
risk — the strongest cost/benefit found and the only genuinely new, actionable
hotspot. It is a startup/cold-path win, so frame it as such (not a throughput
claim). TDD as usual: a failing benchmark-style assertion is awkward for a
one-time cost, so gate on a **behavior** test (positional-only-with-default
creator still uses kwargs) plus a before/after cold micro-measurement noted in
the bundle.

Candidates 2-3 are observations, not tasks. Everything else profiled is either
already banked or at its accepted floor. No new `deferred.md` trigger is
warranted beyond Candidate 1's bundle.
