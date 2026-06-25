---
status: shipped
date: 2026-06-14
slug: audit-fixes-batch3
summary: R-1 (`AbstractProvider.display_name` dedupes the bound-type-or-repr idiom across ~5 sites) + R-2 minimal (public `fetch_context_value`, drop the `SLF001` reach-in). Plan-only; spec = the audit report.
spec: ../../../audits/2026-06-14-deep-audit-report.md
outcome: Added AbstractProvider.display_name deduping R-1 (~5 sites) and public fetch_context_value dropping the SLF001 reach-in (R-2) from 2026-06-14 deep audit; shipped in PR #219.
---

# audit-fixes-batch3 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Refactor batch from the 2026-06-14 deep audit — **R-1** (dedupe the
provider display-name idiom) and **R-2** (drop the `SLF001` private-method
reach-in). Behavior-preserving; no new tests (existing suite + 100% coverage
exercise all branches).

**Spec:** [2026-06-14 deep audit report](../../../audits/2026-06-14-deep-audit-report.md)

**Branch:** `fix/audit-fixes-batch3`

**Commit strategy:** Single commit.

## Design decision (R-2 API shape, approved 2026-06-14)

R-2 was scoped to the **minimal** option: rename `ContextProvider._find_context_value` →
public `fetch_context_value` (removing the `SLF001` noqa at the Factory call site), but **keep**
`isinstance(provider, ContextProvider)` for compile-time routing — an `isinstance` against a
concrete sibling provider is acceptable, and this keeps new public surface to one method. The
fuller "ClassVar capability flag + base method" decoupling was considered and declined. Note:
the `enforces_dependency_scope` ClassVar referenced in the 2026-06-12 audit is not in the live
code (superseded by `effective_scope()`), so the established extension pattern is method/property
overrides on `AbstractProvider`.

R-4/R-5/R-6 are **deferred** (marginal internal tidiness; the compile vs. validate predicates in
Factory genuinely diverge, so R-5 cannot be cleanly unified).

---

### Task 1: R-1 — `display_name` on AbstractProvider

**Files:**
- Modify: `modern_di/providers/abstract.py` (base `display_name` property)
- Modify: `modern_di/providers/factory.py` (override + use in `_resolution_step`)
- Modify: `modern_di/providers/alias.py`, `modern_di/container.py`, `modern_di/exceptions.py` (use it)

- [x] **Step 1:** Add `AbstractProvider.display_name` → `bound_type.__name__ if bound_type else repr(self)`.
- [x] **Step 2:** Override in `Factory` to fall back to the creator's `__name__`.
- [x] **Step 3:** Replace the duplicated idiom at the ~5 sites (`_resolution_step` in Factory and
  Alias, the cycle-path list in `container.validate()`, and both names in
  `InvalidScopeDependencyError`).

### Task 2: R-2 (minimal) — public `fetch_context_value`

**Files:**
- Modify: `modern_di/providers/context_provider.py` (rename method; update internal `resolve`)
- Modify: `modern_di/providers/factory.py` (call public method; drop `# noqa: SLF001`)

- [x] **Step 1:** Rename `_find_context_value` → `fetch_context_value` (public).
- [x] **Step 2:** Update `Factory._resolve_context_value` to call it without the SLF001 suppression.

### Task 3: Verify and ship

- [ ] **Step 1:** `just test-ci` — 100% coverage, green.
- [ ] **Step 2:** `just lint-ci` — clean (the SLF001 noqa is gone).
- [ ] **Step 3:** Commit, push, open PR. On merge: archive bundle (`status: shipped` + `pr:`),
  move Index line, mark R-1/R-2 resolved in the audit report Status line.
