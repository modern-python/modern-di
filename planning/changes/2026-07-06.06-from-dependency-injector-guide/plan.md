# from-dependency-injector-guide — implementation plan

**Goal:** Ship docs/migration/from-dependency-injector.md per the design.
**Spec:** [`design.md`](./design.md)
**Branch:** `docs/from-dependency-injector`
**Commit strategy:** single commit.

### Task 1: The guide
- [ ] Study the template (docs/migration/from-that-depends.md) and the report's
      dependency-injector notes/citations (planning/audits/2026-07-05-v3-ux-research-report.md).
- [ ] Verify every dependency-injector spelling live; write the six design
      sections; taxonomy table complete (each source provider mapped or
      explicitly unmapped + workaround).
- [ ] Spot-run modern-di snippets; nav entry after "From that-depends";
      optional one-line cross-link from comparison.md.
- [ ] Gates: `just docs-build`, `just lint-ci`.
- [ ] Commit: `docs: add "Migrate from dependency-injector" guide (DOC-3)`
