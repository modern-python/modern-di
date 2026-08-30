# Integration kit is low-level primitives in core, and outliers bypass it

**Decision:** the shared adapter skeleton lives in a framework-agnostic module inside core, exposing
only low-level primitives; genuine outliers call `build_child_container` directly rather than the
primitives growing parameters to swallow them.

- **In core, not a new package.** The skeleton imports only stdlib + `modern_di`, so it does not
  threaten the zero-dependency stance, and it deepens the `add_providers`/`resolve_dependency` seam
  core already blesses. A 14th repo would add coordinated-release cost for agnostic code every
  adapter already reaches through its `modern-di` dependency.
- **Low-level primitives only.** A `make_inject` convenience fails the deletion test: the adapters'
  wrapper shapes are not identical (each fetches the child differently — request, ASGI scope, `g`,
  contextvar), so the convenience would take a `get_container` callable and wrap three primitives —
  a shallow module, exactly what the extraction exists to remove.
- **Outliers bypass.** Each absorbing parameter (scope-resolver callable, post-build `set_context`
  hook, no-context mode) is needed by exactly one adapter — a hypothetical seam. Adding them taxes
  the ten common-case adapters; keeping weird logic in the weird adapter is better locality.

Reading all 13 adapters concretely narrowed what "bypass" means: only **typer** is a true Layer-1
bypass (it binds no connection at all). aiohttp and grpc both use `bind(provider, connection)` and
only skip `classify_connection` — aiohttp because both its providers share one type so `isinstance`
cannot dispatch, grpc because it has one provider and no dispatch to do; grpc's `_build_child`
collapses to one `bind()` call, dropping its post-hoc `set_context`. aiogram's context is a
multi-provider merge with a hardcoded scope, a third shape `bind()` does not fit, so it stays a
two-line literal. No primitive grew a parameter for any of them.

**Revisit trigger:** a third adapter needs the same non-`isinstance` scope-dispatch (making the
absorb-it seam real under the two-adapter rule), or adapter authors request the convenience layer
because the residual `inject` glue proves non-trivial in practice.
