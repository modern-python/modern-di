# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## X-4 follow-up — `validate()` does not enforce scope transitively through an Alias

**Source:** 2026-06-12 audit, finding X-4 (fixed in PR #203 for the direct case; this is the residual limitation).

`Alias.scope` is decorative — resolution delegates to the source provider and ignores the alias's own scope. PR #203 made `Container.validate()` stop false-positiving on an Alias whose scope is shallower than its source (via the `AbstractProvider.enforces_dependency_scope` ClassVar, which `Alias` sets to `False`). The side effect: `validate()` no longer catches a **transitive** scope mismatch of the shape `Factory(shallow) → Alias → Factory(deep)`.

- **Symptom:** an APP-scoped factory depending through an alias on a REQUEST-scoped provider passes `validate()` but raises `ScopeNotInitializedError` at runtime when resolved from a too-shallow container. It fails loudly (no silent corruption), just later than `validate()` ideally would.
- **Why deferred:** a proper fix needs `validate()` to track the *effective minimum scope* reachable through alias indirection, rather than checking each edge in isolation. That's its own small design + plan, not a one-line change.
- **Current mitigation:** documented as a caveat in `docs/providers/alias.md` (Validation section).
- **Pick-up:** scope-tracking pass in `Container.validate._visit` that propagates a "deepest reachable source scope" through `enforces_dependency_scope=False` edges and flags the caller if it's shallower.
