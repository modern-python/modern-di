# No Click integration

**Decision:** no `modern-di-click` adapter. `modern-di-typer` covers the CLI entrypoint.

**Why:** a Typer application is a Click application, and the typer adapter already wires the seam
(`setup_di` attaches the container, `@inject` opens a `REQUEST` child per command, the root stays
the caller's by [ADR-0020](0020-d3-root-lifecycle-inherent.md)). A Click adapter would re-derive the
same contract against the lower-level API for no entrypoint that is not already reachable, at the
cost of a repository, a release cadence and a compatibility matrix. Vendoring Click support inside
the typer adapter would tie its surface to which of the two APIs the user built against. A
community-maintained adapter outside the org remains possible.
