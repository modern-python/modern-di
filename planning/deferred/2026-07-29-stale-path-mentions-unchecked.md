---
summary: Nothing checks path *mentions* — `links.py` strips inline-code spans by design, so a backticked path to a deleted file passes every gate; nine such references survived the planning restructure and were found only by hand.
---

# Stale path mentions in prose are unchecked

`just check-links` validates Markdown **links**. A path written as prose or in a
code span — `` `planning/changes/2026-07-07.06-error-docs-registry.md` `` — is
not a link, passes every gate, and points at nothing.

## Why it is open

This is not a bug in `links.py`. It strips inline-code spans before scanning
(`INLINE_CODE`, `planning/links.py:31`) precisely so that a backticked
`[example](path)` in documentation prose is not mistaken for a real link. The
behaviour is correct; the gap is that no check covers the other case.

It surfaced at scale during the planning restructure (#394), which deleted
`planning/changes/`, `planning/audits/`, `planning/retros/`, and moved
`planning/releases/`. `links.py` reported 35 broken links and zero of the
**nine** stale path mentions that also existed:

- `architecture/concurrency.md` — "See the report for the full argument"
- `planning/decisions/2026-07-19-exec-hot-path-declined.md` — opened by naming
  `deferred.md`'s codegen-ceiling item
- four release notes, referring to audit reports in prose
- `tests/test_docs_slug_census.py` — a module docstring citing a change file
- `planning/README.md` — an artifact bullet naming `deferred.md` in backticks
  while the Markdown link two sections below was caught

All nine were found by an ad-hoc `grep` for the deleted directory names. That
sweep is not in the Justfile and not in CI, so the next deletion repeats it.

**This matters more now than it did before.** The convention adopted in #394
deletes files as routine operation, not as a one-off migration: a deferred item
is deleted when it ships, and a decision is superseded rather than kept. Every
one of those deletions can strand prose mentions.

Two shapes for a fix:

1. **A repo-local check.** A small script (or a `just` recipe) that greps for
   references to paths that no longer exist. Simplest, and it stays out of the
   vendored file.
2. **Extend `links.py`.** More thorough, but `links.py` is **vendored into
   consumer repos** (`planning/links.py:1`), so this is a convention-level
   change that would have to go upstream to
   [`lesnik512/planning-convention`](https://github.com/lesnik512/planning-convention)
   rather than being edited here — see
   [`upstream-lean-convention`](2026-07-29-upstream-lean-convention.md).

Shape 1 is the cheaper start and does not block on the upstream question.

## Revisit trigger

The first deletion of a `deferred/` or `decisions/` file under the new lifecycle
— that is the moment the gap becomes live rather than theoretical. Or any stale
path mention found by a reader, which is evidence it is already happening.
