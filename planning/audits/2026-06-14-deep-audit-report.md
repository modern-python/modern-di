# Deep Audit Report — 2026-06-14

**Baseline:** lint-ci PASS, pytest PASS (100% coverage), at commit `4ff7c76` (main).
**Method:** Multi-agent workflow — five parallel finders (bugs, security, performance,
UX/DX, refactoring), each reading source **and** tests, followed by an adversarial
verifier per finding that re-read the actual code and tried to refute it or correct its
severity. 30 agents, 25 findings; severities below are **post-verification**.
**Prior audits:** [2026-06-12 code+docs](2026-06-12-code-docs-audit-report.md),
[2026-06-05 bug-hunt](2026-06-05-bug-hunt-audit-report.md).

## Summary

One genuine ship-blocker (a silent cross-scope `set_context` staleness bug); everything
else is low-severity polish, confirmed-clean non-issues, or one refuted finding. The
security pass came back effectively clean — the two "security" items are a self-inflicted
`RecursionError` and bounded developer-facing error text, neither attacker-reachable.

**Status (2026-06-14):** **B-1**, **B-2**, and **X-1** — the `set_context` cluster —
shipped in **#216** (`ContextProvider` values now resolve live on every resolve;
`invalidate_compiled_kwargs` deleted; docstring + `architecture/` updated; regression
tests added). See
[bundle](../changes/archive/2026-06-14.02-set-context-cross-scope-staleness/design.md).
Two findings shifted slightly post-#216: **R-2** is now *more* relevant (the fix added a second
`ContextProvider._find_context_value` reach-in), and **R-5** is *partially* addressed (the
fix extracted a shared `_argument_resolution_error` helper).

**Status (2026-06-14, batch 1):** the approved doc/test/comment-only rulings shipped in **#217** —
**B-4** (pinning test), **B-5**/**S-1**/**S-2** (doc notes), **A-1** (GIL-benign comment + nogil
caveat in [`deferred.md`](../deferred.md)); **A-2** closed (already documented intentional). See
[bundle](../changes/archive/2026-06-14.03-audit-doc-rulings-batch1/plan.md).

**Status (2026-06-14, batch 2):** the real low-risk code fixes shipped in **#218** — **B-3**
(gapped custom-enum child-scope derivation) and **P-1** (drop the per-resolve throwaway
`CacheItem` alloc via a `get` fast path, retaining atomic `setdefault` on the creation path —
its atomicity is load-bearing for concurrent singleton first-resolve). See
[bundle](../changes/archive/2026-06-14.04-audit-fixes-batch2/plan.md).

**Status (2026-06-14, batch 3):** the refactor batch shipped in **#219** — **R-1**
(`AbstractProvider.display_name` dedupes the bound-type-or-repr idiom across ~5 sites) and **R-2**
(minimal: public `fetch_context_value`, drop the `SLF001` reach-in; `isinstance` routing kept by
design). See [bundle](../changes/archive/2026-06-14.05-audit-fixes-batch3/plan.md).

**Status (2026-06-14, batches 4–5 — audit closed):** the final cleanup shipped in **#220** —
test hardening (**P-6** compile-once pin, **R-3** behavioral singleton assert, **X-2** structured
suggestion/dependency-path asserts) and DX/docs (**X-3** exception docstrings, **X-4** `exceptions`
export, **X-5** `ResolutionStep` docs). See
[bundle](../changes/archive/2026-06-14.06-audit-fixes-batch4-5/plan.md).

**No actionable findings remain.** Closed as **won't-fix** (marginal, by design): **P-2** (a
negligible same-scope `find_container` short-circuit), **R-4** (extract `validate()`'s DFS closure),
**R-5** (single `_classify_param` — the compile vs. validate predicates genuinely diverge, so it
cannot be cleanly unified), **R-6** (split `CacheItem`'s dual role). **Deferred** with a revisit
trigger in [`deferred.md`](../deferred.md): **A-1** free-threading/nogil follow-up. P-3/P-4/P-5 are
verified non-issues; **S-1**/**S-2** were documented in batch 1; **RF-1** refuted.

| Category | High | Medium | Low | None/Clean | Refuted | Total |
|---|---|---|---|---|---|---|
| Bugs (B) | 1 | 1 | 3 | – | – | 5 |
| Security (S) | – | – | 2 | – | – | 2 |
| Performance (P) | – | – | 3 | 3 | – | 6 |
| DX / UX (X) | – | 1 | 4 | – | – | 5 |
| Refactor (R) | – | – | 6 | – | – | 6 |
| Refuted | – | – | – | – | 1 | 1 |
| **Total** | **1** | **3** | **18** | **3** | **1** | **26\*** |

\* 25 verified workflow findings + 1 refuted. Two further main-agent read-through
observations (**A-1**, **A-2**) are recorded at the end; they were outside the workflow's
finder coverage.

---

## Bugs (B)

### B-1 — `set_context` on a parent serves stale values to deeper-scoped factories — HIGH — confirmed — ✅ shipped #216
**Location:** `container.py:230-231` (`set_context`); `cache_registry.py:61-65`
(`invalidate_compiled_kwargs`).
`set_context` invalidated only the calling container's compiled-kwargs memo. A
`REQUEST`-scoped `Factory` reading an `APP`-scoped `ContextProvider` caches its memo in the
*child*; when the context was unset at first resolve, the absence (`None`/default) was
baked in and never invalidated → permanently stale, no error. Reproduced. The present-value
path was already live; only the *absence* was frozen. **Fix (#216):** context params
resolve live on every resolve; `invalidate_compiled_kwargs` removed.

### B-2 — No test covered set_context propagation across scopes — MEDIUM — confirmed — ✅ shipped #216
**Location:** `tests/providers/test_context_provider.py`.
Every `set_context`-after-resolve test was same-scope, so the 100% coverage gate stayed
green while B-1 shipped. **Fix (#216):** added cross-scope defaulted/nullable/required +
override + cached-limitation regression tests.

### B-3 — Auto-derived child scope breaks for non-contiguous custom `IntEnum` — LOW — confirmed — open
**Location:** `container.py:108-112` (`build_child_container`).
`scope=None` derives the next scope as `self.scope.value + 1`, assuming contiguous values.
A gapped custom enum (`TENANT=6, JOB=10`) raises `MaxScopeReachedError` despite a deeper
member existing. The stock `Scope` enum is contiguous, and passing `scope` explicitly
always works. **Fix:** derive the smallest member `> self.scope`; add a gapped-enum test.

### B-4 — `override()` bypasses scope validation — LOW → none — partial (documented intentional) — note only
**Location:** `container.py:139-145` (`resolve_provider`).
An overridden `REQUEST`-scoped provider resolves from an `APP` container (the override is
returned before the scope check). Real and reproducible, **but** this is documented
intentional behavior (`architecture/testing-and-overrides.md` "Scope behaviour under
overrides"). The only residue is that no unit test asserts this exact case directly —
optional test hardening, not a bug.

### B-5 — Union members lose parameterization — LOW — partial — open
**Location:** `types_parser.py:32` (union branch).
`int | list[str]` collapses `list[str] → list`, so a provider bound to bare `list` can
match — while a *non-union* `list[str]` is correctly rejected at declaration. The collapse
is intentional and tested (`test_types_parser.py:30,32`); impact is marginal (needs a
generic union member *and* an origin-typed provider) and Python ignores element types at
runtime. **Fix (optional):** document the asymmetry, or skip generic union members instead
of collapsing.

---

## Security (S)

> Overall: low surface, no attacker-reachable vulnerabilities. Both items are bounded and
> developer-facing.

### S-1 — No runtime cycle/depth guard → `RecursionError` — LOW — confirmed — open
**Location:** `factory.py` (`resolve`), `alias.py:69-74`.
Resolution recurses on the Python stack with no cycle/visited-set; only opt-in
`validate()` detects cycles. A circular graph that never calls `validate()` raises a raw
`RecursionError` on first resolve. The graph is developer-defined (not attacker input), so
this is a self-inflicted misconfiguration crash, not a DoS vector. **Fix (optional,
ergonomics):** track in-flight `provider_id`s during resolve to raise
`CircularDependencyError` eagerly; document `validate=True` for development.

### S-2 — Creator/finalizer error messages embed wrapped exception repr — LOW — partial — open
**Location:** `exceptions.py:195-199` (`CreatorCallError`), `:312-317` (`FinalizerError`).
`FinalizerError` embeds the full list of finalizer exception reprs; `CreatorCallError`
embeds an arg-binding `TypeError` message (narrower than the finding implied — arbitrary
creator-body exceptions propagate unwrapped). DI errors are conservative otherwise (type
names only; context values keyed by type, never repr'd). Disclosure is bounded to
already-exposed exception text and is developer-facing. **Fix:** none needed; optionally
document that apps must not echo raw exceptions to untrusted clients.

---

## Performance (P)

> The resolve hot path is sound: kwargs compilation is memoized (compile-once),
> `find_container` is genuinely O(1), and `validate()`/`build_suggestions` are off the hot
> path. P-3/P-4/P-5 are verified non-issues.

### P-1 — `fetch_cache_item` allocates a throwaway `CacheItem` on every repeat resolve — LOW — confirmed — open
**Location:** `cache_registry.py:55`.
`setdefault(id, CacheItem(...))` evaluates the default eagerly, so every cache-*hit*
(every resolve after the first) constructs and discards a `CacheItem` (+2 dicts) → steady
gen-0 GC pressure in hot loops. **Fix (clean, recommended):** `get`-then-set.

### P-2 — Redundant `closed` check + `find_container` per recursive resolve — LOW — confirmed — open
**Location:** `container.py:136-137`, `factory.py:235-237`.
~2N `closed` reads + N `find_container` lookups for an N-node graph. The second check is
correct for cross-scope targets but redundant when provider scope == entry scope.
**Fix (optional):** short-circuit `find_container` when `self.scope == provider.scope`.

### P-3 — `scope_map` / `find_container` is genuinely O(1) — none — confirmed clean
`scope_map` is precomputed at construction (≤5 entries); `find_container` is two dict ops.
Micro-nit: collapse `in` + `[]` into one `.get()`. No action.

### P-4 — Per-resolve `resolved_kwargs` rebuild is intrinsic — none — confirmed clean
The dict copy + per-key recursion is unavoidable for transient instances; compilation is
memoized; singletons short-circuit. Optimal structure. No action.

### P-5 — `validate()` cost bounded; `build_suggestions` off hot path — none — confirmed clean
`validate()` is O(V+E), opt-in, construction-time; `build_suggestions` is error-path only.
No action.

### P-6 — No test guards the compile-once memoization invariant — LOW — confirmed — open
**Location:** `factory.py` (`_ensure_kwargs_cached`); `tests/providers/test_factory.py`.
Nothing asserts that kwargs compilation runs once per provider per container; a regression
moving it onto the per-resolve path would leave all tests green (results identical, only
slower). Still applies post-#216 (the three-bucket compile is still gated by
`kwargs_compiled`). **Fix:** spy/counter on the compile path asserting one call across
N>1 resolves.

---

## DX / UX (X)

### X-1 — `set_context` docstring overstated late-pickup — MEDIUM — confirmed — ✅ shipped #216
The docstring promised unconditional late-context pickup; true only for non-cached,
same-scope. **Fix (#216):** scoped the guarantee to non-cached providers and documented the
cached-singleton limitation.

### X-2 — Tests assert exact full message strings — LOW — confirmed — open
**Location:** `tests/test_suggestions.py` (7 sites), `tests/test_dependency_path.py:39-45`.
Full-string `==` assertions embed the raw `<class '...'>` repr and exact tree indentation;
`test_typo_suggestion` even embeds the enclosing test-function name (`<locals>.Repostory`).
Brittle against future message polish. **Fix:** prefer substring + structured-field
assertions (as the argument-resolution tests already do); reserve `==` for stable fields.

### X-3 — User-facing exceptions lack attribute docstrings — LOW — confirmed — open
**Location:** `exceptions.py` (concrete subclasses).
Public inspection attributes (`.provider_type`, `.suggestions`, `.original_error`,
`.finalizer_errors`, `.is_async`) are documented in prose but carry no class/attribute
docstrings, so IDE hover yields nothing. **Fix:** brief docstrings enumerating the public
inspection attributes.

### X-4 — `exceptions` absent from `modern_di.__all__` — LOW — partial — open
**Location:** `modern_di/__init__.py:6-11`.
`exceptions` isn't in `__all__` (nor explicitly imported). The documented
`from modern_di import exceptions` works regardless (submodule import), so the "fragility"
framing is overstated — but adding it to `__all__` alongside `providers` is a tidiness
nicety for discoverability. **Fix:** explicit import + `__all__` entry.

### X-5 — `ResolutionStep` is test-asserted but undocumented — LOW — partial — open
**Location:** `exceptions.py:12-15`; asserted in `tests/test_dependency_path.py:35-38`.
The `dependency_path` element type (`scope`/`name`) has no docstring and isn't mentioned in
`errors-and-exceptions.md`, though `dependency_path` itself is documented. Not a public-API
contract (not in `__all__`). **Fix:** short docstring + a doc mention as the programmatic
inspection surface.

---

## Refactor / Code & Test Health (R)

### R-1 — `bound_type` display-name idiom duplicated across ~5 sites — LOW — confirmed — open
**Location:** `factory.py:108`, `alias.py:49`, `container.py:159`, `exceptions.py:281-282`.
`bound_type.__name__ if bound_type else repr(...)` is reimplemented in several places (with
a creator-name variant in Factory), and the fallbacks already differ subtly. **Fix:** a
`display_name` property on `AbstractProvider`, overridden in `Factory`.

### R-2 — `Factory` reaches into `ContextProvider._find_context_value` — LOW — confirmed — open (more relevant post-#216)
**Location:** `factory.py` (`_compile_kwargs` / `_resolve_context_value`).
`isinstance(provider, ContextProvider)` + private-method probe (`SLF001`) couples `Factory`
to `ContextProvider` internals. #216 added a *second* such reach-in (`_resolve_context_value`),
so the case for a public API is stronger now. **Fix:** expose a public
`AbstractProvider.has_resolvable_value(container)` (default `True`, overridden by
`ContextProvider`), or a public context-value accessor.

### R-3 — Tests assert on internal `cache_registry`/`cache_item` state — LOW — confirmed — open
**Location:** `tests/providers/test_singleton.py:54-55,133-144,291`, `test_factory.py:379`.
White-box asserts on `cache_item.cache`/`cached_count()` couple tests to `CacheItem` layout.
The async-finalizer-in-sync-close case is defensible (no behavioral surface). **Fix:** assert
behavior (same/new instance, finalizer ran) where a behavioral surface exists.

### R-4 — `validate()` inlines a dense DFS closure — LOW — confirmed — open
**Location:** `container.py:147-195`.
The nested `_visit` closure interleaves cycle detection, per-provider issue collection, and
scope-ordering checks over four shared mutable locals. Correct and fully covered via the
public API; extraction would only buy finer test seams. **Fix (optional):** extract a small
module-level helper / `GraphValidator`.

### R-5 — Duplicated per-parameter predicate across Factory methods — LOW — partial — open (partially addressed #216)
**Location:** `factory.py` (`_compile_kwargs`, `iter_validation_issues`, `get_dependencies`).
The runtime-resolution and static-validation predicates build an identical
`ArgumentResolutionError` and can drift. #216 extracted a shared `_argument_resolution_error`
helper (partial). The shared lookup `_find_dep_provider` was already factored;
`get_dependencies` is a deliberate pure-lookup, not a duplicate. **Fix (optional):** a single
`_classify_param` helper consumed by all three.

### R-6 — `CacheItem` mixes instance-cache and compiled-kwargs concerns — LOW — partial — open
**Location:** `cache_registry.py:9-43`.
One struct owns both the singleton instance/finalizer lifecycle and the compiled-kwargs memo.
Cohesion nit; the dual role is already documented in `architecture/containers.md`, and
co-location is a defensible hot-path choice (single dict lookup). **Fix (optional):** split
the memo, or leave as documented.

---

## Refuted

### RF-1 — "CreatorCallError `tb_next` heuristic is fragile" — REFUTED
**Location:** `factory.py:220-232` (`_call_creator`).
Claim: a creator raising `TypeError` from its first line (no inner frame) is misclassified
as a wiring error. Empirically false — a Python creator's frame is always pushed before its
body runs, so `tb_next` is non-`None` for body errors; and the boundary test the finding
claimed was missing already exists (`test_factory.py:509`). The only true edge is a
C-implemented builtin used as a creator failing internally on type — contrived, and not the
mechanism the finding described.

---

## Additional observations (main-agent read-through; outside workflow finder coverage)

### A-1 — `Factory.resolve` compiles kwargs / resolves deps outside the lock — LOW (GIL-benign) — open
**Location:** `factory.py` (`resolve` / `_resolve_kwargs`).
Only instance creation is lock-guarded (double-checked locking). Two threads building the
same singleton both run `_ensure_kwargs_cached` (mutating the shared `CacheItem`'s
`kwargs_compiled`/bucket fields) and resolve dependencies before the lock. The operation is
idempotent and CPython-GIL-safe in practice, but it is a genuine data race on the struct
fields. **Fix (optional):** compile/partition under the lock for cached providers, or accept
and document as GIL-benign.

### A-2 — `__enter__` silently re-opens a closed container — LOW — open
**Location:** `container.py:240`.
`__enter__` sets `self.closed = False`, so re-entering a closed container reopens it (cache
cleared on close → singletons rebuild). Likely intended for context-manager reuse, but it
means a use-after-close via `with` won't error. Note: the 2026-06-12 audit's X-1 already
refined close/reopen semantics; this is the `__enter__`-specific facet. **Fix (optional):**
document the reopen semantics explicitly, or guard against reopening after an explicit
`close_*`.
