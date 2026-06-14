# Testing

Two ways to wire `modern-di` into tests:

1. **Recommended — `modern-di-pytest`.** Generates pytest fixtures from your providers. One line per dependency, or one line for the whole `Group`. See the [pytest integration page](../integrations/pytest.md) for the full setup including `expose(...)`, `modern_di_fixture(...)`, child-container fixtures, and overrides.

2. **Plain `modern-di` (without the helper package).** Define `di_container` as a session-scoped pytest fixture using `Container(...)` as a context manager; build a request-container fixture from it; resolve dependencies inside tests with `container.resolve(...)`. See the [testing-with-overrides recipe](../recipes/testing-overrides.md) for a worked example.

For replacing dependencies in tests (mocks, transactional database sessions, etc.), see the [testing-with-overrides recipe](../recipes/testing-overrides.md).

!!! note "Overrides are tree-shared"
    `container.override()` and `container.reset_override()` operate on a registry shared by the entire container tree — parent and all children. Always `reset_override()` in a `finally` block or in a fixture that guarantees cleanup. Leaking overrides between tests is silent and painful.
