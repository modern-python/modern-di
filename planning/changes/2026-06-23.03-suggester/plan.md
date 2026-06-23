---
status: draft
date: 2026-06-23
slug: suggester
spec: suggester
pr: null
---

# suggester — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the shared `difflib` fuzzy-match into a directly-testable
`modern_di/suggester.py`, delegate both call sites to it, and home the `0.6`
cutoff once — with suggestion behavior unchanged.

**Spec:** [`design.md`](./design.md)

**Branch:** `refactor/suggester`

**Commit strategy:** Per-task commits; suite green after each task.

---

### Task 1: Create `suggester.py` with direct tests (TDD)

**Files:**
- Create: `modern_di/suggester.py`
- Create: `tests/test_suggester.py`

Per design §1 and §Testing. The module is pure — write its tests first.

- [ ] **Step 1: Write `tests/test_suggester.py` (RED)**

  Cover: exact match; fuzzy hit ≥ cutoff returned; near-miss < cutoff excluded;
  `n` cap; best-first ordering; empty candidates → `[]`; default cutoff `0.6`
  boundary. Annotate all test args + returns. Run → fails (module absent).

- [ ] **Step 2: Write `modern_di/suggester.py` (GREEN)**

  `close_matches(target, candidates, *, n, cutoff=0.6)` per design §1.

- [ ] **Step 3: Verify**

  `just test tests/test_suggester.py` green; `uv run ruff check modern_di/suggester.py tests/test_suggester.py && uv run ty check modern_di` clean (run `ruff format` and keep its result).

- [ ] **Step 4: Commit**

  ```bash
  git add modern_di/suggester.py tests/test_suggester.py
  git commit -m "feat: add suggester.close_matches with direct tests

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 2: Delegate `providers_registry` to the suggester

**Files:**
- Modify: `modern_di/registries/providers_registry.py`

Per design §2.

- [ ] **Step 1: Delegate + drop the local cutoff**

  Replace the inline `difflib.get_close_matches(...)` in `build_suggestions` with
  `suggester.close_matches(requested_name, name_to_provider.keys(), n=remaining)`.
  Remove `import difflib` and the `_SIMILARITY_CUTOFF` constant. Add `from
  modern_di import suggester` (or `from modern_di.suggester import close_matches`
  — match neighbouring import style). Keep `_MAX_SUGGESTIONS` and `_hierarchy_hint`.

- [ ] **Step 2: Verify**

  `grep -n "difflib\|_SIMILARITY_CUTOFF" modern_di/registries/providers_registry.py` → empty.
  `just test tests/test_suggestions.py tests/registries/test_providers_registry.py` green; ruff + ty clean.

- [ ] **Step 3: Commit**

  ```bash
  git add modern_di/registries/providers_registry.py
  git commit -m "refactor: route registry suggestions through the suggester

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 3: Delegate `factory` to the suggester

**Files:**
- Modify: `modern_di/providers/factory.py`

Per design §3.

- [ ] **Step 1: Delegate + drop the import**

  Replace `difflib.get_close_matches(bad, known, n=1)` in
  `_validate_kwargs_against_signature` with `suggester.close_matches(bad, known,
  n=1)`. Remove `import difflib` (its only use). Add the suggester import.

- [ ] **Step 2: Verify**

  `grep -n "difflib" modern_di/providers/factory.py` → empty.
  `just test tests/providers/test_factory.py` green; ruff + ty clean.

- [ ] **Step 3: Commit**

  ```bash
  git add modern_di/providers/factory.py
  git commit -m "refactor: route factory kwarg suggestions through the suggester

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 4: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (add `modern_di/suggester.py` to Key files)

- [ ] **Step 1: No stray difflib**

  `grep -rn "difflib" modern_di` → only `modern_di/suggester.py`.

- [ ] **Step 2: Full gates**

  `just test-ci` — full suite green at **100% coverage**. `just lint-ci` clean
  (`eof-fixer`, `ruff format --check`, `ruff check --no-fix`, `ty check` — run the
  whole-tree commands CI runs, not just scoped, to catch any drift).

- [ ] **Step 3: Docs**

  Add `modern_di/suggester.py` to the `CLAUDE.md` "Key files" list. Commit.

- [ ] **Step 4: Open the PR**

  Sync off `origin/main`, push, open a PR titled `refactor: extract the suggester
  fuzzy-match module`, linking this bundle. On ship set `status: shipped` + `pr:`
  + `outcome:` in the design front-matter and run `just index`.
