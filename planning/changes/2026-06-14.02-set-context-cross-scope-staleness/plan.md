---
status: shipped
date: 2026-06-14
slug: set-context-cross-scope-staleness
spec: design.md
pr: 216
---

# set-context-cross-scope-staleness — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ContextProvider`-backed factory parameters resolve live so a
late `set_context` always propagates (cross-scope, non-cached), delete the now
dead `invalidate_compiled_kwargs` machinery, and document the cached-factory
limitation.

**Spec:** [`design.md`](./design.md)

**Branch:** `fix/set-context-cross-scope-staleness`

**Commit strategy:** Per-task commits.

---

### Task 1: Write the failing regression tests first (TDD)

**Files:**
- Modify: `tests/providers/test_context_provider.py`
- Modify: `tests/providers/test_factory.py` (if a factory-shaped case fits better there)

Encode the bug and the documented limitation as tests before touching source, so
the fix is proven and the singleton boundary is pinned.

- [ ] **Step 1: Add the core cross-scope regression test**

  `APP ContextProvider` (defaulted param) + `REQUEST Factory(ctx: Ctx | None =
  None)`; build request child; `resolve` → assert `None`; `app.set_context(Ctx,
  value)`; `resolve` again from the **same** child → assert `value`.

- [ ] **Step 2: Add nullable + required cross-scope variants**

  Nullable param → `None` then `value`. Required (non-nullable, no default) →
  first resolve raises `ArgumentResolutionError`; after `set_context`, resolve
  returns the value.

- [ ] **Step 3: Add the cached-factory limitation test**

  `Factory(cache_settings=CacheSettings())` reading a `ContextProvider`; resolve,
  `set_context`, resolve again → assert the value is **unchanged** (singleton not
  rebuilt). Comment it as documenting intentional caching semantics.

- [ ] **Step 4: Add the override-of-context-param test**

  Override a context-backed param via `container.override(...)`, including setting
  the override after first resolve; assert the override is returned.

- [ ] **Step 5: Confirm the new tests fail on current `main`**

  ```bash
  just test tests/providers/test_context_provider.py
  ```
  Expected: the core/nullable/required/override tests FAIL (staleness); the
  cached-limitation and existing same-scope tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add tests/
  git commit -m "test: cover set_context cross-scope staleness (failing)

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 2: Resolve context params live; add the `context_kwargs` bucket

**Files:**
- Modify: `modern_di/providers/factory.py`
- Modify: `modern_di/registries/cache_registry.py`

Move context-value resolution from compile time to resolve time.

- [ ] **Step 1: Add `context_kwargs` field to `CacheItem`**

  `context_kwargs: dict[str, tuple[AbstractProvider[typing.Any], SignatureItem]]
  = field(default_factory=dict)` in `cache_registry.py`.

- [ ] **Step 2: Restructure compilation to produce three buckets**

  Rework `_compile_kwargs` / `_ensure_kwargs_cached` so a parameter whose
  `_find_dep_provider` result is a `ContextProvider` (and is not shadowed by a
  `self._kwargs` entry) goes into `context_kwargs` carrying `(provider, item)` —
  **without** reading the context value or baking skip/`None`/raise. Non-context
  providers → `provider_kwargs`; literals + `self._kwargs` → `static_kwargs`;
  no-provider default/`None`/raise stays compile-time.

- [ ] **Step 3: Factor the `ArgumentResolutionError` construction into one helper**

  Single definition shared by the compile-time (no-provider) raise and the new
  resolve-time (context-unset, required) raise.

- [ ] **Step 4: Resolve `context_kwargs` live in `Factory.resolve`**

  After `static_kwargs`/`provider_kwargs`, iterate `context_kwargs`: check
  overrides first (mirroring `resolve_provider`), then `provider._find_context_
  value(container)`; apply value / default-skip / `None` / raise per the spec.

- [ ] **Step 5: Run the suite**

  ```bash
  just test
  ```
  Expected: all Task 1 tests now pass; nothing else regresses.

- [ ] **Step 6: Commit**

  ```bash
  git add modern_di/providers/factory.py modern_di/registries/cache_registry.py
  git commit -m "fix: resolve ContextProvider params live so late set_context propagates

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 3: Delete `invalidate_compiled_kwargs`

**Files:**
- Modify: `modern_di/registries/cache_registry.py`
- Modify: `modern_di/container.py`

The compiled memo is now matching-only and never goes stale.

- [ ] **Step 1: Remove `CacheRegistry.invalidate_compiled_kwargs`**

  Delete the method (`cache_registry.py:61-65`).

- [ ] **Step 2: Simplify `Container.set_context`**

  Drop the `self.cache_registry.invalidate_compiled_kwargs()` call; `set_context`
  becomes just `self.context_registry.set_context(context_type, obj)`.

- [ ] **Step 3: Run the suite + lint**

  ```bash
  just test && just lint-ci
  ```
  Expected: green, 100% coverage (confirm no now-uncovered lines from the
  deletion).

- [ ] **Step 4: Commit**

  ```bash
  git add modern_di/registries/cache_registry.py modern_di/container.py
  git commit -m "refactor: drop now-dead invalidate_compiled_kwargs

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 4: Document the cached-factory limitation

**Files:**
- Modify: `modern_di/container.py` (`set_context` docstring)
- Modify: `modern_di/providers/context_provider.py` (docstring, if needed)

- [ ] **Step 1: Rewrite the `set_context` docstring**

  Scope the guarantee: late context is picked up by subsequent resolves of
  **non-cached** providers; a cached (singleton) provider's instance is fixed at
  first build and is not rebuilt by a later `set_context`. Remove any wording
  implying global/unconditional pickup.

- [ ] **Step 2: Lint**

  ```bash
  just lint-ci
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add modern_di/container.py modern_di/providers/context_provider.py
  git commit -m "docs: scope set_context guarantee to non-cached providers

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 5: Promote to `architecture/` and ship the bundle

**Files:**
- Modify: `architecture/containers.md`, `architecture/resolution.md`
- Modify: `planning/README.md` (Index: Active → Archived)
- Move: this bundle `active/` → `archive/`

- [ ] **Step 1: Update the architecture truth home**

  `containers.md`: drop the `invalidate_compiled_kwargs` description; restate the
  compiled memo as type→provider *matching* only. `resolution.md`: state that
  `ContextProvider` values are resolved live on every resolve.

- [ ] **Step 2: Verify docs build**

  ```bash
  uv run mkdocs build --strict
  ```

- [ ] **Step 3: Open the PR**

  Push the branch and open a PR summarizing the fix + the documented limitation;
  link the audit finding.

- [ ] **Step 4: On merge — archive the bundle**

  Set `status: shipped`, fill `pr:` and `outcome:` in both files; move the folder
  to `planning/changes/`; move its Index line from **Active** to
  **Archived** in `planning/README.md`.
