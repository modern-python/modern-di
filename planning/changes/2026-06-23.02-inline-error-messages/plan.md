---
date: 2026-06-23
slug: inline-error-messages
spec: design.md
---

# inline-error-messages — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inline the 17 single-use error templates into their exception classes,
relocate the suggestion vocabulary to its two real consumers, and delete
`modern_di/errors.py` — with every rendered message byte-identical.

**Spec:** [`design.md`](./design.md)

**Branch:** `refactor/inline-error-messages`

**Commit strategy:** Per-task commits; suite stays green after each task.

---

### Task 0: Capture the baseline message dump (guard)

**Files:**
- Create (scratch, gitignored): a throwaway dump script under the session scratch dir.

Build the before/after guard from design §Testing **before** any change.

- [ ] **Step 1: Write a dump script**

  Construct every concrete exception class in `modern_di/exceptions.py` with
  representative args (cover both `ArgumentResolutionError` branches: `arg_type`
  set, `member_types` set, and unannotated; and the with-suggestions paths of
  `ProviderNotRegisteredError`/`ArgumentResolutionError`). Print
  `type(e).__name__` + `str(e)` for each. Keep it outside the repo tree (e.g.
  under `$TMPDIR`).

- [ ] **Step 2: Capture baseline on the current tip**

  Run the script on the branch point (pre-change) and save output to
  `$TMPDIR/err-before.txt`. Do not commit anything.

---

### Task 1: Inline `exceptions.py` templates + `SUGGESTION_HEADER` constant

**Files:**
- Modify: `modern_di/exceptions.py`

Per design §1–§2.

- [ ] **Step 1: Add the `SUGGESTION_HEADER` constant**

  Define `SUGGESTION_HEADER = "Did you mean:"` as a module-level constant in
  `exceptions.py` (copy the exact literal from `errors.py`).

- [ ] **Step 2: Inline each single-use template as an f-string**

  For every `errors.X.format(...)` in `exceptions.py`, replace with an f-string
  literal carrying the **exact** text from `errors.py`. Preserve multi-line
  messages via parenthesized implicit concatenation. Update the two
  suggestions-block sites to use the local `SUGGESTION_HEADER`.

- [ ] **Step 3: Drop the `errors` import**

  Remove `from modern_di import errors`. Confirm no `errors.` references remain:
  `grep -n "errors\." modern_di/exceptions.py` → empty.

- [ ] **Step 4: Verify**

  `uv run ruff check modern_di/exceptions.py && uv run ty check modern_di` clean.
  `just test tests/` — full suite green (errors.py still exists; only this module
  changed).

- [ ] **Step 5: Commit**

  ```bash
  git add modern_di/exceptions.py
  git commit -m "refactor: inline error messages into their exception classes

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 2: Inline the suggestion line-formats into `providers_registry.py`

**Files:**
- Modify: `modern_di/registries/providers_registry.py`

Per design §3.

- [ ] **Step 1: Inline `SUGGESTION_SUBCLASS`/`BASECLASS`/`SIMILAR`**

  Replace the three `errors.SUGGESTION_*.format(...)` calls (`_hierarchy_hint`,
  `build_suggestions`) with f-strings carrying the exact line format.

- [ ] **Step 2: Drop the `errors` import**

  Change `from modern_di import errors, exceptions, types` to
  `from modern_di import exceptions, types`. Confirm `grep -n "errors\."
  modern_di/registries/providers_registry.py` → empty.

- [ ] **Step 3: Verify**

  `uv run ruff check modern_di/registries/providers_registry.py && uv run ty check
  modern_di` clean. `just test tests/` green.

- [ ] **Step 4: Commit**

  ```bash
  git add modern_di/registries/providers_registry.py
  git commit -m "refactor: inline suggestion line-formats into the providers registry

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 3: Delete `errors.py` and fix doc references

**Files:**
- Delete: `modern_di/errors.py`
- Modify: `CLAUDE.md` (and any `architecture/` file that names `errors.py`)

- [ ] **Step 1: Confirm no remaining importers**

  `grep -rn "modern_di.errors\|from modern_di import errors\|errors\." modern_di`
  → no hits. Then `git rm modern_di/errors.py`.

- [ ] **Step 2: Fix doc references**

  Remove the `modern_di/errors.py` line from `CLAUDE.md`'s "Key files". `grep -rn
  "errors.py" CLAUDE.md architecture/` and update/remove each stale mention.

- [ ] **Step 3: Verify import + suite**

  `uv run python -c "import modern_di; print('ok')"` → `ok`. `just test-ci` —
  full suite green at **100% coverage**.

- [ ] **Step 4: Commit**

  ```bash
  git add -A
  git commit -m "refactor: delete the errors.py message-template seam

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 4: Prove byte-identical messages + final gates

**Files:** none (verification only)

- [ ] **Step 1: After-dump + diff**

  Run the Task 0 dump script on the branch HEAD → `$TMPDIR/err-after.txt`.
  `diff $TMPDIR/err-before.txt $TMPDIR/err-after.txt` → **empty** (every message
  byte-identical). A non-empty diff blocks the change.

- [ ] **Step 2: Full gates**

  `just test-ci` (225 tests, 100% coverage) and `just lint-ci` clean (`eof-fixer`,
  `ruff format --check`, `ruff check`, `ty check`).

- [ ] **Step 3: Open the PR**

  Branch off `origin/main` (sync first). Push and open a PR titled `refactor:
  inline error messages and delete the errors.py seam`, linking this bundle. On
  ship set `status: shipped` + `pr:` + `outcome:` in the design front-matter and
  run `just index`.
