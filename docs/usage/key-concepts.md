# Key concepts

## Scope

- is a lifespan of a dependency;
- is required almost for each `Provider`;
- in frameworks' integrations some scopes are entered automatically;
- dependencies of `Resource` and `Singleton` provider cached for the lifespan of its scope;

**Default scopes**:
1. `APP`:
   - tied to the entire application lifetime;
   - can be used for singletons of `Resource` and `Singleton` providers;
   - must be managed manually in lifecycle methods of the application: see `integrations` section;
2. `SESSION`:
   - for websocket session lifetime;
   - dependencies of this scope cannot be used for http-requests;
   - managed automatically;
3. `REQUEST`:
   - for dependencies which are created for each user request, for example database session;
   - managed automatically for http-request;
   - must be managed manually for websockets;
4. `ACTION`:
   - for lifetime less than request;
   - must be managed manually;
5. `STEP`:
   - for lifetime less than `ACTION`;
   - must be managed manually.

## Provider

Providers needed to assemble the objects.
They retrieve the underlying dependencies and inject them into the created object.
It causes the cascade effect that helps to assemble object graphs.

More about providers:
- do not contain assembled objects:
  - `Singleton` and `Resource` objects are stored in `Container`;
  - `Factory` objects are built on each call.
- can have dependencies only of the same or more long-lived scopes:
  - `APP`-scoped provider can have only `APP`-scoped dependencies;
  - `SESSION`-scoped provider can have `APP` and `SESSION`-scoped dependencies, etc.;

## Container

Each container is assigned to a certain scope.
To enter a nested scope, a context manager should be used.
Nested scope contains link to parent container.

All states live in containers:
- assembled objects;
- context stacks for resources to finalize them at the end of lifecycle;
- overrides for tests;

## Graph

Graph is a collection of providers.

More about graphs:
- Cannot be instantiated;
- Can initialize its resources and singletons to container:
  - coroutine `async_resolve_creators` should be used to resolve asynchronously;
  - function `sync_resolve_creators` should be used to resolve synchronously.

