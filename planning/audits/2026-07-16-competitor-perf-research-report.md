# Competitor performance research: how rival DI libraries make resolution fast

**Date:** 2026-07-16
**Method:** read the **actual installed source** of four rivals in
`benchmarks/comparative/.venv` (dishka 1.10.1, dependency-injector Cython build,
wireup 2.12.0, that-depends); dumped real generated/compiled output where
relevant; ran first-party CPython 3.12/3.13/3.14 microbenchmarks for per-op
costs; read the `dataclasses`/`attrs` codegen source for the `exec` precedent.
**Motivation:** modern-di resolves at ~1064 / 411 / 3280 ns (transient 2-node /
warm singleton / depth-6 chain) vs dishka's ~338 / 231 / 615 — 3-6x behind. A
2026-07-16 spike proved a compiled **closure** resolver hits 155 / 64 / 464
(below dishka), but the cut-1 additive fast path reached only 30-43% because it
reused `Factory` methods and still paid the full per-node tax. This report
establishes, from evidence, **where the gap actually is and which fixes are clean
vs costly.** All absolute ns are machine-relative (Apple aarch64); the *ratios*
are the durable facts.

---

## 1. The headline finding

The ~2x speedup that matters is **generic-per-call interpretation → a resolver
specialized once**. The further jump from a **closure** resolver to **`exec`
codegen** is **0-4% at fixed arity**, and only ~1.5-2x at high arity. Measured
(CPython 3.13, construct `Target(a, b, c)` from three dep callables):

| Strategy | ns/op | vs codegen |
|---|---|---|
| Generic: `target(*[d() for d in spec])` interpreted each call | 196 | 1.9x slower |
| Hand-unrolled **closure**: `target(da(), db(), dc())` | 109 | +4% |
| **`exec` codegen**, unrolled | 104 | 1.0x |

**Consequence for modern-di:** the win is in *hoisting per-node decisions out of
the per-call path*, not in `exec`. Closures capture ~80-90% of the ceiling
(independently corroborated by the wireup analysis), and the spike already proved
a closure resolver beats dishka. `exec`'s only exclusive win is unrolling to
arbitrary argument count; a non-`exec` general resolver should splat a **list**
(`target(*[d() for d in deps])`), never a genexpr (slower for small N) or
`**kwargs` (4-6x slower). This explains the cut-1 shortfall precisely: it never
hoisted `find_container`, the override lookup, or the closed-state check — the
specialization that buys the 2x — so it paid interpreter-path cost from a
compiled path.

---

## 2. CPython 3.12+ per-operation reality (first-party microbenchmarks)

The 3.12+ specializing adaptive interpreter changed the old advice materially.
ns/op on 3.13; consistent across 3.12/3.14.

| Operation | ns/op | Rule of thumb |
|---|---|---|
| Bare call `leaf(a,b)` | 19.3 | baseline Python call |
| +1 wrapper frame | 32.0 | **~13 ns per extra Python frame** |
| +2 wrapper frames | 45.6 | linear, ~13 ns each |
| Positional call `f(1,2,3)` | 17.1 | cheapest arg-passing |
| Keyword call `f(a=1,b=2,c=3)` | 29.2 | +70% vs positional |
| `f(**d)` unpack | 76.9 | **~4.5x positional — avoid** |
| `def f(**kw)` collect + `kw['a']` | 112.6 | **~6.5x positional — worst** |
| `functools.partial(f,x)(y)` | 30.0 | +50% vs closure |
| Closure `inner(y)` | 20.0 | **cheapest indirection** |
| Lambda / bound method | 18.4 / 21.7 | == closure |
| `s_o.x` via `__slots__` | 6.4 | |
| `n_o.x` via `__dict__` | 6.4 | **same as slots for reads on 3.12+** |
| `p_o.x` via `@property` | 16.6 | **~2.6x a plain attribute** |
| `_local = self.attr` hoist, per access | ~1 ns saved | inline caches closed the gap |
| local-bound global callable, per access | ~0.7 ns saved | negligible now |
| `d[k]` hit | 9.5 | |
| `d.get(k)` hit | 14.5 | |
| `k in d` | 9.0 | |
| `try d[k] except KeyError` on **miss** | 76 | **~8x a hit — never as control flow** |

**Load-bearing rules:**
- **Every extra Python frame ≈ 13 ns.** Frame count is the dominant structural
  lever — this is what inlining/hoisting attacks.
- **`**kwargs` is the cardinal sin (4-6x positional).** modern-di currently
  builds a kwargs dict and calls `creator(**kwargs)` — a real, isolable cost.
- **`__slots__` no longer speeds attribute *reads*** (6.4 either way); its value
  is now **memory + typo/write hygiene**, not resolve speed.
- **The `_local = self.attr` hoist is nearly dead** (~1 ns/access) — not worth
  readability debt except in a genuinely hot loop.
- **`@property` costs ~10 ns/access** — keep the hot resolve path off properties.
- `functools.partial` (30 ns) is *slower* than a closure (20 ns). Closure ≈
  lambda ≈ bound method — pick by readability.

**Scaling, where a closure must be *general* (can't hand-unroll):**

| n_deps | generic `target(*[d() for d in deps])` | general closure `target(*(d() for d in deps))` (genexpr) | codegen unrolled |
|---|---|---|---|
| 1 | 155 | 259 | 106 |
| 3 | 194 | 320 | 146 |
| 8 | 339 | 547 | 260 |

Read: a general non-`exec` resolver should build a **list and splat** (the
"generic" column), not a genexpr. Codegen's exclusive win (unrolled literal
positional call) is ~1.5-2x only at high arity. Build cost: codegen ~14 µs/provider
(≈1 ms for 70 providers, invisible at startup) vs closure ~0.12 µs.

---

## 3. Per-library findings

### 3a. dishka 1.10.1 — ahead-of-time per-factory codegen + inlining (the productionized spike)

On first `.get(key)` per key, dishka **`exec`-codegens a bespoke function per
factory**, memoizes it, and inlines same-scope deps as direct calls to sibling
compiled functions. Real dumped output for a cached `C→B→A` chain:

```python
def get_A(getter, exits, cache, context, container, has):
    if key_A_cache in cache:
        return cache[key_A_cache]
    solved = key_A_cache()          # key_A_cache IS class A
    cache[key_A_cache] = solved
    return solved

def get_B(getter, exits, cache, context, container, has):
    if key_B_cache in cache:
        return cache[key_B_cache]
    try:
        solved = key_B_cache(get_A(getter, exits, cache, context, container, has))
    except NoFactoryError as e:
        e.add_path(val_Factory); raise
    cache[key_B_cache] = solved
    return solved
```

Ranked techniques (file refs into `.../site-packages/dishka/`):

1. **Per-factory codegen + inlined dep calls** (`code_tools/factory_compiler.py:442-478`,
   `code_tools/code_builder.py:257-264`). Depth-6 chain = ~1 frame/node vs our ~3;
   kwargs baked as literal call syntax, no per-node type-hint parsing or dict
   build. Dominant win. **Not adoptable wholesale** (violates zero-`exec` ethos).
2. **Scope decided at build time** (`graph_builder/builder.py:375-445`,
   `registry.py:127-137`): each factory lands in exactly one per-scope `Registry`;
   same-scope deps inline to zero lookup, cross-scope deps become **one
   already-bound `getter` reference** — **no per-node `find_container` search**.
   **Cleanest high-value lesson, no exec.**
3. **Cache check compiled inline**, keyed by the **bare type object** (identity
   hash); for transients the cache code is **absent from the bytecode**
   (`factory_compiler.py:94-101`). Adoptable structurally: cheaper cache key +
   separate transient path.
4. **Overrides are the graph** — resolved at build time, zero hot-path branch
   (`builder.py:238-283`). Only partially adoptable: dishka has no runtime
   `override()`; ours does, so we keep a guarded live check.
5. **`__slots__` + hot state as function-local params** threaded down the call
   chain (`container.py:45-54`, `factory_compiler.py:66-69`). Cheap, clean — but
   see §5, slots is memory not speed now.
6. Memoized compile dict via `try/except KeyError` (`registry.py:151-176`); lazy
   compile-on-first-use.

Locking is **not** the differentiator: dishka holds an uncontended `Lock` on the
warm path by default, same as us. cProfile confirms the cost is per-node
frame/lookup tax, not creator work.

### 3b. wireup 2.12.0 — `exec` codegen, plus two ideas that need no exec

Generated singleton factory (dumped):

```python
def _wireup_factory(container):
    storage = container._global_scope_objects
    if (res := storage.get(OBJ_ID, _SENTINEL)) is not _SENTINEL:
        return res
    with _singleton_lock:
        if (res := storage.get(OBJ_ID, _SENTINEL)) is not _SENTINEL:
            return res
        instance = ORIGINAL_FACTORY(cfg = factories[_dep_obj_id_cfg].factory(container),)
        storage[OBJ_ID] = instance
        factories[OBJ_FACTORY_KEY].factory = _create_singleton_instance_factory(instance)
        return instance
```

Techniques (file refs into `.../site-packages/wireup/`):

1. **Per-injectable `exec`-compiled factory** (`ioc/factory_compiler.py:141,280-283`):
   scope/lock/cache/await all branch-eliminated at compile time; storage dict and
   whether-to-cache baked in; kwargs unrolled with literal names.
2. **Self-modifying singleton memoization** (`ioc/factory_compiler.py:184-185,45`):
   after first build it swaps the singleton's factory entry for
   `def _factory(_): return value`, so a **warm singleton resolve is ~2 frames
   regardless of graph depth** — the whole aggregate is memoized. **Closure-achievable,
   no exec.** Biggest warm-path win, and not codegen-specific.
3. **Overrides by dict-swap, not per-call check** (`ioc/override_manager.py:100-153`):
   replace the entry in the shared `factories` dict; parents dispatch through the
   dict at call time and see the override with no recompile and no per-node
   branch. LIFO stack per obj_id supports nesting. **Closure-achievable.**
4. **Baked direct child dispatch** (`ioc/container/base_container.py:141-165`):
   the hot path never re-enters public `get()`; no override lookup, scope nav,
   closed check, or breadcrumb try/except on the happy path.
5. **Codegen kept maintainable**: a 30-line indent-helper (`codegen.py`) and a
   strict **"namespace-of-constants"** rule (generated source holds identifiers,
   never object literals; `factory_compiler.py:259-278`). **But it fails to
   register generated source in `linecache`** — tracebacks show a frame name and
   line number but **no source line**. That is the debuggability tax to avoid.
6. Micro-opts: `__slots__` on hot structures; `storage = container._…` local
   hoist; sentinel probe `d.get(k, _SENTINEL) is not _SENTINEL`; coarse
   `_recompile()` invalidation of all factories on registry change.

Frame accounting (verified): warm singleton/scoped = **2 frames total regardless
of depth** (whole aggregate memoized); transient depth-6 = ~7 flat frames, no
cache/lock/override/scope/breadcrumb code (compiled out).

### 3c. dependency-injector (Cython) — the structure is portable, the C is not

Its speed principle is **"decide once at wiring time, store the decision, branch
on the stored decision."** Portable techniques (file refs into
`.../site-packages/dependency_injector/`):

| # | Technique | Ref | Portable? |
|---|---|---|---|
| 1 | Each edge frozen into an injection object with a precomputed `_call` flag (provider-to-call vs literal-to-return) — **no per-node `isinstance`** | `providers.pyx:4597`; accessor `providers.pxd:377` | **Fully** |
| 2 | Positional/keyword injections in **separate frozen tuples with cached lengths**; zero-injection & no-caller-kwargs **short-circuits** | `providers.pxd:73`; `providers.pyx:1283,1325`; `providers.pxd:410` | **Fully** |
| 3 | No-caller-kwargs fast path skips prefixed-kwargs parsing | `providers.pxd:443` | **Fully** |
| 4 | Override check is a **nullable scalar** (`_last_overriding is not None`), not a dict lookup | `providers.pyx:243`; `providers.pxd:20` | **Fully** |
| 5 | Singleton warm-hit = `if self._storage is None` on a slot; double-checked locking so warm path never locks | `providers.pyx:3000,3069` | **Fully** |
| 6 | Subclass-per-provider-kind, each owns `_provide` — no runtime type-switch | `providers.pxd:145,172,…` | Structure yes (modern-di already has it); C-vtable speed no |
| 7 | Composition: Singleton→Factory→Callable, each layer one concern, gated by `_attributes_len > 0` etc. | `providers.pxd:140,166` | **Fully** |
| 8 | C-struct layout: `cdef`-typed slots, unboxed `int` flags | `providers.pxd` | **Cython-only** (only `__slots__` survives) |
| 9 | `cimport` cross-module C calls, `cdef inline`, unchecked `<Type>` casts | `_cwiring.pyx:8,32`; `providers.pxd:426` | **Cython-only** |
| 10 | `@inject` plan precomputed as dicts; per-call skips caller-supplied params via `_is_injectable` | `_cwiring.pyx:12,22` | **Fully** (structure) |

Sync-mode note: dependency-injector pays a per-value `__is_future_or_coroutine`
check unless the provider is known-sync (`providers.pxd:430,462,481`) — modern-di,
being sync-only, **avoids this entire tax for free.** Skip the async plumbing and
the `foo__bar=` prefixed-kwargs feature wholesale.

### 3d. that-depends — pure-Python baseline, mostly cautionary

Async-first at the interface but keeps a **full parallel sync chain**
(`resolve_sync` all the way down), so sync callers pay **no coroutine cost** —
validating modern-di's sync-only choice on *maintenance* grounds, not runtime.

Perf-positive (borrow):

| Pattern | Ref | Takeaway |
|---|---|---|
| Precomputed `_args_are_providers` bool tuples built once at `__init__` | `providers/factories.py:117-121` | Cache dep "shape" once; per-call only zips bools |
| 0/1-arg fast paths + shared `_EMPTY_ARGS`/`_EMPTY_KWARGS` | `providers/base.py:27-28,45-56` | Special-case leaf/1-dep providers; reuse `()`/`{}` |
| Lock-free double-checked singleton warm hit | `providers/singleton.py:110-126` | Read cache before any lock; slot-backed instance |
| `@functools.cache` injection plan, scope order baked in | `injection.py:99-129` | Introspect once at decoration into typed tuples |
| `__slots__` + `typing.Final` on hot providers | `factories.py:94-102` | Memory/hygiene |

Perf-negative (avoid):

| Anti-pattern | Ref | Lesson |
|---|---|---|
| Per-call `_SyncInjectionStack` + `set()` whenever scope≠None (default INJECT) | `injection.py:146-147,393-406` | Gate teardown scaffolding on **real context use**, not config |
| ContextResource locks on **every** resolve (no warm fast path) | `base.py:512-522` | Give context-bound caches a pre-lock fast read |
| ContextVar-per-provider scope model | `context_resources.py:129-139`; `state.py:51-55` | Int scope + container dict beats `contextvar.get` per node |
| AttrGetter rebuilds `attrgetter` each resolve | `base.py:589-596` | Memoize derived callables on immutable wiring |
| `is_set()` non-inlined call on hot path | `utils.py:23-25` | Inline the sentinel identity check |

---

## 4. The `exec`-codegen precedent, if it is ever justified

`dataclasses` and `attrs` both `exec`-codegen `__init__` and are in extremely
wide production use, so `exec` is not disqualifying per se. **attrs is the model
to copy** (`attr/_make.py`): `_linecache_and_compile` (line 230) injects the
generated source into `linecache.cache[filename]` with a unique
`<attrs generated __init__ mod.Cls>` filename (`_generate_unique_filename`,
line 1601), so exceptions inside generated code produce **real tracebacks and PDB
can step through** — the one trick that neutralizes the undebuggability
objection. It keeps script-building pure and separately testable (`_make_*_script`
returns `(script, globs)` as data), routes builtins through a passed name, and
`_`-prefixes all injected names for hygiene; only one tiny function
(`_compile_and_eval`, line 216) touches `exec`. `cattrs`' `GenConverter` is a
direct DI-adjacent precedent (exec-codegen per-type converters). Defaults are
passed by reference through a factory's locals, never interpolated as literals.

The ceiling **above** codegen is native code: pydantic v2's core is Rust
(pydantic-core, PyO3), msgspec is hand-written C — both moved the per-field loop
out of Python because the interpreter frame/object cost is the floor. Off the
table for a zero-dependency library. So **codegen is the last pure-Python lever**;
the realistic target is "match/beat dishka," not "approach msgspec."

---

## 5. What this means for modern-di

Our exact per-node cost list: `_warn_and_reopen_if_closed`, `fetch_override`
(dict.get), `find_container(scope)` (scope-map walk), breadcrumb `try/except` +
`prepend_step`, and for cached `fetch_cache_item` + `get_or_create(lock)`, plus a
`creator(**kwargs)` dict build.

**Clean, no-`exec` wins (attack that list at build time):**
1. **Resolve each provider's owning-container reference once** (build/validate
   time), so resolve dereferences instead of `find_container(scope)` per node.
   Biggest clean structural win (dishka 3a#2). In practice: compute the target
   once at the root and pass it down; same-scope deps skip navigation via an int
   compare on `container._scope`.
2. **Split transient vs cached resolve paths**; transients skip cache-registry +
   lock machinery entirely; key the cache by a cheaper object.
3. **Gate the override lookup behind a live `if overrides:` flag** so steady-state
   resolves never pay the per-node `dict.get` (keeps runtime `override()` working
   — a guard, not dishka's build-time-only model).
4. **Freeze a per-edge "call vs literal" verdict at registration** (dep-injector
   3c#1); precompute arg shape; 0/1-arg fast paths with shared empty tuple/dict.
5. **Whole-aggregate warm-singleton memoization** → warm resolve depth-independent
   (wireup 3b#2), closure-achievable.
6. **Positional creator calls instead of `creator(**kwargs)`** where the plan
   shows positional-compatible params (fixes the 4-6x cardinal sin).

**The main lever:** a **specialized-once resolver** (closures, per the spike)
captures the ~2x and already beats dishka. No `exec`.

**`exec` codegen is a last increment,** justified only if a profiler isolates the
per-node kwargs loop / arg-shape as the dominant remaining cost (wide nodes or
hot transient graphs). If ever adopted, copy attrs' linecache + hygiene
discipline. Given the zero-dependency, readability-first posture and that closures
already beat dishka, the marginal gain rarely clears the cost.

**Two stale assumptions corrected:** `__slots__` and local-variable binding are
memory/hygiene choices now, **not resolve-speed wins on 3.12+** (the specializing
interpreter closed those gaps). Don't spend readability on them for speed.

---

## 6. Source pointers

- Rival source: `benchmarks/comparative/.venv/lib/python3.14/site-packages/{dishka,wireup,dependency_injector,that_depends}/`
- The 2026-07-16 compiled-resolver spike record: `planning/deferred.md`
- The cut-1 additive-fast-path attempt (superseded): branch
  `design/compiled-resolver-approach-b`, whose two salvageable commits are the
  canonical cycle rooting (`dependency_graph.py`) and self-contained cycle errors
  (`exceptions.py`).
