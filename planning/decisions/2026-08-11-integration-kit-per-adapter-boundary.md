---
summary: Root-container lifecycle, per-connection child stash/read-back, sync-vs-async close, and handler-signature rewriting stay in each adapter — the integration kit does not absorb them.
---

# What stays per-adapter is not part of the integration kit

**Decision:** Four responsibilities stay outside `modern_di.integrations` and are re-implemented by
each of the 13 framework adapters individually: root-container lifecycle (open/close, where it's
attached to framework state), where the per-connection child container is stashed and read back,
choosing `close_sync` vs. `close_async`, and any handler-signature rewriting (stripping a parameter,
inserting a context object). None of these move into the shared kit.

## Context

`modern_di.integrations` extracts what the 13 adapters duplicated near-verbatim: Layer 1
(`bind`, `classify_connection`) derives a child container's scope/context from `ContextProvider`s, and
Layer 2 (`Marker`, `from_di`, `parse_markers`, `resolve_markers`) is the `Annotated`-marker injector,
replacing the `_parse_inject_params`/resolve pair every non-native-DI integration had reimplemented.
The related decision [`2026-07-13-integration-kit-shape.md`](2026-07-13-integration-kit-shape.md)
settled the kit's overall shape (low-level primitives in core, outliers bypass rather than the
primitives absorbing them). This record is narrower: it's about the four things that were considered
for extraction *into* the kit and rejected, not about the outlier adapters that bypass it.

## Decision & rationale

Each of the four is irreducibly framework-specific in a way the shared primitives are not:

- **Root-container lifecycle** — *where* a framework hangs the root container (an ASGI app's
  `state`, a Celery worker's global, a Typer command's context object) and *when* it opens and closes
  it are governed entirely by that framework's own lifecycle hooks. There's no shared shape to
  extract; a common "lifecycle manager" would need a callback per framework anyway, which is just the
  per-adapter code with extra indirection.
- **Where the per-connection child is stashed and read back** — an HTTP framework has a request
  object, an ASGI framework has a scope dict, a message-queue framework has neither and uses a
  contextvar or a task-local. The storage medium varies by what the framework hands the adapter, not
  by anything modern-di controls.
- **`close_sync` vs. `close_async`** — which one an adapter calls depends on whether the framework's
  own request/task teardown hook is sync or async, which is a property of the framework's execution
  model, not of the container.
- **Handler-signature rewriting** — stripping an injected parameter or inserting a context object
  before calling the user's handler requires knowing that framework's handler-calling convention
  (decorator-wrapped function, class-based view method, positional vs. keyword dispatch). There is no
  framework-agnostic way to rewrite "a handler" in general.

**Rejected alternative: grow the primitives to absorb these.** This was the same shape of argument
`2026-07-13-integration-kit-shape.md` already settled for the three concrete outliers (aiohttp
websocket probe, grpc `set_context` split, typer no-context) — an absorbing parameter needed by one
adapter taxes the other adapters and lowers the kit's depth. These four are the general case of that
same argument: each is needed by *every* adapter, but in a *different shape* per adapter, so there is
no single parameter or callback that would fit all 13 without becoming a second, parallel dispatch
mechanism duplicating what the framework already provides.

The full contract an integration implements around the shared primitives — including these four
per-adapter responsibilities — is documented in
[docs/integrations/writing-integrations.md](../../docs/integrations/writing-integrations.md).

## Revisit trigger

A second and third adapter converge on the *same* concrete shape for stashing the per-connection
child, or for signature rewriting — not just the same responsibility, but the same mechanism — making
a shared helper a two-adapters-rule extraction rather than a hypothetical one, the same bar
`2026-07-13-integration-kit-shape.md` used for its outliers.
