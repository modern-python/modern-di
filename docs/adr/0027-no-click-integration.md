# No Click integration — Typer already covers the CLI entrypoint

**Decision:** no `modern-di-click` adapter. The CLI entrypoint is covered by `modern-di-typer`, and
a second adapter for the same layer would be redundant rather than additive.

Typer is built on Click: a Typer application *is* a Click application, and `modern-di-typer` already
covers the CLI wiring seam — `setup_di` attaches the app-scoped container, `@inject` opens a
`REQUEST` child per command invocation and resolves `FromDI` parameters from it, while the root's
open/close stays the caller's `with container:` by the ruling in
[ADR-0020](0020-d3-root-lifecycle-inherent.md). A separate Click adapter would re-derive that same
contract against the lower-level API for no entrypoint that is not already reachable, while adding a
repository, a release cadence, and a compatibility matrix to maintain. That cost is the one the
[separate-repo integration model](../introduction/design-decisions.md) exists to keep proportionate
to the coverage bought.

- **Vendoring Click support inside `modern-di-typer`** would let a plain Click app reuse the adapter,
  but it makes that package's public surface depend on which of the two APIs the user built against,
  and Typer's own Click version is an implementation detail it is free to move.
- **A community-maintained adapter** stays available: nothing here forbids one existing outside the
  `modern-python` org, on the same footing as the other frameworks nobody has volunteered for.

**Revisit trigger:** a Click-only application that `modern-di-typer` provably cannot wire — a
`click.Group` composed at runtime, or a Click-native plugin system Typer does not expose — reported
by someone hitting it, not hypothesized.
