# No redirect plugin; merged-page URLs 404

**Decision:** no dependency on `mkdocs-redirects` or any redirect plugin. The two URLs orphaned by
the docs merges (`testing/fixtures/`, `introduction/that-depends-or-modern-di/`) 404.

**Why:** `mkdocs-redirects` 1.2.3 added a dependency on `properdocs`, a MkDocs fork that hooks
every build to print marketing for itself, and capped `mkdocs<=1.6.1` against this repo's pin.
Pinning the last clean release (1.2.2) keeps an untrustworthy upstream in the chain; a local hook or
committed meta-refresh stubs add permanently maintained code for two URLs. Two 404s is the smaller
cost.
