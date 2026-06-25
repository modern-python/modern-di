---
date: 2026-06-14
slug: audit-fixes-batch2
summary: B-3 (gapped custom-enum child-scope derivation) + P-1 (drop the per-resolve throwaway `CacheItem` alloc via a `get` fast path, keeping atomic `setdefault` on creation). Plan-only; spec = the audit report.
spec: ../../../audits/2026-06-14-deep-audit-report.md
outcome: Fixed B-3 (gapped custom-enum child-scope derivation) and P-1 (eliminate per-resolve throwaway CacheItem alloc via get fast path) from 2026-06-14 deep audit; shipped in PR #218.
---

# audit-fixes-batch2 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Land the two real, low-risk code fixes from the 2026-06-14 deep audit —
**B-3** (gapped custom-enum child-scope derivation) and **P-1** (avoid the
per-resolve throwaway `CacheItem` allocation).

**Spec:** [2026-06-14 deep audit report](../../../audits/2026-06-14-deep-audit-report.md)

**Branch:** `fix/audit-fixes-batch2`

**Commit strategy:** Single commit.

---

### Task 1: B-3 — derive child scope from the next-deeper enum member

**Files:**
- Modify: `modern_di/container.py` (`build_child_container`, `scope is None` branch)
- Modify: `tests/test_custom_scope.py`

`scope = self.scope.__class__(self.scope.value + 1)` assumes contiguous values and raises
`MaxScopeReachedError` for gapped custom enums (`TENANT=6, JOB=10`). Derive the smallest
member `> self.scope` instead.

- [x] **Step 1:** Failing tests — gapped auto-derive returns the next member;
  deepest-member still raises `MaxScopeReachedError`.
- [x] **Step 2:** Replace `value + 1` with `min(m for m in type(self.scope) if m > self.scope)`,
  raising `MaxScopeReachedError` when none deeper.
- [ ] **Step 3:** `just test tests/test_custom_scope.py` — green.

### Task 2: P-1 — get-then-set in `fetch_cache_item`

**Files:**
- Modify: `modern_di/registries/cache_registry.py`

`setdefault(id, CacheItem(...))` evaluates the default eagerly, so every cache hit (every
resolve after the first) constructs and discards a `CacheItem` (+2 dicts). Add a `get` fast
path that returns an existing item with no allocation, but **keep `setdefault` on the creation
path**: fetch runs outside the container lock, and `setdefault`'s atomicity is load-bearing —
concurrent first-resolvers of a singleton must share one `CacheItem` (the cache and its
double-checked lock live on that object). A plain `get`-then-set would break that. No new test
(behavior-identical; existing suite + 100% coverage exercise both paths).

- [x] **Step 1:** Add a `get` fast path; retain atomic `setdefault` for creation.

### Task 3: Verify and ship

- [ ] **Step 1:** `just test-ci` — 100% coverage, green.
- [ ] **Step 2:** `just lint-ci` — clean.
- [ ] **Step 3:** Commit, push, open PR. On merge: archive bundle (`status: shipped` + `pr:`),
  move Index line in `planning/README.md`, mark B-3/P-1 resolved in the audit report Status line.
