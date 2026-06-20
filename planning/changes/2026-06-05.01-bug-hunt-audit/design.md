---
status: shipped
date: 2026-06-05
slug: bug-hunt-audit
summary: Four-dimension bug-hunt audit harness and report; 18 findings actioned in 2.15.0.
supersedes: null
superseded_by: null
pr: null
outcome: Four-dimension bug-hunt audit harness; report in audits/2026-06-05-bug-hunt-audit-report.md; 18 findings actioned in 2.15.0 (#188–#197).
---

# Bug-Hunt Audit — Design

**Date:** 2026-06-05
**Status:** Draft, pending user approval
**Author:** brainstorming session

## Goal

Produce a triaged backlog of confirmed bugs and quality risks in `modern-di` across four dimensions — UX, security, tests, logic — with enough evidence per finding that a future implementation plan can act on it without re-investigating.

This spec does **not** apply fixes. It defines a one-shot audit; the next planning cycle decides what to act on.

## Success criteria

Every finding in the final report must:

1. Name a specific `file:line` (or line range).
2. Have been adversarially verified by at least 2 of 3 verifiers with distinct lenses.
3. Carry a triage bucket (`must-fix-now`, `should-fix-soon`, `nice-to-have`, `spec-fix`, or `wont-fix`).
4. Be reproducible from the report alone — no need to re-derive the scenario from source.

## Scope

### In scope

- `modern_di/` source — container, providers, registries, types_parser, scope, group, errors, exceptions, types (~900 LOC).
- `tests/` — audited **as a target**, not just used for verification. Looking for weak/missing assertions, branches with coverage but no behavioral assertion, fixtures that paper over bugs, undocumented `xfail`/`skip`.
- `benchmarks/` — correctness of what the benchmarks measure (not perf claims).
- `docs/`, `README.md`, `CLAUDE.md` — audited only for **spec-vs-behavior divergence**: places where docs claim X but code does Y.

### Non-goals

- Sibling repos (`modern-di-pytest`, FastAPI/FastStream/LiteStar/Typer integrations) — explicitly out per `CLAUDE.md`.
- Performance findings unless they cross into correctness (unbounded growth, pathological complexity that becomes DoS).
- Style or lint-class nits — `ruff` and `ty` already enforce these in CI.
- Applying fixes. This audit ends at a triaged report.

## Dimensions and detection heuristics

Each finder agent is calibrated to the library, not given generic checklists.

### UX — developer experience

- **Error message quality.** Templates in `modern_di/errors.py` audited against actual call sites — do they name the offending type, provider, and scope, or just describe a category?
- **API friction.** Required-but-unintuitive kwargs, footguns: `skip_creator_parsing` semantics, `validate=True` cost claims, `cache_settings=CacheSettings()` as the singleton-by-other-name pattern.
- **Surprising defaults.** What happens with no `groups=`, no `context=`, default scope, etc.
- **Doc-vs-behavior divergence.** README and `CLAUDE.md` claims vs. real signatures, exports, scope rules.

### Security

Small surface for a zero-dep DI library, but real.

- **`types_parser` evaluation paths.** String-typed forward refs — any `eval`, `exec`, or `__import__` resolution? Behavior on adversarial annotation strings (`Annotated[str, "..."]`, exotic forward refs).
- **Override registry escape hatches.** Can override bypass scope guards? Can a child container's override leak to siblings via the shared registry?
- **Unbounded recursion / cache growth.** Cycle-detection guarantees, child-container leak on long-lived parents, ContextRegistry sizes.
- **Unsafe `__reduce__` / pickling paths** on providers, if any.

### Tests

Audit `tests/` itself as a target.

- **Assertions that don't test the claim.** `assert x is not None` where the claim was about structure or value.
- **Branches with coverage but no behavioral assertion.** Recent commits (`d9b7bcd`, `36c7c8f`) added a full-coverage requirement — this is gameable; we look for the games.
- **Missing edges per dimension.** Scope mismatch errors, cycle detection, async finalizer in sync close, override reset semantics, deep child-container chains.
- **Fixtures that paper over bugs.** Always-fresh container hides cross-test cache bleed, etc.
- **Undocumented `xfail` / `skip` / flake markers** — anything without a `# Why:` rationale.

### Logic

- **Scope rules.** Can you resolve a deeper-scoped provider from a shallower container? CLAUDE.md says no — verify the guard fires on every path including `container_provider` and aliases.
- **Cache lifecycle.** Child cache vs. parent cache; behavior on `close()` mid-resolution; finalizer order (LIFO vs. insertion); sync `close()` with an async finalizer (recent commit suggests this is now raised on — verify it actually does).
- **Override propagation.** Shared `overrides_registry` semantics across the container tree; reset behavior; interaction with caching (cached value present before override registered).
- **`types_parser`.** PEP 604 unions, `Optional`, `Annotated`, `TYPE_CHECKING` strings, forward refs, generics, `*args` / `**kwargs`, default-valued params, `Self`.
- **Container tree edges.** `build_child_container` on a closed parent; on the same parent concurrently; with a shallower scope than the parent.

## Method — agent topology

A single Workflow script, four phases, pipelined so verify starts as soon as any dimension's finder returns. No global barriers between phases except the synthesis step.

```
Phase 1: Discover          Phase 2: Find             Phase 3: Verify              Phase 4: Synthesize
─────────────              ─────────────             ─────────────                ──────────────────

read repo,                 ├─ ux-finder        ─┐    each finding fans to         dedup across
list files,                ├─ security-finder  ─┤    3 verifiers w/ distinct      dimensions
emit file map              ├─ tests-finder     ─┤    lenses (parallel):           ↓
+ shared                   └─ logic-finder     ─┘    ├─ reproduce                 apply triage rubric
context blob                                         ├─ read-real-code            ↓
                           (4 parallel)              └─ spec-vs-behavior          emit report
                                                     ↓                            ↓
                                                     ≥2/3 → kept                  write to
                                                                                  planning/audits/...
```

### Phase 1 — Discover

One agent reads the file tree, line counts, key module structure, recent commits, and behavior claims in `README.md` / `CLAUDE.md`. Emits a structured context blob (file map + claim list) consumed by every finder. Done once; cheap; eliminates redundant re-discovery across the four finders.

### Phase 2 — Find

Four finders run in parallel, each given the shared context blob and its dimension's heuristics. Each emits a list of findings via the structured-output schema below. Finders are told to be specific (`file:line` required) and skeptical — no speculative findings without a code citation.

### Phase 3 — Verify

`pipeline()`, not `parallel()` with a barrier — each finding flows to verify as soon as its finder returns; no waiting for slow finders.

Each finding gets 3 verifiers with distinct lenses:

- **Reproduce.** Write the minimum code snippet that would trigger the claimed bug. If it can't be constructed, refuted.
- **Read-real-code.** Open the cited `file:line` and confirm the code actually does what the finding claims. Catches finder hallucinations.
- **Spec-vs-behavior.** Cross-check `CLAUDE.md`, `README.md`, docstrings; classify as `bug-in-code`, `bug-in-spec`, or `intended-behavior`.

**Survival rule.** A finding is kept if at least 2 of 3 verifiers confirm. Verifiers are explicitly prompted to **default to "refuted" if uncertain** — asymmetric on purpose: false positives cost user attention, which is the scarcest resource here.

### Phase 4 — Synthesize

One agent dedups across dimensions (a "weak assertion" from `tests` and a "missed edge" from `logic` are often the same root issue), applies the triage rubric, and emits the final markdown report.

### Cost shape

Roughly 1 (discover) + 4 (finders) + 3N (verifiers, where N ≈ 30-80 raw findings) + 1 (synth). Expected order: 100-250 agent invocations. Bounded; well below the per-workflow 1000-agent cap. Verifier concurrency capped at the workflow's default `min(16, cores − 2)`.

### Resumability

The whole audit runs in one `Workflow` invocation. If interrupted or stopped, `resumeFromRunId` re-uses completed agent results, so the next attempt only re-runs from the first edited or new call.

## Finding schema

Enforced via structured output on every finder.

```
{
  dimension:        "ux" | "security" | "tests" | "logic"
  title:            short noun phrase
  file:             relative path                            (required)
  line:             integer or "start-end"                   (required)
  description:      1-3 sentences on what is wrong
  evidence:         exact code snippet or doc quote indicted
  repro:            minimal scenario; code for code-bugs,
                    prose for docs/UX issues
  suggested_fix:    one-line direction, not a patch
  severity:         "high" | "medium" | "low"
  confidence_finder:"high" | "medium" | "low"
}
```

After verify, each finding gains:

```
  verifier_votes:   [{lens, verdict, reasoning}, ...]
  survives:         bool       (≥2/3 confirm)
  reclassification: "bug-in-code" | "bug-in-spec" | "intended-behavior"
```

## Triage rubric

The synth phase sorts surviving findings into these buckets:

- **must-fix-now** — correctness or security, high severity, all 3 verifiers confirm.
- **should-fix-soon** — high severity with 2/3 confirmation, OR medium-severity correctness/security with 3/3.
- **nice-to-have** — UX rough edges, test weaknesses that don't currently mask known bugs, low-severity logic edges.
- **spec-fix** — reclassified as `bug-in-spec` (code is correct, docs are wrong). Separate bucket because the fix is editing docs, not code.
- **wont-fix** — survived verify but is intentional design per `CLAUDE.md` ("conservative feature set", "resolution is sync-only", etc.). Recorded with a rationale quoting the spec/CLAUDE.md line that endorses the behavior, so they don't resurface next audit.

## Deliverables

- **This spec:** `planning/specs/2026-06-05-bug-hunt-audit-design.md`
- **Implementation plan (next phase, via writing-plans):** `planning/plans/2026-06-05-bug-hunt-audit-plan.md`
- **Audit report (when the plan is executed):** `planning/audits/2026-06-05-bug-hunt-audit-report.md` — five sections matching the triage buckets, each finding rendered with the post-verify schema.

## Risks and open questions

- **Finder hallucinations.** Mitigated by the read-real-code verifier lens and the require-`file:line` schema rule.
- **Over-eager triage.** Synth could promote a marginal finding to `must-fix-now`. Mitigated by requiring 3/3 verifier confirmation for that bucket; everything else lands lower.
- **Doc decay.** If `CLAUDE.md` is itself stale, "spec-vs-behavior" lens flips bugs into `spec-fix` incorrectly. Acceptable; `spec-fix` is its own bucket and easy to re-triage.
- **Single-shot vs. loop-until-dry.** Spec chose single-shot (Approach B). If the user runs the audit, reads the report, and the tail still feels rich, a follow-up loop-until-dry pass is a small spec delta — same finders, dedup against `seen`, K-rounds-empty exit. Not built in now to keep this audit cheap and bounded.
