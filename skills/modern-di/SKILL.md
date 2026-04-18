---
name: modern-di
description: >
  Reference guide for the modern-di Python DI framework. Use this skill for ANY question about modern-di —
  scope hierarchy (Scope.APP/REQUEST/SESSION/ACTION), Group/Factory/CacheSettings declaration, Container
  resolution (resolve vs resolve_provider, build_child_container), ContextProvider for runtime values,
  framework integration via ModernDIPlugin or setup_di/FromDI, testing with container.override/reset_override,
  injecting Request objects into providers, and SQLAlchemy session wiring. Trigger on: modern-di,
  providers.Factory, CacheSettings, Scope.REQUEST, Scope.APP, build_child_container, ModernDIPlugin,
  setup_di, modern-di-litestar, modern-di-fastapi, container.override, resolve_provider. Don't skip this
  skill for questions that seem simple — modern-di has specific idioms (no Singleton class, sync-only
  resolution, hierarchical scopes) that differ from other DI frameworks.
---

# modern-di Skill

modern-di is a **zero-dependency** Python DI framework. It wires object graphs from type annotations,
manages lifetimes through hierarchical scopes, and supports sync/async finalizers.

## Navigation

This skill is split across focused reference files. Read the one that matches the task:

| File | When to read it |
|------|----------------|
| `common.md` | Core concepts: Group, Factory, Container, Scope, CacheSettings, ContextProvider |
| `litestar.md` | Litestar integration: ModernDIPlugin, FromDI, route handlers |
| `fastapi.md` | FastAPI integration: setup_di, FromDI, route handlers |
| `testing.md` | Testing: overrides, scope chains, pytest fixtures |

Read `common.md` first if the user is new to modern-di. For framework-specific questions, go directly to
`litestar.md` or `fastapi.md`. For testing questions, read `testing.md` (and `common.md` if needed for
context).

## Quick reference

```python
from modern_di import Container, Group, Scope, providers

class Dependencies(Group):
    db_engine = providers.Factory(
        scope=Scope.APP,
        creator=create_async_engine,
        cache_settings=providers.CacheSettings(finalizer=close_engine),
    )
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache_settings=providers.CacheSettings(finalizer=close_session),
    )

container = Container(scope=Scope.APP, groups=[Dependencies])
```

## Common errors

| Error | Fix |
|---|---|
| `Provider of type X not registered` | Add `providers.Factory(creator=X)` to your Group |
| `Provider of scope REQUEST cannot be resolved in container of scope APP` | Build a child container first |
| `Provider is duplicated by type X` | Set `bound_type=None` on one of the conflicting providers |
| `Argument X of type Y cannot be resolved` | Register a provider for that type or pass via `kwargs` |
