# No provider-facing seam on `Container`

**Decision:** no `ResolutionContext` view handed to providers and no declared interface over the
members providers touch. Resolution runs against `Container` directly.

**Why:** there is exactly one `Container` implementation, so the interface would have one
implementer, a hypothetical seam. Since the single-path compiler, providers no longer resolve
themselves at all; the crossings the view would have formalized live in the compiler, which is
[ADR-0014](0014-per-provider-compile-seam-declined.md)'s business. The public docs already say
which members are supported for callers (`find_container`) and which are internal.
