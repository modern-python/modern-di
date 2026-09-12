# Root-lifecycle gaps in the integrations are inherent

**Decision:** the integrations whose `setup_di` does not own both the root open/close and the
per-unit-of-work child keep their current lifecycle handling. The gaps are framework limits plus
the deliberate caller-owns-root rule, so the treatment is this record and the deployment notes, not
code.

| Integration | Root open/close | Why |
|---|---|---|
| fastapi, starlette | `setup_di` owns both | ASGI lifespan is optional and may never fire |
| faststream | `setup_di` owns both | `TestBroker` / `TestApp` skip `on_startup` |
| taskiq | `setup_di` owns both | `run_receiver_task(run_startup=False)` skips the hook |
| celery | root owned; per-task child by `@inject` / `DITask` | `task_always_eager` bypasses worker signals |
| flask | child owned; root is the caller's | Flask has no app-shutdown hook |
| grpc | per-RPC child owned; root is the caller's | `start()` / `stop()` is caller-owned |
| typer | neither | a Click callback could own the root, deferred: hidden control flow in a millisecond process |

**Why:** the first four already own both sides and fall short only through documented framework
behaviour. flask and grpc give the root to the caller by the lifecycle rule (no framework hook, the
caller owns it). Since 3.1 a root is open from construction and reuse after close warns and
reopens, so each caveat changed failure mode (a hard raise became "finalizers silently do not run")
without any integration's code changing.
