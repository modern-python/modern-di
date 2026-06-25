---
status: shipped
date: 2026-06-12
slug: code-docs-audit
spec: design.md
---

# Code & Docs Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a severity-ranked findings report covering bugs, doc/code drift, internals quality, API/DX, and docs completeness for `modern-di` — no fixes applied.

**Architecture:** Sequential audit passes (baseline → code → tests → docs), each appending findings to a single report at `planning/audits/2026-06-12-code-docs-audit-report.md` using a fixed finding format. Each pass commits the report increment so progress is durable. Spec: `docs/superpowers/specs/2026-06-12-code-docs-audit-design.md`.

**Tech Stack:** `just` + `uv` + `pytest`; Read/Grep for inspection; `uv run python` scratch scripts to probe edge cases and execute doc examples.

**Important:** This is an audit, not a build. "TDD" here means: every Bug finding must be backed by either a failing probe script you actually ran, or a precise code-path trace with `file:line`. Never report a bug you haven't verified. Suspicions that resist verification go in as Quality findings explicitly marked "unverified suspicion".

---

### Task 0: Prior-audit context

**Files:**
- Read: `planning/audits/2026-06-05-bug-hunt-audit-report.md`
- Read: `docs/superpowers/specs/2026-06-12-code-docs-audit-design.md`

- [ ] **Step 1: Read the spec** so the scope and finding categories are loaded.

- [ ] **Step 2: Read the prior bug-hunt report** (2026-06-05). Note every finding it lists and its status. Rules derived from it:
  - A finding already reported there and since **fixed** (verify in current code) → do not re-report.
  - A finding reported there and still **present** → re-report, marked `(known since 2026-06-05)`.
  - The prior report's scope was bugs only; drift/DX/docs findings are all new ground.

- [ ] **Step 3: Skim recent git history for context**

Run: `git log --oneline -30`
Purpose: know what changed since 2026-06-05 (docs restructure, recipes, migration guide) — that's where fresh drift is most likely.

### Task 1: Baseline + report skeleton

**Files:**
- Create: `planning/audits/2026-06-12-code-docs-audit-report.md`
- Modify: `docs/superpowers/specs/2026-06-12-code-docs-audit-design.md` (one line: report path → `planning/audits/...` to match repo convention)

- [ ] **Step 1: Run lint baseline**

Run: `just lint-ci`
Expected: PASS. If it fails, the failure text becomes finding B-1 (category Bug, severity high) and the audit continues.

- [ ] **Step 2: Run test baseline**

Run: `just test`
Expected: PASS with coverage summary. Record the coverage percentage — Task 4 uses it. If tests fail, each failure becomes a Bug finding.

- [ ] **Step 3: Create the report skeleton**

```markdown
# Code & Docs Audit Report — 2026-06-12

**Spec:** docs/superpowers/specs/2026-06-12-code-docs-audit-design.md
**Baseline:** lint-ci PASS|FAIL, pytest PASS|FAIL (NN% coverage), at commit <sha>
**Prior audit:** planning/audits/2026-06-05-bug-hunt-audit-report.md

## Summary

(filled in Task 7)

## Findings

### Bugs
### Drift (docs vs code)
### Quality (internals)
### DX (public API)
### Docs gaps
```

Every finding uses this exact format:

```markdown
#### <ID>: <one-line title>
- **Severity:** high | medium | low
- **Evidence:** `file.py:NN` — what the code/doc actually says/does
- **Why it's a problem:** one or two sentences
- **Proposed fix:** concrete change, one or two sentences
- **Verified by:** probe script output | code-path trace | doc/code diff
```

IDs: `B-n` Bugs, `D-n` Drift, `Q-n` Quality, `X-n` DX, `G-n` Docs gaps.

- [ ] **Step 4: Fix the spec's report path** — edit the spec line `planning/2026-06-12-audit-findings.md` → `planning/audits/2026-06-12-code-docs-audit-report.md`.

- [ ] **Step 5: Commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md docs/superpowers/specs/2026-06-12-code-docs-audit-design.md
git commit -m "Audit: baseline + report skeleton"
```

### Task 2: Code audit — core

**Files:**
- Read: `modern_di/container.py`, `modern_di/scope.py`, `modern_di/group.py`, `modern_di/errors.py`, `modern_di/exceptions.py`, `modern_di/types.py`, `modern_di/types_parser.py`, `modern_di/__init__.py`
- Modify: `planning/audits/2026-06-12-code-docs-audit-report.md`

- [ ] **Step 1: Read all eight files fully.**

- [ ] **Step 2: Probe `types_parser` edge cases.** Write a scratch script `/tmp/audit_probe_parser.py` exercising at minimum these creator signatures, and run it with `uv run python /tmp/audit_probe_parser.py`:
  - `def f(x: "ForwardRef")` under `from __future__ import annotations`
  - `def f(x: int | None)` and `def f(x: typing.Optional[Svc])`
  - `def f(x: list[Svc])` and other parameterized generics
  - `def f(*args, **kwargs)` and positional-only params (`def f(x, /, y)`)
  - a class whose `__init__` is inherited from a parent
  - a creator with an unannotated parameter
  - a creator with a default value (`def f(x: Svc = sentinel)`)
  - `functools.partial` and lambdas as creators

  For each: does it raise a clear error, a confusing error, or silently misbehave? Confusing/silent → Bug finding; clear error not documented → Docs gap.

- [ ] **Step 3: Probe `Container` lifecycle edge cases** the same way (`/tmp/audit_probe_container.py`):
  - resolve after container close/exit (if a close API exists)
  - `build_child_container` skipping a scope level (APP → ACTION directly)
  - two children of the same parent — cache isolation
  - resolving a type registered in two groups passed to one container
  - `validate=True` on a graph with a cycle through an Alias or ContextProvider
  - override set on parent, resolved from child; override reset mid-life
  - concurrent `resolve` of the same cached provider from two threads (singleton race — check whether the RLock from the 2026-06-05 `singleton-rlock-plan` actually landed and works)

- [ ] **Step 4: Failure-behavior review.** For every `raise` in the eight files: is the message actionable (names the type/provider/scope involved)? Cross-check `errors.py` templates against `exceptions.py` usage — unused templates are Quality findings, formatted-wrong messages are Bugs.

- [ ] **Step 5: Internals + API lens.** Dead code (Grep each public name for callers/tests), type-hint gaps (`ty` already ran — anything it can't see), perf smells (repeated parsing per resolve vs at declaration), naming/ergonomics oddities → X findings.

- [ ] **Step 6: Append findings to report and commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit: core code pass"
```

### Task 3: Code audit — providers + registries + benchmarks

**Files:**
- Read: `modern_di/providers/*.py` (6 files), `modern_di/registries/*.py` (5 files), `benchmarks/*.py` (4 files)
- Modify: `planning/audits/2026-06-12-code-docs-audit-report.md`

- [ ] **Step 1: Read all files fully.**

- [ ] **Step 2: Probe Factory/cache/finalizer behavior** (`/tmp/audit_probe_factory.py`):
  - sync finalizer registered, container torn down → runs exactly once, LIFO order across dependent providers
  - async finalizer in a sync teardown path — what happens?
  - `CacheSettings` on a REQUEST-scoped provider resolved from two sibling REQUEST containers → two instances, not shared
  - `kwargs={}` static args colliding with a type-resolved param of the same name
  - `skip_creator_parsing=True` with missing kwargs at resolve time
  - exception raised mid-creation: is a half-built instance cached? are already-resolved deps' finalizers leaked?

- [ ] **Step 3: Probe Alias + ContextProvider + container_provider:**
  - Alias chain (alias of alias), alias to a provider at a shallower scope
  - ContextProvider resolved when context not passed → error message quality
  - context passed at APP scope vs REQUEST scope — which registry wins
  - `container_provider` resolved from a child → returns child or root?

- [ ] **Step 4: Registry lenses.** For each registry: thread safety of mutation paths, behavior on duplicate registration, memory growth (does CacheRegistry release on teardown?). Cross-check the CLAUDE.md table (shared vs per-container) against actual constructor wiring in `container.py` — mismatch is a Drift finding against CLAUDE.md itself.

- [ ] **Step 5: Benchmarks sanity.** Read the three bench files: do they still import/run? Run: `uv run python -m pytest benchmarks/ --collect-only -q` (or however they're invoked — check `Justfile`/`pyproject.toml` first). Broken benchmarks → Quality finding.

- [ ] **Step 6: Append findings and commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit: providers/registries pass"
```

### Task 4: Test audit

**Files:**
- Read: all test files under `tests/` (14 test modules + `__init__.py` files)
- Modify: `planning/audits/2026-06-12-code-docs-audit-report.md`

- [ ] **Step 1: Read every test file.** For each, note behaviors asserted.

- [ ] **Step 2: Weak-assertion scan.** Flag tests that (a) assert only `is not None`/no-exception, (b) have names promising more than they check, (c) mock the thing they claim to test. Each → Quality finding.

- [ ] **Step 3: Coverage-gap diff.** Compare the behavior list from Tasks 2–3 probes against what tests cover. Specifically check for tests covering: every edge case probed in Task 2 Step 2/3 and Task 3 Step 2/3 that turned out to have *intentional* behavior. Intentional-but-untested → Quality finding (severity by blast radius). Also run:

Run: `just test 2>&1 | tail -20`
and inspect per-file coverage; any source file below the baseline average gets its uncovered lines (from the coverage report) listed in a finding.

- [ ] **Step 4: Append findings and commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit: test pass"
```

### Task 5: Docs cross-check (drift)

**Files:**
- Read: `README.md` and all 30 pages under `docs/` (skip `docs/superpowers/specs/`)
- Modify: `planning/audits/2026-06-12-code-docs-audit-report.md`

- [ ] **Step 1: Extract and execute examples.** For each docs page with Python code blocks, copy each self-contained example into `/tmp/audit_doc_<page>.py` and run with `uv run python`. Integration pages (`docs/integrations/*.md`) reference external packages not installed here — for those, verify only the `modern_di` API calls (names, signatures, kwargs) against source by Grep, and mark "not executed (external dep)".
  - Failure to run → Drift finding, severity high.
  - Runs but output contradicts the page's prose → Drift, medium.

- [ ] **Step 2: Claim trace.** For every behavioral claim in prose (e.g. "child containers share the parent's overrides", "validation is zero-cost when disabled"), find the implementing line(s). Claim with no implementation or contradicting implementation → Drift finding citing both the doc line and the code line.

- [ ] **Step 3: Cross-page consistency.** Same concept described on two pages (e.g. scopes in `providers/scopes.md` vs `introduction/resolving.md` vs README) — flag contradictions between pages even when each is individually defensible.

- [ ] **Step 4: Append findings and commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit: docs drift pass"
```

### Task 6: Docs completeness (inverse check)

**Files:**
- Read: `mkdocs.yml` (nav — find orphaned/missing pages)
- Modify: `planning/audits/2026-06-12-code-docs-audit-report.md`

- [ ] **Step 1: Public-surface inventory.** List every name exported from `modern_di/__init__.py` and `modern_di/providers/__init__.py`, plus every public method/kwarg on `Container`, `Factory`, `CacheSettings`, `Group`, `ContextProvider`, `Alias`. For each: which docs page covers it? Uncovered → Docs gap finding.

- [ ] **Step 2: Behavior inventory.** Every *intentional* behavior discovered via probes in Tasks 2–3 that no docs page mentions (e.g. error raised on skipped scope, finalizer ordering guarantee) → Docs gap finding, severity by how surprising the behavior is.

- [ ] **Step 3: Nav check.** Every `docs/**/*.md` page present in `mkdocs.yml` nav? Every nav entry has a file? Orphans/dead entries → Docs gap, low.

- [ ] **Step 4: Append findings and commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit: docs completeness pass"
```

### Task 7: Final assembly + self-review

**Files:**
- Modify: `planning/audits/2026-06-12-code-docs-audit-report.md`

- [ ] **Step 1: Write the Summary section.** Table of counts by category × severity, then a "Top 5 by impact" list with one-line rationale each.

- [ ] **Step 2: Self-review the report against the spec checklist:**
  - every finding has all five fields filled (no "TBD")
  - every Bug has a "Verified by" that is a real probe run or trace, not a hunch
  - no finding duplicates the 2026-06-05 report without the `(known since)` marker
  - IDs are sequential with no gaps
  - severity is justified by the "Why it's a problem" text

- [ ] **Step 3: Final commit**

```bash
git add planning/audits/2026-06-12-code-docs-audit-report.md
git commit -m "Audit: final report — summary + self-review"
```

- [ ] **Step 4: Present the Summary section to the user** and ask which findings to fix. The selected set becomes the input to the next plan (fix plan). Do NOT fix anything in this plan's scope.
