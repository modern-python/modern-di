---
status: accepted
summary: The 8 integrations scoring D3<2 in the blessed-ready audit stay as-is — the root-lifecycle gaps are inherent framework-lifecycle limits plus the deliberate caller-owns-root contract, not fixable ergonomics; typer's callback fix considered and deferred.
supersedes: null
superseded_by: null
---

# D3 root-lifecycle gaps are inherent — no integration code changes

**Decision:** The 8 integrations scoring D3<2 (lifespan handled for the user) in
the [blessed-ready on-ramp audit](../audits/2026-07-22-blessed-ready-onramp-report.md)
keep their current lifecycle handling. The gaps are inherent framework-lifecycle
limits plus the deliberately-chosen caller-owns-root contract, so the treatment
is this documented rationale, not integration code.

## Context

The audit's **D3** dimension scores whether `setup_di` owns *both* the root
open/close and the per-unit-of-work child, with no documented deployment context
where the root fails to open. Its bar gives **1** when one side is owned or a
documented root-open caveat exists, and **0** when the user wires both sides. Of
the 12 integrations, four clear it (aiogram, aiohttp, arq, litestar); the other
eight are below, in two shapes. The question this reopens: are any of the eight a
*fixable* ergonomics gap, or are they inherent framework behavior the score
merely reflects.

Per-integration verdict (fixable vs inherent):

| Integration | D3 | Root open/close | Why inherent |
|---|---|---|---|
| fastapi | 1 | `setup_di` owns both | ASGI lifespan is optional — a mounted sub-app / `lifespan="off"` never fires it; a real, documented deployment caveat, not a code gap |
| starlette | 1 | `setup_di` owns both | Same ASGI-lifespan-optional caveat |
| faststream | 1 | `setup_di` owns both | `TestBroker`/`TestApp` deliberately skip `on_startup`; a test-mode caveat, documented |
| taskiq | 1 | `setup_di` owns both | `run_receiver_task(run_startup=False)` skips the startup hook by default; documented |
| celery | 1 | root owned; per-task child owned by `@inject`/`DITask` | `task_always_eager` bypasses the worker signals that open the root; documented |
| flask | 1 | child owned; root is the caller's | Flask has **no app-shutdown hook**, so the root *close* is unavoidably the caller's |
| grpc | 1 | per-RPC child owned; root is the caller's | The server's `start()`/`stop()` is caller-owned; the integration's seam is the interceptor, not the server lifecycle |
| typer | 0 | neither owned by `setup_di` | Callback hook *does* exist (the one fixable case) — see below |

## Decision & rationale

**Category A (fastapi, starlette, faststream, taskiq, celery) — nothing to fix.**
`setup_di` already owns both sides; each scores 1 *only* because a documented
execution-context caveat exists, and every one of those caveats is real framework
behavior: ASGI's lifespan scope is optional, test brokers deliberately skip
startup hooks, `run_startup` defaults off, eager execution bypasses worker
signals. No code closes a caveat the framework itself imposes. These are already
captured in the [lifecycle rules](../../docs/integrations/writing-integrations.md#lifecycle-rules)
and the per-integration deployment caveats added in
[`2026-07-21.01`](../changes/2026-07-21.01-integration-open-lifecycle-lessons.md).

**Category B (flask, grpc) — root ownership is the caller's, by design.** Flask
has no app-shutdown hook and gRPC's server lifecycle is caller-owned, so the root
*close* is inherently the caller's. Owning the root *open* in Flask's `setup_di`,
or adding a gRPC server-wrapper helper, would add machinery and revisit the
contract the lifecycle rules already state deliberately — *"if the framework
offers no lifecycle hook at all, the root's open/close is the caller's to own —
document it."* The gain (removing one `open()`/`with` line the caller writes
once) does not justify a new contract or new API surface, against the
conservative-feature-set principle.

**typer — the one fixable case, deferred.** typer is the lone D3=0 and the only
one with an available hook (a Typer/Click callback could open the root and close
it via `ctx.call_on_close`). It is declined for now because:

- The 0 is largely a **scoring artifact** — the command child *is* owned (inside
  `@inject`'s `_build_command_container`); only the root is left to the caller,
  and an explicit `with container:` is the right idiom for a short-lived CLI
  process, not a footgun.
- Auto-owning the root via an integration-injected callback adds hidden control
  flow and must compose with a user's own `@app.callback()` (non-trivial in
  Click) — real machinery to replace a one-line `with container:` on a process
  that exits in milliseconds.

**Consistency.** This is the same call as `@inject` being ruled inherent (audit
§2 D5: no framework exposes an unused injection seam) and the
[exec hot-path re-decline](2026-07-19-exec-hot-path-declined.md): keep the
conservative feature set and the explicit lifecycle; document the deliberate
stance rather than add machinery to move a score the framework, not modern-di,
holds down.

## Revisit trigger

A real user reporting friction with a specific integration's root-lifecycle
ergonomics — most plausibly the typer CLI, where the callback fix would then be
worth its composition cost. Also: if a Category-B framework gains a
startup/shutdown lifecycle hook it currently lacks, its `setup_di` should own the
root and this row is reopened.

## Amendment (2026-07-26)

The revisit trigger above fired: a maintainer-reported root-lifecycle friction —
the hard `ContainerClosedError` failure mode every documented caveat in this
audit relies on — was addressed on 2026-07-26 by making `open()` optional in the
core (`modern-di` 3.1: a root container is open from construction, and reusing
one after an explicit close warns and reopens instead of raising). That fix
landed in `modern_di.Container` itself, not in any
integration's `setup_di`/lifecycle wiring, so this decision's conclusion —
**no integration code changes** — still stands: every caveat this audit
documented changes failure mode (from a hard raise to "finalizers silently
don't run") rather than disappearing, and the per-integration deployment notes
were reworded to say so, but no integration's lifecycle code changed. Status
stays `accepted`.
