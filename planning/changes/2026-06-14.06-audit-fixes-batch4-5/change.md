---
status: shipped
date: 2026-06-14
slug: audit-fixes-batch4-5
summary: Final audit cleanup: test hardening (P-6 compile-once pin, R-3 behavioral singleton assert, X-2 structured suggestion/path asserts) + DX/docs (X-3 exception docstrings, X-4 `exceptions` export, X-5 `ResolutionStep` docs). Closes every actionable finding. Plan-only; spec = audit report.
spec: ../../../audits/2026-06-14-deep-audit-report.md
pr: 220
outcome: Closed every actionable 2026-06-14 audit finding (P-6/R-3/X-2 test hardening; X-3/X-4/X-5 DX/docs); only won't-fix R-4/R-5/R-6 and the A-1 nogil follow-up remain.
---

# audit-fixes-batch4-5 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Clear the remaining actionable low-severity findings from the 2026-06-14 deep
audit — test hardening (**P-6, R-3, X-2**) and DX/docs (**X-3, X-4, X-5**).

**Spec:** [2026-06-14 deep audit report](../../../audits/2026-06-14-deep-audit-report.md)

**Branch:** `fix/audit-fixes-batch4-5`

**Commit strategy:** Two commits — (1) test hardening, (2) DX/docs.

**Scope notes:** X-2 and R-3 are deliberately **surgical** — the verifier defended exact-match
asserts as a useful DX-regression guard for this library, so only the genuinely brittle cases are
changed (the `<locals>`-coupled typo message and the exact-indentation dependency tree for X-2;
the one white-box assert with a clear behavioral surface for R-3). The remaining exact-match and
white-box asserts are left as intentional guards.

---

### Task 1 (commit 1): Test hardening — P-6, R-3, X-2

**Files:**
- Modify: `tests/providers/test_factory.py` (P-6)
- Modify: `tests/providers/test_singleton.py` (R-3)
- Modify: `tests/test_suggestions.py`, `tests/test_dependency_path.py` (X-2)

- [x] **P-6:** add `test_compile_kwargs_is_memoized_across_resolves` — spies on
  `Factory._compile_kwargs`, asserts it runs once per provider across two resolves (pins the
  compile-once invariant).
- [x] **R-3:** rewrite the `test_app_singleton` `cache_item.cache is not UNSET` check into a
  behavioral reopen assertion (`clear_cache=False` instance survives close and is returned again
  after reopen). Other white-box asserts (async-finalizer-in-sync-close; failed-creation
  `cached_count`) are intentional and already commented.
- [x] **X-2:** `test_typo_suggestion` asserts `exc.suggestions` + message substrings instead of the
  full rendered string (drops the brittle `<locals>.Repostory` repr); `test_chain_appears_…`
  keeps the structured `dependency_path` assert and checks the rendered tree via substrings.

### Task 2 (commit 2): DX/docs — X-3, X-4, X-5

**Files:**
- Modify: `modern_di/exceptions.py` (X-3 + X-5 docstrings)
- Modify: `modern_di/__init__.py` (X-4)
- Modify: `docs/providers/errors-and-exceptions.md` (X-5)

- [x] **X-3:** add concise class docstrings to every concrete exception, naming its public
  inspection attributes (IDE hover).
- [x] **X-4:** explicitly `from modern_di import exceptions` and add `"exceptions"` to `__all__`.
- [x] **X-5:** docstring on `ResolutionStep` (its `scope`/`name` fields) + a doc note that
  `dependency_path` is a `list[ResolutionStep]`.

### Task 3: Verify and ship

- [x] `just test-ci` — 209 passed, 100% coverage.
- [x] `just lint-ci` — clean. `uv run mkdocs build --strict` — OK.
- [ ] Commit (×2), push, open PR. On merge: archive bundle (`status: shipped` + `pr:`), move
  Index line, mark P-6/R-3/X-2/X-3/X-4/X-5 resolved in the audit report Status line. This closes
  every actionable finding; only R-4/R-5/R-6 (won't-fix) and the A-1 nogil follow-up remain.
