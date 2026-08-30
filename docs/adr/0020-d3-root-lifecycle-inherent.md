# D3 root-lifecycle gaps are inherent — no integration code changes

**Decision:** the eight integrations whose `setup_di` does not own both the root open/close and the
per-unit-of-work child keep their current lifecycle handling. The gaps are inherent framework limits
plus the deliberate caller-owns-root contract, so the treatment is this rationale, not code.

| Integration | Root open/close | Why inherent |
|---|---|---|
| fastapi | `setup_di` owns both | ASGI lifespan is optional — a mounted sub-app / `lifespan="off"` never fires it |
| starlette | `setup_di` owns both | Same ASGI-lifespan-optional caveat |
| faststream | `setup_di` owns both | `TestBroker`/`TestApp` deliberately skip `on_startup` |
| taskiq | `setup_di` owns both | `run_receiver_task(run_startup=False)` skips the startup hook by default |
| celery | root owned; per-task child owned by `@inject`/`DITask` | `task_always_eager` bypasses the worker signals that open the root |
| flask | child owned; root is the caller's | Flask has **no app-shutdown hook**, so the root *close* is unavoidably the caller's |
| grpc | per-RPC child owned; root is the caller's | `start()`/`stop()` is caller-owned; the integration's seam is the interceptor, not the server lifecycle |
| typer | neither owned by `setup_di` | A Click callback hook *does* exist — the one fixable case, see below |

**The first five have nothing to fix.** `setup_di` already owns both sides; each falls short only
because of a documented execution-context caveat, and every caveat is real framework behaviour. No
code closes a caveat the framework itself imposes; they are captured in the
[lifecycle rules](../integrations/writing-integrations.md#lifecycle-rules) and in each integration
page's deployment caveats.

**flask and grpc give the root to the caller by design.** Owning the root open in Flask's
`setup_di`, or adding a gRPC server-wrapper helper, would add machinery and revisit a contract the
lifecycle rules state deliberately — *if the framework offers no lifecycle hook at all, the root's
open/close is the caller's to own; document it.* Removing one `open()`/`with` line the caller writes
once does not justify new API surface.

**typer is the one fixable case, deferred.** A Typer/Click callback could open the root and close it
via `ctx.call_on_close`, but the command child *is* already owned inside `@inject`, an explicit
`with container:` is the right idiom for a process that exits in milliseconds, and an
integration-injected callback adds hidden control flow that must compose with a user's own
`@app.callback()` — non-trivial in Click.

**One-call-setup scores follow from this, not from anything separate.** Where a second wiring action
is required (flask, grpc, typer), that action *is* the manual root `open()` ruled inherent above —
there is no independent setup fix. Under these rulings the ceiling for integrations that own their
whole lifecycle is four: litestar, aiogram, aiohttp, arq. The other eight are each gated by a
framework-inherent root-lifecycle limit, with the revisit trigger below.

**Amendment (2026-07-26).** The trigger fired: maintainer-reported root-lifecycle friction — the
hard `ContainerClosedError` failure mode every caveat here relies on — was addressed by making
`open()` optional in core (3.1: a root is open from construction, and reuse after an explicit close
warns and reopens). That landed in `modern_di.Container`, not in any integration's wiring, so the
conclusion stands: every caveat changes failure mode (a hard raise becomes "finalizers silently do
not run") rather than disappearing, the deployment notes were reworded, and no integration's
lifecycle code changed.

**Revisit trigger:** a real user reporting friction with a specific integration's root-lifecycle
ergonomics — most plausibly typer, where the callback fix would then be worth its composition cost.
Also: a flask/grpc-shaped framework gaining a startup/shutdown hook it currently lacks, at which
point its `setup_di` should own the root and its row reopens.
