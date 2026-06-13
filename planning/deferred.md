# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## X-4 follow-up — `validate()` does not enforce scope transitively through an Alias

**Source:** 2026-06-12 audit, finding X-4 (fixed in PR #203 for the direct case; this is the residual limitation).

`Alias.scope` is decorative — resolution delegates to the source provider and ignores the alias's own scope. PR #203 made `Container.validate()` stop false-positiving on an Alias whose scope is shallower than its source (via the `AbstractProvider.enforces_dependency_scope` ClassVar, which `Alias` sets to `False`). The side effect: `validate()` no longer catches a **transitive** scope mismatch of the shape `Factory(shallow) → Alias → Factory(deep)`.

- **Symptom:** an APP-scoped factory depending through an alias on a REQUEST-scoped provider passes `validate()` but raises `ScopeNotInitializedError` at runtime when resolved from a too-shallow container. It fails loudly (no silent corruption), just later than `validate()` ideally would.
- **Why deferred:** a proper fix needs `validate()` to track the *effective minimum scope* reachable through alias indirection, rather than checking each edge in isolation. That's its own small design + plan, not a one-line change.
- **Current mitigation:** documented as a caveat in `docs/providers/alias.md` (Validation section).
- **Pick-up:** scope-tracking pass in `Container.validate._visit` that propagates a "deepest reachable source scope" through `enforces_dependency_scope=False` edges and flags the caller if it's shallower.

## Propagate behavior changes to the sibling integration repos

**Source:** integrations live in separate repos (per `CLAUDE.md`): `modern-di-fastapi`, `modern-di-faststream`, `modern-di-litestar`, `modern-di-typer`, and `modern-di-pytest`.

Several changes from the 2026-06-12 audit (PRs #202, #203) may need verification or follow-up in those repos:

- **None-injection (Q-1/G-3, PR #203):** `X | None` params with no registered provider and no default now inject `None` instead of raising. Any integration relying on the old "raises if unregistered" behavior for optional params would now silently get `None`. Check for optional-typed injected params.
- **`CreatorCallError` / `ContainerClosedError` / `UnsupportedCreatorParameterError` (new exceptions):** integrations that catch broad `ResolutionError`/`ContainerError` are unaffected; any that match on specific exception types or raw `TypeError` from creator calls should be reviewed.
- **Close/reopen + `clear_cache=False` semantics (PR #202, X-1):** the FastStream test-broker pattern (reuse the same instance across the close→reopen cycle) is the motivating case — confirm `modern-di-faststream`'s fixtures still behave under the codified `ContainerClosedError`-on-closed + reopen-via-context-manager rules.
- **`expose()` duplicate-name `ValueError` (D-5):** `modern-di-pytest`'s `expose(*groups)` is the actual owner of the attribute-name-collision `ValueError` (the main repo's `Container` keys on `bound_type` only). No change needed, but the main-repo docs now point here — keep `expose()`'s behavior matching that description.

- **Why deferred:** separate repositories; out of scope for the main-repo audit branch.
- **Pick-up:** clone each sibling, run its suite against the latest `modern-di`, and check the four bullets above.
