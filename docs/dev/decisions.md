# Decisions
1. Dependency resolving is sync only since 2.x version
2. Singletons are thread-safe for concurrent resolving (`threading.Lock` is used)
3. No global state -> all state lives in containers and registries:
4. Focus on maximum compatibility with mypy:
  - No need for `# type: ignore`
  - No need for `typing.cast`
5. No adding new features while tasks can be solved by default implementation.
