# No redirect plugin — merged-page URLs 404

**Decision:** no dependency on `mkdocs-redirects` or any redirect plugin. The two URLs orphaned by
the docs-dedupe merges (`testing/fixtures/`, `introduction/that-depends-or-modern-di/`) 404.

`mkdocs-redirects` 1.2.3 (2026-03-28) is a hostile release: it adds a dependency on `properdocs` — a
MkDocs fork whose code hooks into every build to print scare-marketing urging users to switch to the
fork — and caps `mkdocs<=1.6.1`, fighting this repo's `mkdocs>=1.6,<2` pin. The prior release,
1.2.2 (2024-11-07), is clean, and there has been no clean release since. Two 404s is a small,
contained cost; carrying a supply-chain-compromised dependency to avoid it is not.

- **Pinning `==1.2.2`** freezes the immediate problem but leaves an untrustworthy upstream in the
  chain: any loosened resolution re-admits 1.2.3+, and the pin is a standing note-to-self that has
  to survive every future audit.
- **A local mkdocs hook** avoids the dependency but adds build-time code to maintain for two URLs.
- **Committed meta-refresh stub pages** work without a plugin but add permanently maintained files
  for a problem that exists only because of the merge.

**Revisit trigger:** MkDocs gains native redirect support, or `mkdocs-redirects` changes hands /
publishes a clean release dropping the `properdocs` dependency and the `mkdocs<=1.6.1` cap.
