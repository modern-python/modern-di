# Key concepts

## Scope

- Is a lifespan of a dependency;
- Is required for almost each provider;
- In frameworks' integrations some scopes are entered automatically;
- Dependencies of **Resource** and **Singleton** providers are cached for the lifespan of their scope;

### Default scopes

**APP**:

   - Tied to the entire application lifetime;
   - Can be used for singletons of **Resource** and **Singleton** providers;
   - In integrations managed automatically in lifecycle methods: see **integrations** section for more details;

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

Providers are needed to assemble objects.
They retrieve the underlying dependencies and inject them into the created object.
This causes a cascade effect that helps to assemble object graphs.

More about providers:

- Do not contain assembled objects:
    - **Singleton** and **Resource** objects are stored in the container;
    - **Factory** objects are built on each call.
- Can have dependencies only of the same or more long-lived scopes:
    - **APP**-scoped providers can have only **APP**-scoped dependencies;
    - **SESSION**-scoped providers can have APP and **SESSION**-scoped dependencies, etc.;

## Container

Each container is assigned to a certain scope.
To enter a nested scope, a context manager should be used.
A nested scope contains a link to its parent container.

All states live in containers:

- Assembled objects;
- Context stacks for resources to finalize them at the end of their lifecycle;
- Overrides for tests;

## Graph

A Graph is a collection of providers. They cannot be instantiated.
