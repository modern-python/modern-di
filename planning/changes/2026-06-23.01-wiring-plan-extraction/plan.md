# wiring-plan-extraction — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the kwarg-wiring decision out of `Factory` into a pure
`WiringPlan` module so the partition, the absent-value table, and the
error-construction site each exist once — with no change to behavior, coverage,
or per-resolve cost.

**Spec:** [`design.md`](./design.md)

**Branch:** `refactor/wiring-plan-extraction`

**Commit strategy:** Per-task commits; the suite must be green at task 3 onward.

---

### Task 1: Create the `wiring` module

**Files:**
- Create: `modern_di/wiring.py`

Introduce `_Absent`, `absent_disposition`, `find_dep_provider`, and
`WiringPlan.build` as a pure unit — nothing imports it yet.

- [ ] **Step 1: Write `modern_di/wiring.py`**

  Per design §1–§2: `_Absent` enum (`OMIT`/`NULL`/`UNWIRABLE`);
  `absent_disposition(item)` (default → OMIT, nullable → NULL, else UNWIRABLE);
  `find_dep_provider(registry, owner, item)` (moved verbatim from
  `Factory._find_dep_provider`, self-exclusion via `provider is owner`);
  `WiringPlan` frozen dataclass with `provider_kwargs` / `static_kwargs` /
  `context_kwargs` / `dependencies` / `issues` and the `build` classmethod.
  Import `ContextProvider` as `factory.py` does; keep `Factory` and
  `ProvidersRegistry` under `TYPE_CHECKING`. `build` calls
  `owner._argument_resolution_error(...)` with `# noqa: SLF001`.

- [ ] **Step 2: Smoke-import to catch cycles**

  ```bash
  uv run python -c "import modern_di, modern_di.wiring; print('ok')"
  ```
  Expect `ok`. If it raises an ImportError cycle, move `Factory`/registry imports
  under `TYPE_CHECKING` (per design risk note).

- [ ] **Step 3: Commit**

  ```bash
  git add modern_di/wiring.py
  git commit -m "refactor: add WiringPlan module (unused)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 2: Store one plan on `CacheItem`

**Files:**
- Modify: `modern_di/registries/cache_registry.py`

Replace the four compiled-kwargs fields with a single `wiring_plan` slot.

- [ ] **Step 1: Edit `CacheItem`**

  Drop `kwargs_compiled`, `provider_kwargs`, `static_kwargs`, `context_kwargs`
  (`cache_registry.py:13-17`); add `wiring_plan: "WiringPlan | None" = None` with
  a `TYPE_CHECKING` import of `WiringPlan` from `modern_di.wiring`. Leave
  `cache`, `finalized`, `settings`, and the `_clear`/`close_*` methods untouched.

- [ ] **Step 2: Confirm it imports**

  ```bash
  uv run python -c "from modern_di.registries.cache_registry import CacheItem; print('ok')"
  ```
  Expect `ok`. (Suite is red until Task 3 — that is expected.)

- [ ] **Step 3: Commit**

  ```bash
  git add modern_di/registries/cache_registry.py
  git commit -m "refactor: store a single WiringPlan on CacheItem

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 3: Rewire `Factory` onto the plan

**Files:**
- Modify: `modern_di/providers/factory.py`

`Factory` reads the plan for resolve and validate; the duplicated traversals and
the moved matcher are deleted.

- [ ] **Step 1: Add `_ensure_plan`, delete `_ensure_kwargs_cached`**

  Build + memoize `cache_item.wiring_plan` via `WiringPlan.build` (design §3).

- [ ] **Step 2: Point `resolve` / `_resolve_kwargs` at the plan**

  Read `plan.provider_kwargs` / `static_kwargs` / `context_kwargs` (loop
  unchanged); raise `plan.issues[0]` if any before building kwargs, matching the
  current eager raise.

- [ ] **Step 3: Share the absent table in the context path**

  `_resolve_context_value` keeps its live container/override/scope logic but its
  absent branch calls `absent_disposition(item)` (design §3) instead of
  re-spelling default/`None`/raise.

- [ ] **Step 4: Make `get_dependencies` / `iter_validation_issues` plan-readers**

  Both build a transient plan and return `.dependencies` / `.issues`
  respectively (design §4).

- [ ] **Step 5: Delete the now-dead code**

  Remove `_compile_kwargs`, `_find_dep_provider` (moved to `wiring`), and any
  helper left unused. Keep `_argument_resolution_error` (now called from
  `wiring.build` and the context path).

- [ ] **Step 6: Green suite, unchanged**

  ```bash
  just test
  ```
  All existing tests pass **without edits**. If any test needs changing, stop —
  it signals a behavior change; reconcile against design §3/§4 before proceeding.

- [ ] **Step 7: Commit**

  ```bash
  git add modern_di/providers/factory.py
  git commit -m "refactor: resolve and validate Factory via WiringPlan

  Collapses _compile_kwargs, get_dependencies, iter_validation_issues, and
  the context absent-value table into one plan + one shared helper.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 4: Direct tests for the plan

**Files:**
- Create: `tests/test_wiring.py`

Exercise `WiringPlan.build` and `absent_disposition` with no `Container` (design
§Testing 1–4).

- [ ] **Step 1: Write the tests**

  Partitioning into the four buckets; `issues` populated without raising;
  `dependencies` excludes static-supplied providers; `absent_disposition`
  precedence table. Annotate all test args (per repo convention).

- [ ] **Step 2: Run them**

  ```bash
  just test tests/test_wiring.py
  ```
  All pass.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/test_wiring.py
  git commit -m "test: cover WiringPlan.build and absent_disposition directly

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 5: Verify coverage, lint, and the full graph

**Files:** none (verification only)

- [ ] **Step 1: Full suite + 100% coverage**

  ```bash
  just test
  ```
  Green; coverage gate (100% line) holds. If `wiring.py` shows an uncovered
  branch, add the missing direct test in `test_wiring.py`.

- [ ] **Step 2: Lint clean**

  ```bash
  just lint-ci
  ```
  No `SLF001` escapes beyond the annotated `_argument_resolution_error` call; `ty`
  clean.

- [ ] **Step 3: Open the PR**

  Branch off `origin/main` is current; push and open a PR titled
  `refactor: extract WiringPlan from Factory`, linking this bundle. On ship,
  hand-edit `architecture/resolution.md` + `architecture/providers.md` and set
  `status: shipped` + `pr:` + `outcome:` in the design front-matter, then run
  `just index`.
