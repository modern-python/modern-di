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

<!-- invisible-code-block: python
import sys
import types

import grpc


class HelloRequest(types.SimpleNamespace):
    pass


class HelloReply(types.SimpleNamespace):
    pass


class GreeterServicer:
    pass


def add_GreeterServicer_to_server(servicer: GreeterServicer, target: grpc.Server) -> None:
    handler = grpc.unary_unary_rpc_method_handler(servicer.SayHello)
    target.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("helloworld.Greeter", {"SayHello": handler}),))


def offline_server(*args: object, **kwargs: object) -> grpc.Server:
    built = real_grpc_server(*args, **kwargs)
    built.add_insecure_port = lambda address: 0
    built.start = lambda: None
    built.wait_for_termination = lambda timeout=None: True
    return built


myapp_module = types.ModuleType("myapp")
pb2_module = types.ModuleType("myapp.greeter_pb2")
pb2_grpc_module = types.ModuleType("myapp.greeter_pb2_grpc")
pb2_module.HelloRequest = HelloRequest
pb2_module.HelloReply = HelloReply
pb2_grpc_module.GreeterServicer = GreeterServicer
pb2_grpc_module.add_GreeterServicer_to_server = add_GreeterServicer_to_server
myapp_module.greeter_pb2 = pb2_module
myapp_module.greeter_pb2_grpc = pb2_grpc_module
sys.modules.update({"myapp": myapp_module, "myapp.greeter_pb2": pb2_module, "myapp.greeter_pb2_grpc": pb2_grpc_module})
real_grpc_server = grpc.server
grpc.server = offline_server
del HelloRequest, HelloReply, GreeterServicer, add_GreeterServicer_to_server
-->

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
    def __init__(self, settings: Settings, context: grpc.ServicerContext) -> None:
        self._settings = settings                  # APP-scoped, injected by type
        self._context = context                    # REQUEST context object, injected by type

    def line(self) -> str:
        return f"{self._settings.service_name} <- {self._context.peer()}"


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


container = Container(groups=[AppGroup])
server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=10),
    interceptors=[DIInterceptor(container)],
)
greeter_pb2_grpc.add_GreeterServicer_to_server(GreeterService(), server)
container.validate()  # after DIInterceptor(container) — it registers ServicerContext's provider
server.add_insecure_port("[::]:50051")
server.start()
try:
    server.wait_for_termination()
finally:
    server.stop(grace=5).wait()   # let in-flight RPCs finish before APP finalizers run
    container.close_sync()
```

<!-- invisible-code-block: python
from unittest import mock

grpc.server = real_grpc_server
container.open()
peer_context = mock.Mock(spec=grpc.ServicerContext)
peer_context.peer.return_value = "ipv4:127.0.0.1:1"
say_hello = DIInterceptor(container).intercept_service(
    lambda details: grpc.unary_unary_rpc_method_handler(GreeterService().SayHello), None
)
assert say_hello.unary_unary(greeter_pb2.HelloRequest(), peer_context).message == "catalog <- ipv4:127.0.0.1:1"
-->

Constructing `DIInterceptor(container)` registers the `ServicerContext` context
provider on the container automatically, with no separate setup call. Call
`container.validate()` after that construction, not before, for the same reason
described in [Writing an integration](writing-integrations.md#lifecycle-rules).

### 3. Async server (`grpc.aio`)

`DIAioInterceptor` is the async twin: pass it to `grpc.aio.server(...)` and write
`async def` servicer methods (server-streaming methods as `async` generators), or sync methods
[with a thread pool](#sync-methods-on-the-aio-server). The `AppGroup` and `container` from the
sync example work unchanged:

<!-- invisible-code-block: python
import asyncio

asyncio.set_event_loop(asyncio.new_event_loop())
-->

```python
import grpc
from modern_di_grpc import DIAioInterceptor, FromDI, inject


class GreeterService(greeter_pb2_grpc.GreeterServicer):
    @inject
    async def SayHello(
        self,
        request: greeter_pb2.HelloRequest,
        context: grpc.aio.ServicerContext,
        report: typing.Annotated[RpcReport, FromDI(RpcReport)],
    ) -> greeter_pb2.HelloReply:
        return greeter_pb2.HelloReply(message=report.line())


server = grpc.aio.server(interceptors=[DIAioInterceptor(container)])
```

<!-- invisible-code-block: python
del server
asyncio.get_event_loop().close()
asyncio.set_event_loop(None)
-->

`@inject` adapts to the method it decorates, whether a sync method, `async def`,
or async generator (server-streaming), so the same decorator works on any of the
four RPC types on either server.

#### Sync methods on the aio server

Since modern-di-grpc 4.1.0, the aio server also takes sync servicer methods when you create it
with `grpc.aio.server(migration_thread_pool=...)`, for example a `futures.ThreadPoolExecutor()`.
gRPC runs them in that pool, and `@inject` resolves from the per-call container. Before 4.1.0,
every sync method on an aio server with the interceptor failed, with or without `@inject`.

A cancelled server-streaming RPC is the one case where the child is not closed. When the client
cancels, gRPC never closes a sync method's generator on the aio server, so the child container stays
open and its REQUEST finalizers do not run. grpcio 1.83.1 does the same without the interceptor. On
the aio server, write server-streaming methods as async generators.

## Scopes

The integration opens one `Scope.REQUEST` child container per RPC call, for
all four RPC types (unary-unary, server-streaming, client-streaming, bidi). The
child is created when the RPC starts and closed when it ends. For a streaming
RPC it stays open for the whole stream and closes after the last message,
including on the error and client-cancellation paths (with one exception for
[sync methods on the aio server](#sync-methods-on-the-aio-server)). REQUEST-scoped providers
(and their finalizers) live for exactly one RPC. APP-scoped providers persist for
the life of the container.

The sync server closes each RPC's child with `close_sync()`, so an async finalizer on a
REQUEST-scoped provider fails the RPC with `StatusCode.UNKNOWN` and a `FinalizerError` in the
details. The aio server closes it with `close_async()`, where async finalizers run, except for a
sync method: its child is closed with `close_sync()`, as on the sync server.

There is no `Scope.SESSION` for gRPC: a streaming RPC is one method invocation,
modelled as a single REQUEST-scoped unit of work.

## Injecting the `ServicerContext`

The `ServicerContext` is injectable at `Scope.REQUEST`: the interceptor
registers `grpc_context_provider` on the container when constructed, and seeds the
live context per RPC. A factory can depend on it to read RPC metadata, the
deadline, or the peer:

```python
import grpc
from modern_di import Group, Scope, providers


def make_caller(context: grpc.ServicerContext) -> str:
    return context.peer()


class AppGroup(Group):
    caller = providers.Factory(make_caller, scope=Scope.REQUEST)
```

Annotate the parameter as `grpc.ServicerContext` on both servers. The aio interceptor stores
its context under that type too, and `grpc.aio.ServicerContext` is not a subclass of it, so a
factory parameter annotated `grpc.aio.ServicerContext` does not resolve.

The interceptor's provider has no default, so the context is required for a direct resolve and
for a required parameter. Outside an RPC no context is set, and resolving `caller` raises
`ContextValueNotSetError`.

A factory that must also resolve outside an RPC makes the parameter optional. With no context set
it gets `None`. See [Optional parameters](../providers/context.md#optional-parameters).

```python
def make_caller(context: grpc.ServicerContext | None = None) -> str:
    return context.peer() if context is not None else "unknown"


class AppGroup(Group):
    caller = providers.Factory(make_caller, scope=Scope.REQUEST)
```

The protobuf request `Message` is not exposed as a provider
(that would add a `protobuf` dependency); the request is already a servicer-method
argument.

## Root container lifecycle

gRPC has no server startup/shutdown hook, so the root container's lifecycle is
yours to own (as with Flask). Build the container, pass it to the interceptor, and
close it after the server stops to run APP-scoped finalizers. The sync example above
does this in a `finally`, so Ctrl+C still runs them. `server.stop(grace=5)` stops taking
new RPCs and gives the ones in flight up to 5 seconds to finish, and `.wait()` blocks until
the server has stopped, so the close does not run under them. On `grpc.aio`, use
`await server.stop(5)` and then `await container.close_async()`.

## Resolving without `@inject`

Inside a servicer method (or anything it calls during the RPC),
`fetch_di_container()` returns the current RPC's child container:

<!-- invisible-code-block: python
for stand_in in ("myapp", "myapp.greeter_pb2", "myapp.greeter_pb2_grpc"):
    sys.modules.pop(stand_in)
-->

<!-- raises: RuntimeError -->
```python
from modern_di_grpc import fetch_di_container

container = fetch_di_container()   # raises RuntimeError outside an intercepted RPC
```

## `*args` / `**kwargs`

gRPC always calls a servicer method as `(request, context)`, so `@inject` needs no
signature rewrite and puts no restriction on the method signature beyond the injected
parameters. The arq and Celery `@inject` decorators, by contrast, raise `TypeError` for a
task that declares `*args` or `**kwargs`.

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Lifecycle](../providers/lifecycle.md): finalizers and container teardown.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `DIInterceptor(container)` | `grpc.ServerInterceptor` for the sync thread-pool server. Opens a `Scope.REQUEST` child per RPC (`close_sync`); auto-registers `grpc_context_provider`. |
| `DIAioInterceptor(container)` | `grpc.aio.ServerInterceptor` for the async server. Same, with `close_async`, except that the child of a sync method, run in the server's `migration_thread_pool`, is closed with `close_sync`. |
| `FromDI(provider_or_type)` | Marker for `Annotated[T, FromDI(...)]` in servicer-method signatures; accepts a provider instance or a plain type. |
| `@inject` | Decorates a servicer method to resolve its `FromDI` parameters from the current RPC's child container; adapts to sync / async / async-generator methods. Raises `RuntimeError` naming `DIInterceptor` when the RPC did not pass through the interceptor. |
| `fetch_di_container()` | Returns the current RPC's child container (raises `RuntimeError` naming `DIInterceptor` outside an intercepted RPC). |
| `grpc_context_provider` | `ContextProvider` exposing `grpc.ServicerContext` at `Scope.REQUEST`; auto-registered by the interceptor. |
