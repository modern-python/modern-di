---
status: accepted
summary: Drop the mkdocs-redirects plugin entirely — merged-page URLs 404 instead of being preserved.
supersedes: null
superseded_by: null
---

# No redirect plugin — merged-page URLs 404

**Decision:** Do not depend on `mkdocs-redirects` (or any redirect plugin) to
preserve the two old URLs from the docs-dedupe page merges
(`testing/fixtures/`, `introduction/that-depends-or-modern-di/`). Both URLs
404 after the merge.

## Context

Task 1 of the docs-dedupe change added `mkdocs-redirects>=1.2,<2` to
`docs/requirements.txt` and a `redirects` plugin block to `mkdocs.yml` so the
two merged pages' old URLs would keep resolving. Investigating the pin before
shipping found that `mkdocs-redirects` 1.2.3 (2026-03-28) is a hostile
release: it adds a dependency on `properdocs` — a fork of MkDocs whose code
hooks into every build to print scare-marketing urging users to switch to the
fork — and it caps `mkdocs<=1.6.1`, fighting our own `mkdocs>=1.6,<2` pin.
The prior release, 1.2.2 (2024-11-07), is clean; there has been no clean
release since.

## Decision & rationale

Remove the `mkdocs-redirects` dependency and the `redirects` plugin block
entirely, rather than pin around the compromised release. Pinning `==1.2.2`
would keep an unmaintained-and-now-hostile project in the dependency chain:
any future `pip`/`uv` resolution loosened even slightly re-admits 1.2.3+, and
a hard pin still ships a package whose maintainers have shown willingness to
weaponize a point release. Two URLs 404ing is a small, contained cost;
carrying a supply-chain-compromised dependency to avoid it is not a good
trade.

### Rejected alternatives

- **Pin `mkdocs-redirects==1.2.2`.** Freezes the immediate problem but leaves
  an untrustworthy upstream in the chain — the next dependency bump (manual
  or automated) can silently reintroduce 1.2.3+, and the pin itself is a
  standing note-to-self that has to survive every future audit.
- **Local mkdocs hook to implement redirects ourselves.** Avoids the
  dependency but adds custom build-time code to maintain for two URLs — more
  surface area than the problem warrants.
- **Committed static meta-refresh stub pages** (e.g. hand-written HTML/MD
  files at the old paths that redirect via `<meta http-equiv="refresh">`).
  Works without a plugin but adds permanent maintenance-owned files for a
  problem that only exists because of the merge; simpler to just let the
  URLs 404.

## Revisit trigger

Revisit if MkDocs gains native redirect support (removing the need for a
third-party plugin), or if `mkdocs-redirects` changes hands / publishes a
clean release that drops the `properdocs` dependency and the `mkdocs<=1.6.1`
cap.
