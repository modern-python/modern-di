# quickstart-ramp — implementation plan

**Goal:** docs/index.md teaches Group + Factory + resolve first; caching and scopes are lessons two and three.
**Spec:** [`design.md`](./design.md)
**Branch:** `docs/quickstart-ramp`
**Commit strategy:** single commit (plus relocations if any, same commit).

### Task 1: Restructure the ramp
- [ ] Inventory docs/index.md: mark each block keep / restructure / relocate
      (unique content) / drop (duplicated elsewhere — name where).
- [ ] Write steps A/B/C per the design's target shape; spot-run each snippet
      as a throwaway scratchpad script.
- [ ] Apply relocations; keep "Where to next" current.
- [ ] Gates: `just docs-build`, `just lint-ci`.
- [ ] Commit: `docs: progressive-disclosure quickstart — first success in three concepts (DOC-2)`
