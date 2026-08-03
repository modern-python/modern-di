# Hot-path performance design

Why the resolve path is shaped the way it is. Several places in `modern_di/` look
like duplication a reviewer would want to collapse, or like a method call that
was needlessly hand-inlined. They are deliberate, and this page is why. The rules
below are the contract; the numbers that motivated them are quarantined in
[Measurements](#measurements), because a measurement ages and a rule does not.

The scope is the **warm resolve path** only — what runs on every `resolve_provider`
once the graph is compiled. Compile-time work (`compile_resolver`, `WiringPlan`)
runs once per provider per registry and is not optimized for; `validate()` and
error rendering are cold by construction.

## The per-node frame budget

**Resolving one node in a dependency graph costs exactly one Python frame — the
node's own compiled resolver.** Nothing else. A chain of depth 6 costs 6 resolver
frames plus the 6 creator calls the user asked for.

This is the rule the rest of the page serves, and it is why
[`resolver_compiler.py`](../modern_di/resolver_compiler.py) contains what reads as
copy-paste. Each compiled closure independently:

- front-guards its own override (`overrides.has_overrides`, then `fetch_override`),
- navigates to its own scope target,
- reopens a closed target,
- inlines the kwargs (or positional) argument build,
- inlines the creator call and its `TypeError` handling.

Extracting any of that into a shared helper is correct, tidy, and costs **one
Python frame per resolved node** — a cost that scales with graph depth on the
hottest path in the library. Python has no inlining to give it back.

**This is enforced, not merely documented.**
`tests/test_resolver_compiler.py::test_resolve_costs_exactly_one_resolver_frame_per_node`
counts Python-level calls (via `sys.setprofile`, so a frame that is pushed and
popped mid-resolve still counts) across two chain depths and asserts the per-node
slope is exactly 2 — one resolver frame, one creator. Extracting the override
guard into a helper moves it to 3 and fails the test by name.

**On CPython below 3.12 the real slope is 3, not 2.** Each resolver's argument
build is a comprehension — `<listcomp>` on the positional path, `<dictcomp>` on
the kwargs path — and before [PEP 709](https://peps.python.org/pep-0709/) a
comprehension is a separate code object, so it costs its own frame per resolved
node. From 3.12 both are inlined into the resolver and the cost disappears. This
is a genuine per-version difference in what a resolve costs, not a measurement
artifact; the test carries the version-conditional constant rather than relaxing
the assertion, so the budget stays enforced on every supported interpreter.

The corollary for anyone adding a provider type: put the whole resolver in the
closure. `compile_resolver` raising `TypeError` for an unknown provider type is
deliberate — there is no interpreted fallback to inherit shared behaviour from.

## Inlined memo hits

Four lookups are hand-inlined across three call sites, with the method called
only on a miss:

| Call site | Inlines | Method still owns |
|---|---|---|
| `Container.resolve_provider` | `providers_registry._resolvers.get(pid)` | the cycle guard and memo write, on a miss |
| `_compile_cached_factory`'s `resolve` | `cache_registry._items.get(pid)` | `setdefault`, which is what makes concurrent first-resolvers share one `CacheItem` |
| `_compile_alias`'s `resolve` | `providers_registry._providers.get(source_type)` and `._resolvers.get(source.provider_id)` | `_find_source`'s error, and `resolver_for`'s cycle guard and memo write, on a miss |

In each case the method being inlined *opens with exactly that lookup and
returns*, so the inline is not a reimplementation that can drift — it is the
method's own fast path, hoisted past its frame. All three keep calling the real
method on a miss, so the miss-path invariants (cycle detection, single shared
`CacheItem`, the dangling-source error) are untouched.

The alias case inlines two lookups rather than one, because the hop is two indirections deep: without them an
alias costs four Python frames (`_find_source`, `find_provider`, `resolve_provider`, then the source's
resolver) where every `Factory` dependency costs one.
`tests/test_resolver_compiler.py::test_alias_hop_costs_exactly_one_resolver_frame` holds it at one.

The warm cached resolve also returns before `CacheItem.get_or_create`, having
already made the same `is UNSET` sentinel check that method opens with.

### No cell on the warm path

The cached-factory resolver's cold-miss thunk is built with
`functools.partial(build_cold, target)` and **must never be a lambda closing over
`target`**. A closure promotes `target` to a cell variable for the *whole*
resolver, so `MAKE_CELL` runs in the prologue on **every** call — including the
warm hit that returns two lines later, and the override hit that never reaches
`target` at all. It also turns four `LOAD_FAST` into `LOAD_DEREF`.

The mechanism is worth stating precisely, because the obvious rationale is wrong:
`functools.partial` is **not** cheaper than a lambda. On CPython 3.14 it costs
~69 ns to construct against the lambda's ~36 ns, and ~105 ns against ~75 ns for
construct-plus-call. It is chosen *despite* that, because it is constructed once
per cold miss while the cell it avoids was charged on every call. The thunk must
therefore stay inside the cell-bearing resolver; hoisting its construction
elsewhere would flip the trade.

Enforced by
`tests/test_resolver_compiler.py::test_cached_resolver_has_no_cell_on_the_warm_path`,
which asserts `co_cellvars == ()` on the compiled resolver — nothing else in the
suite would catch a revert to a lambda.

## The positional fast path

When a creator's entire signature is provider dependencies in declaration order,
the compiled resolver calls `creator(*args)` instead of `creator(**kwargs)`,
skipping the dict build and the keyword-binding cost.

Eligibility is deliberately narrow — `_can_call_positionally` returns `False` on
any static kwarg, context kwarg, omitted defaulted param, keyword-only param,
kwargs-overlay reordering, or positional-only gap. **When in doubt, exclude**: a
wrong `True` here silently binds arguments to the wrong parameters, which is a
correctness bug, not a slow path. `tests/test_resolver_compiler.py` pins all four
exclusion rules plus the positive case directly.

## Scope navigation

A resolver navigates to its target container **once**, and same-scope
dependencies — the common case — skip navigation entirely via an int compare
(`container if container.scope == scope else _navigate(...)`) rather than calling
`find_container`. `Container._scope_map` then makes any genuine cross-scope hop
O(1), and holds ancestors only: a `scope: self` entry would make every container
a reference cycle, so none could be freed by refcounting.

`ContextProvider.fetch_context_value` carries the same guard, so a request value
read from the request container costs no navigation frame either. It uses a plain
int compare and **not** the compiler's `_navigate`: that helper prepends a
resolution step, and the calling `Factory` closure prepends its own, so the caller
would appear twice in the breadcrumb.

`Scope._next_deeper` is memoized because it is a constant function of an immutable
enum member, consulted per child on the default `build_child_container()` path.

## Allocation and lock avoidance

- **`CacheRegistry.fetch_cache_item` has a get-before-setdefault fast path**, because
  a plain `setdefault` eagerly constructs a throwaway `CacheItem` on every hit.
  The creation path still goes through `setdefault`, whose atomicity is what makes
  concurrent first-resolvers share one item.
- **`Container.__init__` inlines its registry wiring** rather than calling a helper:
  it is on the per-request child-build path.
- **The cached-read path takes no lock at all**, and reopening a closed container
  takes none either. See [concurrency.md](concurrency.md) — that page owns the
  thread-safety contract, this one only notes that the absence of a lock is
  intentional rather than an oversight.
- **`WiringPlan`s are memoized on the shared providers registry**, so a
  deeper-scope factory builds its plan once tree-wide, not once per child
  container.

## How to measure a change here

**Do not read a `just bench` median to judge a small change.** Guard-tier
scenarios are auto-calibrated and land on `iterations=1`, so their medians are
quantized to one `time.perf_counter` tick — 41 ns on an Apple M4, which is 23% of
G2's whole value. Two runs of unchanged code report numbers a tick apart, and that
has already caused one false reading of a real change.
[`benchmarks/README.md`](../benchmarks/README.md) documents this in full.

Measure the specific call directly, with enough iterations to escape the grid.
The A/B/A harness under `.superpowers/spike/` (git-ignored, so it survives
`git checkout <rev> -- modern_di/`) does this: it measures base, then candidate,
then base again, and reports the delta against the baseline's own drift.

For a change that claims to be *free*, there is a stronger check than any
benchmark: fingerprint the compiled resolvers' code objects (`co_code`,
`co_consts`, `co_names`, `co_varnames`, `co_freevars`, recursively) before and
after. Byte-identical output means there is nothing to measure.

## Measurements

> Measured 2026-08 on an Apple M4, CPython 3.14. **Absolutes age and are
> machine-specific — the rules above are the contract, these are only the
> evidence that motivated them.** Re-measure before citing.

| What | Cost | Context |
|---|---|---|
| `creator(**kwargs)` vs `creator(*args)` | **4-6x** | the positional fast path's whole justification |
| `resolver_for` method frame | ~34 ns | of a ~170 ns warm resolve (~20%) |
| `fetch_cache_item` method frame | ~23 ns | of the same ~170 ns warm resolve (~14%) |
| `MAKE_CELL` + 4 `LOAD_DEREF` in the cached resolver prologue | ~18 ns | of a ~162 ns warm cached hit (~11%); no path regressed, including a one-shot cold miss |
| `functools.partial` vs a `lambda`, construct + call | +30 ns | why the partial is a deliberate trade, not a free swap |
| `typing.cast` on the context resolve path | ~19 ns | removed in #404 |
| `isinstance` vs an `is` identity check | ~10 ns | why the `UNSET` check is `is`, with a scoped `ty: ignore` |
| A redundant `open()` lock acquire | ~81 ns | found in the comparative C6 body |
| One `time.perf_counter` tick | 41 ns | the guard tier's resolution floor |
