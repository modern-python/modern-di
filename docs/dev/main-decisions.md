# Main decisions
1. Dependency resolving is async and sync:
   - if resolving requires event loop in sync mode `RuntimeError` is raised;
   - framework was developed mostly for usage with async python applications;
   - sync resolving is also possible, but it will fail in runtime in case of unresolved async dependencies;
2. No global state -> all state lives in containers:
   - it's needed for scopes to work;
3. Focus on maximum compatibility with mypy:
   - no need for `# type: ignore`
   - no need for `typing.cast`
