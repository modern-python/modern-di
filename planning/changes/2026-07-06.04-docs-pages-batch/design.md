---
summary: Docs pages batch — FastAPI-users translation page (DOC-4), cross-framework vocabulary table (DOC-5), anti-patterns catalog (DOC-7), non-goals extension (DOC-9).
---

# Design: Docs pages batch (DOC-4, DOC-5, DOC-7, DOC-9)

## Summary

Four self-contained page additions from the ruled 2026-07-05 UX-research
shortlist, batched into one PR (house precedent: the audit fix batches).
All content claims about other frameworks must be verified against live
sources at writing time — the per-framework research notes were ephemeral;
the report (`planning/audits/2026-07-05-v3-ux-research-report.md`) retains
the citations to start from.

## Design

### DOC-4 — "modern-di for FastAPI users" (`docs/introduction/for-fastapi-users.md`)

Side-by-side translation table: `Depends(fn)` ↔ `Factory(creator=fn)`;
`use_cache` per-request memo ↔ REQUEST-scope `Factory(cache=True)` (a bare
Factory = fresh instance per resolve, i.e. `use_cache=False`); yield
teardown ↔ `cache=CacheSettings(finalizer=...)`; `lru_cache` singleton ↔
APP-scope `Factory(cache=True)` with finalizer; `app.dependency_overrides` ↔
`container.override(provider, mock)`. Callout box: since FastAPI 0.121.0,
`Depends(scope="function"|"request")` means *teardown timing*, while
modern-di's `Scope` is *lifetime* — same word, different axis (verify the
0.121 semantics against FastAPI's release notes/docs before quoting). Nav:
under Introduction, after Comparison.

### DOC-5 — vocabulary table (extend `docs/introduction/comparison.md`)

A "where is Singleton?" translation table appended to the existing
comparison page (not a new page): rows = singleton · transient ·
request-scoped · runtime value · interface binding · test override; columns
= dependency-injector, dishka, wireup, svcs, FastAPI, modern-di. Each
modern-di cell links to the owning docs page. Every competitor spelling
verified against that framework's current docs (the report's precedent URLs
are the starting set). Beware the repo's table rule: a literal `|` inside a
code span in a Markdown table must be a raw pipe, not `\|` or `&#124;`.

### DOC-7 — anti-patterns page (`docs/recipes/good-and-bad-practices.md`)

5-7 named anti-patterns, each with a bad/good code pair and a link to the
enforcing mechanism: captive dependency (validate catches); cached factory
built before `set_context` (stale instance); shipping unvalidated graphs
(cycle guard is the backstop, `validate=True` the answer); service location
via `container_provider` overuse; override leaks across tests (root close
auto-clears; `reset_override()` / the shared registry). Precedents:
injector's practices page, Microsoft's DI guidelines anti-pattern catalog.
Nav: Recipes; cross-link from quickstart's "Where to next".

### DOC-9 — non-goals (extend `docs/introduction/design-decisions.md`)

Add the three genuinely missing deliberate omissions, in the page's existing
what/why/alternative format: auto-binding / auto-registration; in-package
framework integrations; graph *rendering/visualization* tooling (phrase the
graphs entry carefully: rendering is out of scope — do not promise the
accepted-but-unshipped text export). Reference the page from `README.md`
and `comparison.md` (the repo has no issue templates; the ruling chose
these two link points instead). Source material: report section 4.

## Non-goals

- No quickstart changes (DOC-2 is its own PR), no migration guide (DOC-3),
  no build tooling (DOC-8).
- No new claims about competitor roadmaps; only current, verifiable API
  spellings with citations checked at writing time.

## Testing

`just docs-build` (strict links/anchors), `just lint-ci`; every
cross-framework claim carries a source the implementer actually fetched;
modern-di-side snippets spot-run where runnable.

## Risk

Stale competitor claims (medium/medium) — mitigated by the live-verification
requirement; a reviewer re-checks a sample of claims independently.
