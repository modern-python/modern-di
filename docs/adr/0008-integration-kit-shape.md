# The integration kit is low-level primitives in core; outliers bypass it

**Decision:** the shared adapter skeleton lives in a framework-agnostic module in core and exposes
only low-level primitives. An adapter whose shape does not fit calls `build_child_container`
directly; the primitives do not grow parameters to absorb it.

**Why:** the skeleton imports only stdlib and `modern_di`, so it keeps the zero-dependency stance
and a separate package would only add release coordination. A `make_inject` convenience fails the
deletion test because each adapter fetches its child differently (request, ASGI scope, `g`,
contextvar). Every parameter proposed to absorb an outlier is needed by exactly one adapter, and a
one-consumer seam is hypothetical: keeping the odd logic in the odd adapter is better locality.
Reading all thirteen adapters, only typer bypasses the kit entirely; aiohttp and grpc skip only
connection classification.
