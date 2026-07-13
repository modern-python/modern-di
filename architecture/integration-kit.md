# Integration Kit

Framework-agnostic primitives for building a **modern-di integration** — the
shared skeleton every framework adapter (FastAPI, Starlette, gRPC, ...) needs,
extracted so it has one home instead of thirteen. Lives in
`modern_di/integrations.py`. See
[docs/integrations/writing-integrations.md](../docs/integrations/writing-integrations.md)
for the user-facing spec an integration author follows; this page is the
capability's truth home.

## Layer 1 — connection derivation

`ConnectionMatch(scope, context)` pairs a child container's intended scope with
the context dict `build_child_container(context=...)` expects.

`bind(provider, connection) -> ConnectionMatch` derives both from one
`ContextProvider` and one connection object: `scope=provider.scope`,
`context={provider.context_type: connection}`. Neither `bind` nor
`classify_connection` calls `build_child_container` itself — the caller's own
call stays the single, un-wrapped way to open a child; these functions only
decide what to pass it.

`classify_connection(connection, providers) -> ConnectionMatch | None` is
isinstance-over-tuple dispatch built on `bind`: the first provider whose
`context_type` `connection` is an instance of wins. Returns `None` — never
raises — on no match, matching every dispatch adapter's existing fallback of
opening an auto-scoped, context-less child.

Not every adapter's shape fits either primitive. A single-connection-kind
adapter with no context to inject (a CLI command) has nothing to derive and
calls `build_child_container(scope=...)` directly. A multi-provider fan-in that
merges several providers' context into one child at a hardcoded scope (rather
than deriving scope from any one of them) also bypasses both — see
[decisions/2026-07-13-integration-kit-shape.md](../planning/decisions/2026-07-13-integration-kit-shape.md)
for which adapters land where.

## Layer 2 — the `Annotated` marker injector

`Marker(dependency)` is what `resolve_dependency` should resolve for one
`Annotated[T, marker]` parameter; `dependency` is an `AbstractProvider` or a
bare type, exactly `resolve_dependency`'s own accepted shape.
`Marker.resolve(container)` resolves it — the shape every native-DI
integration's own per-parameter resolver (`Dependency.__call__`) already had,
now shared instead of duplicated per adapter.

`from_di(dependency) -> T` is the default `Marker` factory —
`Annotated[T, from_di(dep)]` type-checks as `T` via `typing.cast`. Integrations
with their own per-handler injection seam (FastAPI's `Depends`, Litestar's
`Provide`) define their own factory that wraps a `Marker` instead; the rest
re-export `from_di` verbatim as their public `FromDI`.

`parse_markers(func) -> dict[str, Marker]` scans `func`'s `Annotated`
parameter hints once, at decoration time, and returns every parameter whose
metadata holds a `Marker` — the first one found per parameter, `return` never
scanned. `resolve_markers(container, markers) -> dict[str, Any]` resolves each
by name. Together these are the `_parse_inject_params`/resolve pair that was
duplicated near-verbatim across every integration without native DI.

## Double-wrap guard

`is_injected(func)` / `mark_injected(wrapper)` read and set one shared
attribute flag (`__modern_di_injected__`). An adapter whose auto-inject sweep
can visit the same handler twice (a shared view function registered under two
routes, a handler re-wrapped on plugin re-init) marks it on first wrap and
skips on the next. Adapters with no auto-inject sweep — a single `@inject` per
handler is never applied twice — have no need for either.

## What stays per-adapter

Root-container lifecycle (open/close, where it's attached to framework state),
where the per-connection child is stashed and read back, `close_sync` vs
`close_async`, and any handler-signature rewriting (stripping a parameter,
inserting a context object) are irreducibly framework-specific and are not
part of this module. See
[docs/integrations/writing-integrations.md](../docs/integrations/writing-integrations.md)
for the full contract an integration implements around these primitives.
