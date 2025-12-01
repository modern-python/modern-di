# Decisions
1. Dependency resolving is async and sync:
  - If resolving requires an event loop in sync mode, a `RuntimeError` is raised;
  - The framework was developed mostly for usage with async Python applications;
  - Sync resolving is also possible, but it will fail at runtime in case of unresolved async dependencies;
2. Resources and singletons are safe for concurrent resolving:
  - In async resolving, `asyncio.Lock` is used;
  - In sync resolving, `threading.Lock` is used;
3. No global state -> all state lives in containers and registries:
  - This is needed for scopes to work;
4. Focus on maximum compatibility with mypy:
  - No need for `# type: ignore`
  - No need for `typing.cast`
5. No adding new features while tasks can be solved by default implementation.
