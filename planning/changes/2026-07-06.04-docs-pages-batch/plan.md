# docs-pages-batch — implementation plan

**Goal:** Ship DOC-4, DOC-5, DOC-7, DOC-9 as one docs PR.
**Spec:** [`design.md`](./design.md)
**Branch:** `docs/pages-batch`
**Commit strategy:** one commit per DOC item (4 commits).

### Task 1: DOC-5 vocabulary table (comparison.md)
- [ ] Verify each competitor spelling against its live docs (start from the
      report's citations); build the 6×6 table; raw pipes in code spans.
- [ ] Commit: `docs: add cross-framework lifetime vocabulary table (DOC-5)`

### Task 2: DOC-4 for-fastapi-users page
- [ ] Verify FastAPI Depends semantics (use_cache, yield, 0.121 scope=)
      against live FastAPI docs; write the page + nav entry.
- [ ] Commit: `docs: add "modern-di for FastAPI users" page (DOC-4)`

### Task 3: DOC-7 anti-patterns page
- [ ] Write 5-7 anti-patterns with bad/good pairs; verify each footgun
      against current source behavior (post ERR-1/ERR-3 the cycle framing
      changed); nav entry + quickstart cross-link.
- [ ] Commit: `docs: add good-and-bad-practices anti-pattern catalog (DOC-7)`

### Task 4: DOC-9 non-goals + links
- [ ] Extend design-decisions.md (three omissions, existing format);
      reference from README.md and comparison.md.
- [ ] Commit: `docs: document remaining deliberate non-goals (DOC-9)`

### Gates (after each task and at the end)
- [ ] `just docs-build`, `just lint-ci`, `just check-planning`.
