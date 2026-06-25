---
status: shipped
date: 2026-06-14
slug: audit-doc-rulings-batch1
summary: Action batch-1 rulings from the 2026-06-14 deep audit (B-4 pin, B-5/S-1/S-2 doc notes, A-1 comment + nogil caveat; A-2 closed). Doc/test/comment-only. Plan-only; spec = the audit report.
spec: ../../../audits/2026-06-14-deep-audit-report.md
pr: 217
outcome: Actioned batch-1 doc/test/comment rulings from 2026-06-14 deep audit (B-4 pin, B-5/S-1/S-2 doc notes, A-1 comment + nogil caveat; A-2 closed with no action); shipped in PR #217.
---

# audit-doc-rulings-batch1 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Action the approved batch-1 rulings from the 2026-06-14 deep audit —
the doc/test/comment-only findings (**B-4, B-5, S-1, S-2, A-1**); **A-2** closes
with no action. No production behavior changes.

**Spec:** [2026-06-14 deep audit report](../../../audits/2026-06-14-deep-audit-report.md)

**Branch:** `fix/audit-doc-rulings-batch1`

**Commit strategy:** Single commit (batch of trivial doc/test edits).

**Rulings (approved 2026-06-14):**

| ID | Ruling | Action |
|----|--------|--------|
| B-4 | document (done) + pin | Add a test asserting an override resolves a deeper-scoped provider from a shallower container |
| B-5 | document | Note the union parameterized-generic → origin degradation asymmetry |
| S-1 | document | Note that runtime resolution has no cycle guard; use `validate()` in dev |
| S-2 | document | Note wrapped creator/finalizer error text; don't echo raw exceptions to untrusted clients |
| A-1 | accept + comment | Comment the GIL-benign compile-outside-lock; record the free-threading caveat in `deferred.md` |
| A-2 | close | Already documented intentional (2026-06-12 X-1); no action |

---

### Task 1: Pin B-4 (override bypasses scope validation)

**Files:**
- Modify: `tests/providers/test_factory.py`

- [ ] **Step 1:** Add a test: a REQUEST-scoped factory raises `ScopeNotInitializedError`
  on `app_container.resolve(...)`; after `app_container.override(provider, mock)` the same
  call returns the mock. Reference `architecture/testing-and-overrides.md` "Scope behaviour
  under overrides" in a comment.
- [ ] **Step 2:** `just test tests/providers/test_factory.py` — passes.

### Task 2: Document B-5, S-1, S-2

**Files:**
- Modify: `architecture/resolution.md` (B-5 — union origin-degradation note)
- Modify: `architecture/validation.md` (S-1 — runtime has no cycle guard; use `validate()`)
- Modify: `docs/providers/errors-and-exceptions.md` (S-2 — wrapped error text note)

- [ ] **Step 1:** B-5 — in the union/`_find_dep_provider` discussion, note that a
  parameterized generic inside a union degrades to its origin for matching (whereas a bare
  single parameterized generic is rejected at declaration).
- [ ] **Step 2:** S-1 — note that runtime resolution does not detect cycles (raises
  `RecursionError`); use `validate=True` / `container.validate()` in development.
- [ ] **Step 3:** S-2 — note that messages may embed wrapped creator/finalizer exception
  text; applications must not echo raw exceptions to untrusted clients.

### Task 3: A-1 comment + deferred caveat

**Files:**
- Modify: `modern_di/providers/factory.py` (comment at the compile site)
- Modify: `planning/deferred.md` (free-threading caveat)

- [ ] **Step 1:** Add a comment explaining the kwargs compilation runs outside the lock and
  why that is safe under the GIL (deterministic, idempotent buckets).
- [ ] **Step 2:** Add a `deferred.md` entry: under free-threaded (nogil) CPython,
  `kwargs_compiled` set after the bucket rebinds could expose stale-empty buckets; revisit if
  free-threading support becomes a goal.

### Task 4: Verify and ship

- [ ] **Step 1:** `just test-ci` — 100% coverage, green.
- [ ] **Step 2:** `just lint-ci` — clean.
- [ ] **Step 3:** `uv run mkdocs build --strict` — OK.
- [ ] **Step 4:** Commit, push, open PR. On merge: set `status: shipped` + `pr:`, move bundle
  to `archive/`, move Index line in `planning/README.md`, and mark B-4/B-5/S-1/S-2/A-1/A-2 as
  resolved in the audit report's Status line.
