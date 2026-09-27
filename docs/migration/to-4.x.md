# Migration guide: upgrading to modern-di 4.x

This document describes the changes required to migrate from modern-di 3.x to modern-di 4.0. It
grows as 4.0 changes land; the [4.0 milestone](https://github.com/modern-python/modern-di/milestone/3)
lists what is planned.

## `find_container` no longer redirects navigation

A generated resolver reads the resolving container's `_scope_map` directly for a dependency at an
ancestor scope, and calls `find_container` only when the scope is not an ancestor, to raise
`ScopeNotInitializedError` or `ScopeSkippedError`. Through 3.x every cross-scope hop went through
`find_container`, and [Advanced / low-level API](../providers/advanced-api.md#find_containerscope)
named it as the one method a `Container` subclass could override to redirect navigation. That
override point is gone: a subclass override runs only on the miss path.

No integration or documented pattern relied on it. If yours did, build the tree you want with
`build_child_container` instead of redirecting lookups. Measured on the guard tier, the change is
−17% on a cross-scope resolve (G5) and −11% on a context resolve (G9), with every other scenario
within 1%.
