---
summary: Published llms.txt + per-page markdown endpoints via mkdocs-llmstxt (DOC-8), mirroring that-depends' plugin/config with sections adapted to this repo's nav.
---

# Design: llms.txt for the docs site

## Summary

Implements shortlist ruling DOC-8 (2026-07-05 UX research). AI assistants are
a primary onboarding channel; the site ships `docs/context7.json` but
`https://modern-di.modern-python.org/llms.txt` 404s, so agents scrape mkdocs
HTML. Sibling project that-depends (same org) already serves
`https://that-depends.modern-python.org/llms.txt` plus per-page markdown
endpoints — mirror its setup rather than inventing one.

## Design

- **Follow that-depends exactly**: fetch its live `mkdocs.yml` and docs
  requirements from GitHub (`modern-python/that-depends`) and adopt the same
  plugin and configuration (expected: an mkdocs llms.txt plugin emitting the
  nav tree with page summaries and raw-markdown endpoints). Deviate only
  where this repo's nav demands it, and record any deviation.
- Docs tooling only: the plugin goes in `docs/requirements.txt` (the docs
  build runs via `uvx --with-requirements docs/requirements.txt`, so the
  published library keeps zero dependencies); config in `mkdocs.yml`.
- No Justfile/CI changes expected: `just docs-build` and the Deploy Docs
  workflow already build via the same requirements file. Verify the built
  `site/` contains `llms.txt` (and the per-page endpoints) under
  `mkdocs build --strict`.
- Pin the plugin version in `docs/requirements.txt` (the file's existing
  style governs).

## Non-goals

- No changes to `docs/context7.json`; no content edits; no README section
  about llms.txt (can ride a later docs pass if wanted).

## Testing

`just docs-build` (strict) then assert `site/llms.txt` exists and sanity-read
it (nav coverage, no broken relative links inside); spot-check one per-page
markdown endpoint file in `site/`; `just lint-ci`.

## Risk

Plugin/theme incompatibility (low/low): the same org runs the identical stack
(mkdocs Material) with this plugin in production.
