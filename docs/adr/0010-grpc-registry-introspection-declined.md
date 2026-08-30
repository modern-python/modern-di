# No blessed provider-introspection seam for grpc's registry drill

**Decision:** no `Container.is_registered(type)` and no idempotent-`add_providers` mode for adapters
to query registration state. `modern-di-grpc` keeps its local `_ensure_context_provider` guard,
which checks `find_provider(ServicerContext) is None` before registering — grpc has no `setup_di`
(constructing an interceptor *is* the setup) and both interceptors may be built on one container, so
the guard prevents a `DuplicateProviderTypeError`.

The deciding evidence: **grpc is the only consumer.** A grep across every `modern-di-*` adapter and
its tests found no other reader of `providers_registry` / `find_provider`, and by the standing rule
(one adapter is a hypothetical seam, two is a real one — the same principle that kept the
[integration-kit](0008-integration-kit-shape.md) outliers local) a single consumer does not justify
new core API. Reinforcing it: `container.providers_registry` and `find_provider` are both public, so
grpc is using a lower-level public API rather than breaching encapsulation; and `add_providers`'
strictness is a deliberate feature catching accidental double-registration, which an
`ignore_existing` mode would loosen globally to serve one adapter.

**Revisit trigger:** a **second** adapter needs to query registration state, or a decision to
privatize `container.providers_registry` — at which point a blessed `is_registered` becomes grpc's
migration path.
