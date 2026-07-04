# that-depends or modern-di?

Both [`that-depends`](https://github.com/modern-python/that-depends) and
`modern-di` are dependency-injection frameworks from the same author, in the
[modern-python](https://github.com/modern-python) family. This page helps you
choose.

## Short answer

- **Starting a new project?** Use **modern-di**. It has explicit scopes, no
  global state, a small strictly-typed core, and separate framework adapters —
  see [Design decisions](design-decisions.md).
- **Already using that-depends?** It remains **actively maintained and
  production-proven** — you don't need to migrate. Move when you want explicit
  scopes or a no-global-state architecture; the
  [migration guide](../migration/from-that-depends.md) maps every concept across.

## How they differ

| | that-depends | modern-di |
|---|---|---|
| Status | actively maintained, production-proven | recommended for new projects |
| Resolution | async + sync (`AsyncFactory`, `await resolve`) | sync resolution (async finalizers supported) |
| Container model | the container class is both schema and runtime | `Group` (schema) and `Container` (runtime) are separate |
| Scopes | context-based lifetimes | explicit, enforced scope chain (APP→…→STEP) |
| Global state | resolves directly from the container class | none — you create and pass containers explicitly |
| Integrations | bundled | separate adapter packages (install only what you need) |

!!! note "\"Sync only\" means resolution, not teardown"
    modern-di resolves synchronously, but finalizers may be sync **or** async
    (`close_sync` / `close_async`), so async resource cleanup is fully
    supported. See [Lifecycle](../providers/lifecycle.md).

## Choose that-depends if…

- You specifically want **async resolution** (`await container.resolve(...)`).
  modern-di is sync-only by design and will not add async resolution.
- You want the **simplest possible** setup for a single service and don't need an
  explicit scope chain.
- You already run it in production and have no reason to change.

## Choose modern-di if…

- You're starting fresh and want **explicit scopes** and **no global state**.
- You want **one wiring across multiple entrypoints** (FastAPI + FastStream +
  Typer + workers) via official adapters.
- You value a **first-party pytest plugin** and a small, strictly-typed core.

## Migrating

The [migration guide](../migration/from-that-depends.md) covers every provider
type and concept, including the conceptual shifts: the schema/runtime split
(`Group` vs `Container`), sync-only resolution, and explicit scopes.

## See also

- [modern-di vs other libraries](comparison.md)
- [Design decisions](design-decisions.md)
