# Free-threaded (nogil / PEP 703) support research: correctness gap and cost to support

**Date:** 2026-07-17
**Scope:** correctness only (parallel-resolution *performance* is explicitly out
of scope — noted as follow-up, see §7). Sizes the gap between modern-di today and
a defensible free-threaded compatibility claim, and recommends whether to pursue it.
**Method:** Part A — read every path that touches shared mutable state during
concurrent `resolve()` (`container.py`, the four `registries/*`, `providers/factory.py`,
`resolver_compiler.py`, `providers/abstract.py`). Part B — a focused web-research
pass (official python.org docs, PEP 703 / PEP 779, packaging.python.org,
`py-free-threading.github.io`, live PyPI metadata for five peer DI libraries) to
establish current free-threaded CPython facts, since 3.14 shipped after the
assistant knowledge cutoff. This report **supersedes** the "Free-threaded (nogil)
safety of wiring-plan compilation" item in [`../deferred.md`](../deferred.md),
whose core premise turns out to be false (§3).

---

## 1. TL;DR / recommendation

**GO — support free-threading at classifier level `2 - Beta`, at low cost.** The
deferred doc's fear (concurrent `dict.__setitem__` corrupts the dict / a resize
corrupts it) is **not true** for real free-threaded CPython: built-in container
single-operations are internally locked and cannot corrupt or crash (§3). Every
lock-free memoization publish in modern-di is **idempotent** (rebuild-if-stale,
at worst duplicated work), so single-op safety is sufficient for correctness. No
non-idempotent corruption bug was found (§4).

The one honest caveat is **object-publication ordering**: CPython publishes *no
formal Python-level memory model*, so "a reader that sees the stored reference is
guaranteed to see the object's fully-initialized fields" rests on *implementation
behavior*, not spec (§3c). This is the same reliance every lock-free Python
singleton pattern makes; it is why the honest classifier level is `2 - Beta`
(production-ready, tested, caveats documented), not `3 - Stable` (a full
thread-safety guarantee we cannot spec-back).

For a **zero-dependency pure-Python** library the packaging cost is ~nil: no C
extension, no `Py_mod_gil`, no special wheel — the existing `py3-none-any` wheel
already runs on `3.14t`. The work is CI + a stress test + a classifier + doc
truth-up (§6). **Competitive note:** none of `dishka`, `that-depends`,
`dependency-injector`, `wireup`, `svcs` has adopted the `Free Threading` trove
classifier; only wireup claims readiness in prose. Adopting it is a differentiator.

---

> **Correction (2026-07-18, during implementation).** The H3 verdict below —
> "the `_building` cycle-guard self-heals, low severity" — was **wrong**.
> Implementation reproduced a real, pre-existing bug: because `_building` is
> shared across threads, two threads first-resolving the same provider
> concurrently make the second mistake the first's in-flight compile for a cycle,
> take the back-edge thunk, and recurse to `RecursionError` on an acyclic graph.
> It reproduces **under the GIL too** (verified on CPython 3.10), so it is not a
> free-threading artifact. Fixed by making `_building` thread-local (the guard is
> per-call-stack). The GO / Beta / low-cost conclusion still holds — this is one
> bounded production fix, not a redesign — but §1's "no hot-path code change" and
> §4's "no non-idempotent corruption path exists" are amended by it. See the
> implementing change bundle.

## 2. Part A — shared-state hazard inventory

Every piece of shared mutable state reachable from concurrent `resolve()`, with
its current synchronization and hazard class. "Idempotent publish" means two
threads racing produce the *same* value for the same registry version, so a
last-writer-wins store is correct and the worst case is repeated work.

| # | State | Site | Current sync | Class | Verdict |
|---|---|---|---|---|---|
| H1 | `ProvidersRegistry._plans` | `plan_for` | lock-free `get`+`setitem`, version-stamped | idempotent publish | safe under §3 |
| H2 | `ProvidersRegistry._resolvers` | `resolver_for` | lock-free `get`+`setitem`, version-stamped | idempotent publish | safe under §3 |
| H3 | `ProvidersRegistry._building` set | `resolver_for` | lock-free `add`/`discard` | compound cycle-guard | **REAL BUG (see correction above)** — fixed via thread-local `_building` |
| H4 | `CacheItem.cache` warm read | `_compile_cached_factory.resolve` | writer stores under RLock; warm reader reads bare | bare-attr publication | §3c reliance |
| H5 | `CacheRegistry._creation_order.append` | `mark_created` | lock-free `append`, one call per item | single-op list write | safe under §3 |
| H6 | `OverridesRegistry` / `ContextRegistry` dicts | `override` / `set_context` vs resolve | lock-free | runtime mutate-during-resolve | inherent race, matches GIL semantics |
| H7 | `provider_id` = `itertools.count()` | provider `__init__` | lock-free `next()` | startup-only | out of hot path |

**The deferred doc is stale on two counts** independent of the corruption
finding: (1) it names only `_plans` (H1); the compiled resolver shipped after it
(PR #334, 2026-07-16) and added `_resolvers` (H2) — an exact structural twin — plus
the `_building` cycle-guard set (H3). Any statement about H1 must now cover H2.

---

## 3. Part B — the CPython facts that decide it

### (a) 3.14 free-threading is officially supported

PEP 779 was accepted 2025-06-16; "What's New in Python 3.14" states verbatim
*"PEP 779: Free-threaded Python is officially supported."* This is Phase II
(supported, still a separate opt-in build), not experimental. Single-threaded
overhead is now ~5–10% (down from ~40% in 3.13). Supporting it is a stable
commitment against a fixed target, not a moving experiment.
Sources: `docs.python.org/3/whatsnew/3.14.html`, `peps.python.org/pep-0779/`.

### (b) Single container ops are safe; compound ops are not

There is now an official `docs.python.org/3/library/threadsafety.html`. Built-in
`dict`/`list`/`set` use per-object locks / critical sections
(`Py_BEGIN_CRITICAL_SECTION`) plus QSBR for lock-free reads. **A single
operation** — `d[k]=v`, `d.get(k)`, `k in d`, `d.setdefault(...)`, `lst.append(x)`
— **cannot corrupt the structure or crash.** **Compound** check-then-act
(`if k in d: del d[k]`, `d[k]=d[k]+1`, `if lst: lst.pop()`, iterate-while-mutate)
is explicitly *not* atomic. **Caveat:** the docs frame single-op safety as *"a
description of the current implementation, not a guarantee."*

This directly **refutes** the deferred doc's premise. There is no dict-corruption
hazard; the only question is whether modern-di's *compound* sequences are
idempotent (they are — §4).

### (c) No formal memory model — publication is implementation-safe, not spec-safe

PEP 703 is implementation-focused (per-object locks, critical sections,
QSBR/mimalloc for use-after-free safety) and makes **no statement** about whether
a reader observing a shared reference sees fully-initialized fields. PEP 583 (a
Python memory model) is withdrawn/historical, not in force. In practice, storing
into a built-in container goes through that container's critical section (with the
attendant atomics), so publication *through a dict/list* is expected safe in the
current implementation — but this is **not a documented guarantee**. H4 is the
weakest point because it publishes via a **bare `slots` attribute store**
(`self.cache = value`), not through a container critical section — it relies purely
on "CPython does not tear a pointer store or reorder the object's field inits
past it," which holds on all real targets but is unspecified.

### (d) Pure-Python declares compatibility with a classifier and nothing else

The `Free Threading` trove classifier is live in `pypa/trove-classifiers` with
four status levels: `1 - Unstable`, `2 - Beta`, `3 - Stable`, `4 - Resilient`
(rough semantics: 1 = feedback-only; 2 = production-ready + multithreaded-tested +
caveats documented; 3 = fully thread-safe; 4 = resilient). A `py3-none-any` wheel
needs **no** free-threading wheel tag and **no** `Py_mod_gil` — those are
C-extension-only. Pure Python runs on `3.14t` unchanged.
Sources: `github.com/pypa/trove-classifiers`, `py-free-threading.github.io/porting/`.

### (e) CI mechanics

`uv python install 3.14t` (and `3.13t`) installs the free-threaded build;
`uv python pin 3.14t` selects it. `actions/setup-python` accepts `python-version:
3.14t`. Confirm the GIL is off at runtime with `sys._is_gil_enabled() is False`
(a `t` build defaults off; `PYTHON_GIL=1`/`-X gil=1` forces it back on). Importing
a non-ported C extension auto-re-enables the GIL with a `RuntimeWarning` — a
non-issue for a zero-dependency lib. Thread-stress tool: **`pytest-run-parallel`**
(Quansight-Labs) reruns the existing suite across a thread pool
(`--parallel-threads=auto`, `--iterations=N`).

### (f) Peer libraries have not claimed it

Live PyPI `classifiers`: `that-depends`, `dishka`, `dependency-injector`, `svcs`
— **none** carry a Free Threading classifier. `wireup` claims *"no-GIL (PEP 703)
ready"* in its description text only (no classifier, not independently verified).
The classifier is an open differentiator.

---

## 4. Why modern-di is already correct (given §3)

Walking each compound sequence for a non-idempotent race:

- **`plan_for` / `resolver_for` (H1/H2):** `get(pid)` miss → build → `setitem`.
  A `WiringPlan`/resolver is a pure function of `(provider, registry-version)`, so
  two racers build **identical** objects and both store the same `(version, obj)`
  tuple. Last-writer-wins is correct; worst case is one duplicated build. The
  version snapshot is taken *before* the build, so a plan built against a
  since-mutated registry carries the old stamp and is never served as current.
- **`_building` set (H3):** for a shared diamond dependency, racer B may see
  A's `pid` mid-compile and return the **unmemoized** runtime-routing thunk
  (`lambda c: c.resolve_provider(provider)`). That thunk is correct (routes through
  the runtime path) and is never stored, so it self-heals to the memoized resolver
  on the next call. `discard` (not `remove`) is safe even if already discarded.
- **`fetch_cache_item`:** `get` fast-path miss → `setdefault`. `setdefault` is a
  single atomic op (§3b), so concurrent first-resolvers share **one** `CacheItem`
  — which is the invariant the double-checked lock on that object depends on. The
  code already comments this intent.
- **`get_or_create`:** `resolve()` (dependency build) runs unlocked; `create` +
  store run under the container RLock, double-checked. Two racers may both run
  `resolve()`; exactly one wins `create` under the lock, the other sees the set
  cache and returns it. A cached *dependency* recurses into its own
  `get_or_create` (no double-create); a transient dependency's discarded value is
  never finalized anyway.
- **`mark_created` (H5):** only the `created=True` winner calls it, once per item;
  `list.append` is single-op safe. Relative order of *independent* singletons is
  already nondeterministic, so the finalizer LIFO invariant (a dependency finalizes
  after its dependents) is unaffected.
- **Override front-guard (H6):** `has_overrides` read + `fetch_override` is racy
  against a concurrent runtime `override()`, but mutate-during-resolve is inherently
  racy under *any* model and already is under the GIL. Not a free-threading
  regression; document as "apply overrides before concurrent resolution."

**Conclusion:** no non-idempotent corruption path exists. The only residual is the
§3c publication-ordering reliance (H1/H2/H4), shared by all lock-free Python
singleton code.

---

## 5. The one design choice for the maintainer

Given §4, the publication-ordering reliance can be handled two ways. This is a
genuine design fork — it trades a spec-level guarantee against hot-path cost and
the zero-`exec`/lock-free-memoization design that PR #334 deliberately bought:

- **Option P1 — accept documented single-op + publication behavior (recommended).**
  Add no locks to H1/H2/H4. Rely on §3b single-op safety (documented) + §3c
  publication (implementation behavior), validate with a `pytest-run-parallel`
  stress job, claim classifier `2 - Beta`, and document the reliance. Zero hot-path
  cost. This is what "beta / production-ready with documented caveats" *means*, and
  matches how every lock-free singleton in the ecosystem already ships.
- **Option P2 — lock/barrier the publishes for a spec-hard guarantee.** Wrap the
  H1/H2 store (and the H4 warm read) so publication has an explicit
  happens-before. This buys classifier `3 - Stable` honesty but **regresses the
  exact lock-free memoization PR #334 shipped** (a lock on every cold publish, and
  for H4 either a lock on the warm-hit fast path or a redesign). Given the plan/
  resolver are immutable-once-built and the store is idempotent, the marginal
  correctness this buys on real targets is ~nil.

Recommendation: **P1 at level `2 - Beta`.** Revisit level `3 - Stable` only if a
real free-threaded miscompile is ever reproduced, or CPython publishes a memory
model that makes P2 cheap to assert.

---

## 6. If GO — the correctness-only work (for the design phase)

1. **CI:** add a `3.14t` job (`uv python install 3.14t` + pin) running the full
   suite, plus a `pytest-run-parallel` thread-stress pass over resolution
   (`--parallel-threads=auto --iterations=N`), asserting `sys._is_gil_enabled()
   is False`. Decide: matrix addition vs. a dedicated stress job (pytest's own
   fixture-sharing-across-threads caveat may argue for a separate, purpose-built
   concurrent-resolution test rather than blindly parallelizing the whole suite).
2. **A concurrent-resolution stress test:** N threads resolving overlapping graphs
   (shared singletons, deep chains, cross-scope) off one root + many child
   containers, asserting single-instance identity for singletons and no exceptions.
3. **Trove classifier:** add `Programming Language :: Python :: Free Threading ::
   2 - Beta` to `pyproject.toml`.
4. **Doc truth-up:** replace the `deferred.md` item with this report's finding;
   add a "free-threading" note to the relevant `architecture/` capability
   (containers or a concurrency note) stating the P1 stance and the H6 override
   caveat; retarget the two GIL-caveat code comments (`factory.py:_plan`,
   `cache_registry.fetch_cache_item`) at this report.

Est. size: one **Full** change bundle (new CI surface + public-metadata change +
architecture promotion). No hot-path code change under P1.

---

## 7. Explicitly out of scope (follow-up)

**Parallel-resolution performance.** Without the GIL, the per-container RLock in
`get_or_create` serializes concurrent first-resolution of *distinct* singletons
sharing a container, and the warm-hit path still pays `fetch_cache_item` +
override front-guard per call. Whether that RLock becomes a contention bottleneck
under real parallel load — and whether a lock-free or per-provider-lock resolution
path is worth it — is a separate investigation that ties into the warm-singleton
perf item in [`../deferred.md`](../deferred.md). Not required for a correctness
claim; revisit if a user reports parallel-resolution contention.
