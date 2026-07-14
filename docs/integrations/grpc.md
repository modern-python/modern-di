# Usage with `gRPC`

## How to use

### 1. Install `modern-di-grpc`

=== "uv"

      ```bash
      uv add modern-di-grpc
      ```

=== "pip"

      ```bash
      pip install modern-di-grpc
      ```

=== "poetry"

      ```bash
      poetry add modern-di-grpc
      ```

### 2. Apply to your application (sync server)

`DIInterceptor` is a `grpc.ServerInterceptor`; pass it to `grpc.server(...)`. It
opens one `Scope.REQUEST` child container per RPC and resolves `FromDI`-annotated
parameters of `@inject`-decorated servicer methods.

```python
import typing
from concurrent import futures

import grpc
from modern_di import Container, Group, Scope, providers
from modern_di_grpc import DIInterceptor, FromDI, inject

from myapp import greeter_pb2, greeter_pb2_grpc   # your generated stubs


class Settings:
    def __init__(self) -> None:
        self.service_name = "catalog"


class RpcReport:
    def __init__(self, settings: Settings, context: grpc.ServicerContext | None = None) -> None:
        self._settings = settings                  # APP-scoped, injected by type
        self._context = context                    # REQUEST context object, injected by type

    def line(self) -> str:
        peer = self._context.peer() if self._context is not None else "unknown"
        return f"{self._settings.service_name} <- {peer}"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    rpc_report = providers.Factory(RpcReport, scope=Scope.REQUEST)


class GreeterService(greeter_pb2_grpc.GreeterServicer):
    @inject
    def SayHello(
        self,
        request: greeter_pb2.HelloRequest,
        context: grpc.ServicerContext,
        report: typing.Annotated[RpcReport, FromDI(RpcReport)],   # resolve by type
    ) -> greeter_pb2.HelloReply:
        return greeter_pb2.HelloReply(message=report.line())


container = Container(groups=[AppGroup], validate=True)
server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=10),
    interceptors=[DIInterceptor(container)],
)
greeter_pb2_grpc.add_GreeterServicer_to_server(GreeterService(), server)
server.add_insecure_port("[::]:50051")
server.start()
server.wait_for_termination()
```

Constructing `DIInterceptor(container)` registers the `ServicerContext` context
provider on the container automatically — no separate setup call.

### 3. Async server (`grpc.aio`)

`DIAioInterceptor` is the async twin — pass it to `grpc.aio.server(...)` and write
`async def` servicer methods (server-streaming methods as `async` generators):

```python
import grpc
from modern_di_grpc import DIAioInterceptor, FromDI, inject


class GreeterService(greeter_pb2_grpc.GreeterServicer):
    @inject
    async def SayHello(
        self,
        request: greeter_pb2.HelloRequest,
        context: grpc.aio.ServicerContext,
        greeter: typing.Annotated[Greeter, FromDI(Greeter)],
    ) -> greeter_pb2.HelloReply:
        return greeter_pb2.HelloReply(message=greeter.greet(request.name))


server = grpc.aio.server(interceptors=[DIAioInterceptor(container)])
```

`@inject` adapts to the method it decorates — sync method, `async def`, or async
generator (server-streaming) — so the same decorator works on any of the four RPC
types on either server.

## Scopes

The integration opens one `Scope.REQUEST` child container **per RPC call**, for
all four RPC types (unary-unary, server-streaming, client-streaming, bidi). The
child is created when the RPC starts and closed when it ends — for a streaming
RPC it stays open for the whole stream and closes after the last message,
including on the error and client-cancellation paths. REQUEST-scoped providers
(and their finalizers) live for exactly one RPC. APP-scoped providers persist for
the life of the container.

There is no `Scope.SESSION` for gRPC — a streaming RPC is one method invocation,
modelled as a single REQUEST-scoped unit of work.

## Injecting the `ServicerContext`

The `ServicerContext` is injectable at `Scope.REQUEST` — the interceptor
registers `grpc_context_provider` on the container when constructed, and seeds the
live context per RPC. A factory can depend on it to read RPC metadata, the
deadline, or the peer:

```python
import grpc
from modern_di import Group, Scope, providers


def make_caller(context: grpc.ServicerContext | None = None) -> str:
    return context.peer() if context is not None else "unknown"


class AppGroup(Group):
    caller = providers.Factory(make_caller, scope=Scope.REQUEST)
```

The `| None = None` default lets the provider construct at validation time, when
no context is set. The protobuf request `Message` is **not** exposed as a provider
(that would add a `protobuf` dependency); the request is already a servicer-method
argument.

## Root container lifecycle

gRPC has no server startup/shutdown hook, so the **root container's lifecycle is
yours to own** (as with Flask). Create the container open, pass it to the
interceptor, and close it after the server stops to run APP-scoped finalizers:

```python
server.stop(grace=5).wait()
container.close_sync()          # or: await container.close_async() on grpc.aio
```

## Resolving without `@inject`

Inside a servicer method (or anything it calls during the RPC),
`fetch_di_container()` returns the current RPC's child container:

```python
from modern_di_grpc import fetch_di_container

container = fetch_di_container()   # raises LookupError outside an intercepted RPC
```

## `*args` / `**kwargs`

Unlike the Celery/Typer decorator integrations, gRPC always calls a servicer
method as `(request, context)`, so `@inject` needs no signature rewrite and
imposes no restriction on the method signature beyond the injected parameters.

## See also

- [Testing with overrides](../recipes/testing-overrides.md) — swap providers in your tests.
- [Lifecycle](../providers/lifecycle.md) — finalizers and container teardown.
- [Scopes](../providers/scopes.md) — the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `DIInterceptor(container)` | `grpc.ServerInterceptor` for the sync thread-pool server. Opens a `Scope.REQUEST` child per RPC (`close_sync`); auto-registers `grpc_context_provider`. |
| `DIAioInterceptor(container)` | `grpc.aio.ServerInterceptor` for the async server. Same, with `close_async`. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in servicer-method signatures; accepts a provider instance or a plain type. |
| `@inject` | Decorates a servicer method to resolve its `FromDI` parameters from the current RPC's child container; adapts to sync / async / async-generator methods. |
| `fetch_di_container()` | Returns the current RPC's child container (raises `LookupError` outside an RPC). |
| `grpc_context_provider` | `ContextProvider` exposing `grpc.ServicerContext` at `Scope.REQUEST`; auto-registered by the interceptor. |
