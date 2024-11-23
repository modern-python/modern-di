# Development Notes
## Main decisions
1. Dependency resolving is async and sync:
  - if resolving requires event loop in sync mode `RuntimeError` is raised;
  - framework was developed mostly for usage with async python applications;
  - sync resolving is also possible, but it will fail in runtime in case of unresolved async dependencies;
2. Resources and singletons are safe for concurrent resolving:
  - in async resolving `asyncio.Lock` is used;
  - in sync resolving `threading.Lock` is used;
3. No global state -> all state lives in containers:
  - it's needed for scopes to work;
4. Focus on maximum compatibility with mypy:
  - no need for `# type: ignore`
  - no need for `typing.cast`

## Base parts
### Scope
- any int enum, starting from 1 with step 1;
- skipping scopes is allowed by explicit passing required scope when initializing `Container`.

### Container
- all states live in containers:
  - resolved dependencies;
  - context stacks for resources;
  - overrides;
- must have scope;
- can have link to parent container;

### Providers
- completely stateless
- if dependency is already saved or overridden in `Container`, returns it
- otherwise build dependency and save it to `Container`
- can have dependencies only the same or lower scope, check in init

### Graph
- Cannot be instantiated
- Contains graph of `Providers`
- Can initialize its resources and singletons to container

## Questions
1. Is configuration needed inside DI or global object is OK?
