# No blessed registration-introspection seam for grpc

**Decision:** no `Container.is_registered(type)` and no idempotent `add_providers` mode.
`modern-di-grpc` keeps its local guard (`find_provider(ServicerContext) is None` before
registering), which it needs because constructing an interceptor is its setup and two interceptors
may share one container.

**Why:** grpc is the only consumer; no other adapter reads `providers_registry` or
`find_provider`. One consumer is a hypothetical seam. Both members grpc uses are already public, so
it is using a lower-level API rather than breaching encapsulation, and `add_providers`' strictness
is a feature that an `ignore_existing` mode would loosen for everyone to serve one adapter.
