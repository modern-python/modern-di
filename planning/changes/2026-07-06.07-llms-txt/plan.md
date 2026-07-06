# llms-txt — implementation plan

**Goal:** The built docs site serves llms.txt and per-page markdown endpoints.
**Spec:** [`design.md`](./design.md)
**Branch:** `docs/llms-txt`
**Commit strategy:** single commit.

### Task 1: Mirror the that-depends setup
- [x] Fetch that-depends' live mkdocs.yml + docs requirements (GitHub raw);
      identify the plugin + config it uses for llms.txt.
- [x] Add the pinned plugin to docs/requirements.txt; add the mkdocs.yml
      plugin config adapted to this repo's nav.
- [x] `just docs-build` (strict); assert site/llms.txt exists and covers the
      nav; spot-check a per-page markdown endpoint; `just lint-ci`.
- [x] Commit: `docs: publish llms.txt + per-page markdown endpoints (DOC-8)`
