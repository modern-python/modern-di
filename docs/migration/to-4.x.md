# Migration guide: upgrading to modern-di 4.x

This document describes the changes required to migrate from modern-di 3.x to modern-di 4.0.

## Key changes

### `Container` takes only `scope` positionally

Every `Container` argument after `scope` is keyword-only: `Container(Scope.APP, None)` raises
`TypeError`, so pass `parent_container=`, `context=`, `groups=` and `use_lock=` by name.
