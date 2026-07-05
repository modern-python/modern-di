# v3-ux-research — execution plan

Execution is a multi-agent research workflow (deep-research harness), not a
code-change task list. This plan records the harness so it can be re-run or
resumed. Spec: [`design.md`](./design.md).

**Branch:** `docs/v3-ux-research` — bundle + report ship in one PR.

## Phase 1 — Ground truth (inline, before fan-out)

Assemble the modern-di current-surface digest passed to every agent: the six
`architecture/*.md` files, the public exports, the queued 3.0 breaking
changes, and the four fixed constraints. No agent describes modern-di from
memory.

## Phase 2 — Per-framework research (fan-out, 13 agents)

One agent per framework: dependency-injector, dishka, that-depends, svcs,
wireup, injector, FastAPI `Depends`; .NET M.E.DI, Dagger 2, Spring, Angular DI,
Uber Fx, Koin. Each reads current docs (web + Context7) and returns structured
notes:

```
{ framework, declaration_style, scope_model, singleton_vocabulary,
  context/runtime-value pattern, error_examples[] (verbatim where possible),
  validation_story, docs_onboarding_path, integration_contract,
  citations[] }
```

## Phase 3 — Per-surface synthesis (fan-out over the whole set, 4 agents)

One agent per surface (core API ergonomics · errors & diagnostics · docs &
onboarding · integration API shape). Input: ground-truth digest + all phase-2
notes. Output: candidate improvements, each as:

```
{ id, surface, problem_in_modern_di, precedent (framework + citation),
  sketch (≤5 lines), breaking: yes/no, constraint_check: pass/violates-<n> }
```

Constraint violators are kept but routed to the rejected-context pool.

## Phase 4 — Adversarial verify (fan-out, one agent per candidate)

Independent agent per candidate attempts to refute: (a) the competitor-API
claim against current docs, (b) the constraint check, (c) the breaking-or-not
flag, (d) whether modern-di already has the capability (checked against the
ground-truth digest). Refuted → dropped; corrected → amended; survivors carry
a verdict.

## Phase 5 — Synthesize the report

Dedupe and rank; write
`planning/audits/2026-07-05-v3-ux-research-report.md`:

1. Summary + method.
2. Per-surface comparative findings (cited).
3. "Consciously rejected" section (constraint-violating field practices).
4. Ranked candidate shortlist — each with precedent, breaking flag, and an
   empty **Ruling:** slot for the maintainer.

## Phase 6 — Ship

- [x] `just check-planning` and `just lint-ci` pass.
- [x] Finalize this bundle's `summary:` to the realized result.
- [x] Commit report + bundle, push, open PR, watch CI.
- [ ] Maintainer rules on the shortlist (in PR review or a follow-up session);
      accepted items spawn their own planning bundles.
