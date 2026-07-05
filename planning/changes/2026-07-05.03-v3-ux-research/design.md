---
summary: Comparative UX research across 13 DI frameworks; cited report with a 30-candidate verified shortlist (26 distinct decisions, 3 breaking) awaiting maintainer rulings.
---

# Design: 3.0 UX & Interface Research

## Summary

A deep-research effort answering one question: **given one breaking-change
budget (the 3.0 major release), what should modern-di change or add across its
UX surfaces?** The method is comparison against other DI frameworks — six in
Python, six in other languages, plus FastAPI's `Depends` as the ambient
baseline — verified against their current documentation, never asserted from
memory. The deliverable is a cited report in `planning/audits/` ending in a
ranked candidate shortlist where each item carries competitor precedent, a
breaking-or-not flag, and a ruling slot for the maintainer. Accepted rulings
spawn normal planning bundles; this change produces **no code or API changes**
itself.

## Motivation

3.0 already has queued breaking changes (`ContainerClosedWarning` →
`ContainerClosedError`, removal of `Alias(scope=)` and `cache_settings=`), so a
major release is coming regardless. A major release is the only opportunity to
spend breaking-change budget on the API surface; spending it well requires
knowing what the rest of the field does — and what users trained on
dependency-injector, dishka, FastAPI `Depends`, or .NET DI will expect.
Recent UX work (inline error messages #227, the suggester #228, the 2026-06
docs-ux audit and fix batches) was inward-looking: it polished what exists.
This research looks outward before the 3.0 surface freezes.

## Constraints (fixed, not up for re-examination)

All four core design principles are hard constraints on candidates:

1. **Zero dependencies.**
2. **Sync-only resolution** (finalizers may stay sync or async).
3. **No global state.**
4. **Conservative feature set.**

A competitor practice that violates a constraint may appear in the report only
as explicitly-rejected context ("what others do that we consciously don't"),
never as a candidate.

## Non-goals

- No fixes, API changes, or deprecations in this phase — report only.
- No rulings made on the maintainer's behalf; every candidate ends in a ruling slot.
- Sibling integration repos' internals are out of scope; only the contract core
  exposes to them is examined.
- No re-audit of docs correctness or prose quality (covered by the 2026-06 audits).

## Design

### 1. Comparison set

**Python:** dependency-injector, dishka, that-depends (migration guide already
exists here), svcs, wireup, injector, plus FastAPI's `Depends` as the ambient
baseline most Python web developers already know.

**Other languages:** .NET `Microsoft.Extensions.DependencyInjection`
(philosophically closest — scopes, `ValidateOnBuild`/`ValidateScopes`),
Dagger 2 (best-in-class compile-time error messages), Spring (failure
analyzers, diagnostics), Angular DI, Go Uber Fx, Kotlin Koin.

### 2. Research questions per surface

- **Core API ergonomics** — declaration style (class-attribute `Group` vs.
  decorators, modules, DSLs); scope vocabulary (`APP/SESSION/REQUEST/ACTION/STEP`
  vs. the singleton/scoped/transient lingua franca); `cache=` vs. an explicit
  `Singleton` concept; child-container and `context` ergonomics; what others do
  that we would consciously reject.
- **Errors & diagnostics** — benchmark message quality against Dagger and
  Rust-style diagnostics and Spring failure analyzers; `validate()` report
  format; graph introspection/visualization precedents.
- **Docs & onboarding** — time-to-first-success vs. dishka/svcs/
  dependency-injector; how each framework teaches its mental model; 2.x → 3.0
  migration-guide patterns from other projects' major releases.
- **Integration API shape** — what core primitives other ecosystems expose for
  framework integrations, vs. what the sibling repos (aiohttp, FastAPI,
  FastStream, Litestar, Starlette, Typer, pytest) currently build on.

### 3. Method

The deep-research harness (multi-agent workflow):

1. **Ground truth** — modern-di's current surface is taken from
   `architecture/` and code, not from memory; passed into every agent.
2. **Per-framework research (fan-out)** — one agent per framework reads its
   current docs (web + Context7), returning structured notes per surface, with
   citations; verbatim error-message examples where obtainable.
3. **Per-surface synthesis (fan-out over the whole set)** — one agent per
   surface compares modern-di against the field and drafts candidate
   improvements, each with precedent and a constraint check.
4. **Adversarial verify** — each candidate is independently checked:
   competitor-API claims re-verified against current docs; constraint
   compliance; breaking-or-not flag correctness. Refuted claims are dropped;
   constraint violators move to the rejected-context section.
5. **Synthesize** — dedupe, rank, and write the report.

### 4. Deliverables

- **Report:** `planning/audits/2026-07-05-v3-ux-research-report.md` — cited
  comparative findings per surface, a "consciously rejected" section, and the
  ranked candidate shortlist with per-item ruling slots (mirroring the
  2026-06-13 docs-ux-audit → rulings-batch flow).
- **This bundle:** design + plan, shipped in the same PR as the report.

## Testing

`just check-planning` passes; `just lint-ci` passes on the added Markdown. The
substantive quality gate is the adversarial-verify phase inside the research
workflow: no competitor-API claim survives into the report unverified.

## Risk

- **Stale/wrong competitor claims** (medium likelihood, high impact — a ruling
  made on a false premise wastes the breaking-change budget). Mitigated by the
  verify phase and citation requirement.
- **Scope creep into design work** (medium/medium): candidates ballooning into
  full designs inside the report. Mitigated: candidates are capped at
  problem + precedent + sketch; design happens in follow-up bundles.
- **Recommendation bias toward feature accretion** (low/high): comparison
  research naturally surfaces "others have X, we lack X". Mitigated by the
  fixed conservative-feature-set constraint and the rejected-context section
  giving "do nothing" a first-class home.
