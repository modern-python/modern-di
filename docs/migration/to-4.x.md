# Migration guide: upgrading to modern-di 4.x

This document describes the changes required to migrate from modern-di 3.x to modern-di 4.0.

## Key changes

### `Container` takes only `scope` positionally

Every `Container` argument after `scope` is keyword-only: `Container(Scope.APP, None)` raises
`TypeError`, so pass `parent_container=`, `context=`, `groups=` and `use_lock=` by name.

### Resolving on a closed container raises

In 3.x, resolving from a closed container, or through a child whose resolve reached a closed
ancestor, emitted `ContainerClosedWarning` and reopened it. In 4.0 the same call raises
`ContainerClosedError` and the container stays closed. `ContainerClosedWarning` is removed, so delete
any `filterwarnings` entry that names it. Where the reuse is deliberate, reopen the container first
with `open()` or by re-entering `with` / `async with`. See
[Troubleshooting: ContainerClosedError](../troubleshooting/container-closed-error.md).
