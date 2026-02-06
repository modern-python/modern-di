# Key concepts

## Scope

- Is a lifespan of a dependency;
- Equal to APP by default;
- In frameworks' integrations some scopes are entered automatically;
- Dependencies of cached **Factory** providers are cached for the lifespan of their scope;

### Default scopes

**APP**:

   - Tied to the entire application lifetime;
   - Can be used for cached **Factory** providers;

**SESSION**:

   - For websocket session lifetime;
   - Dependencies of this scope cannot be used for http-requests;
   - Managed automatically in integrations;

**REQUEST**:

   - For dependencies which are created for each user request, for example database session;
   - Managed automatically for http-request;
   - Must be managed manually for websockets;

**ACTION**:

   - For lifetime less than request;
   - Must be managed manually;

**STEP**:

   - For lifetime less than **ACTION**;
   - Must be managed manually.

### How to choose scope

Provider's scope must be max value between scopes of all its dependencies.

Examples:
- A provider has dependencies of `APP` and `REQUEST` scopes. Final scope should be `REQUEST`.
- A provider has no dependencies. Final scope should be `APP`.
- A provider has dependencies only of `APP` scope. Final scope should be `APP`.

## Provider

Providers are needed to describe, how to assemble objects.
They retrieve the underlying dependencies and inject them into the created object.
This causes a cascade effect that helps to assemble object graphs.

## Container

Each container is assigned to a certain scope.
A nested scope contains a link to its parent container.

All states live in containers:

- Assembled objects;
- Overrides for tests;

Container provides methods for resolving dependencies:

1. `resolve_provider(provider)` - Resolve a specific provider instance
2. `resolve(SomeType)` - Resolve by type

Container also provides methods for overriding providers with objects:

1. `override(provider, override_object)` - Override a provider with a mock object for testing
2. `reset_override(provider)` - Reset override for a specific provider
3. `reset_override()` - Reset all overrides

When resolving by type, the container looks for a provider that was registered with a matching `bound_type`.

The container itself can also be resolved as a dependency using `container.resolve(Container)`, which returns the same container instance.

## Group

A Group is a collection of providers. They cannot be instantiated.
