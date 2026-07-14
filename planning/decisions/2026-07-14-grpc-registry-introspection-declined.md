---
status: accepted
summary: Decline a blessed provider-introspection seam (container.is_registered) for grpc's idempotent registration — one consumer is a hypothetical seam; grpc keeps its local guard.
supersedes: null
superseded_by: null
---

# No blessed provider-introspection seam for grpc's registry drill

**Decision:** Do not add `Container.is_registered(type)` (or an
idempotent-`add_providers` mode) for adapters to query registration state
(Candidate 5 from the 2026-07-13 architecture review). `modern-di-grpc`
keeps its local `_ensure_context_provider` guard.

## Context

`modern-di-grpc`'s `_ensure_context_provider` calls
`container.providers_registry.find_provider(ServicerContext) is None` before
`container.add_providers(grpc_context_provider)`, to register the context
provider idempotently. grpc has no `setup_di` — constructing an interceptor
*is* the setup, and both interceptors (sync `DIInterceptor` + async
`DIAioInterceptor`) may be built on one container, so the guard prevents a
`DuplicateProviderTypeError` from `add_providers`. The review read this as
grpc "reaching past the blessed seam" and proposed a blessed
`is_registered` query. The integration-kit design deferred it as a distinct
change ([2026-07-13-integration-kit-shape](2026-07-13-integration-kit-shape.md)
non-goals).

Options on the table: (a) bless `container.is_registered(type)` and convert
grpc; (b) add an `ignore_existing` mode to `add_providers` so grpc registers
unconditionally; (c) close it — keep grpc's local guard.

## Decision & rationale

Chose (c). The deciding evidence: **grpc is the only consumer** — a grep
across every `modern-di-*` adapter and its tests found no other reader of
`providers_registry` / `find_provider`. By the project's standing rule (one
adapter = hypothetical seam, two = a real one — the same principle that kept
the integration-kit outliers' logic local rather than growing the primitives),
a single consumer does not justify new core API.

Reinforcing it: `container.providers_registry` and `find_provider` are both
**public** — grpc is using a lower-level public API, not breaching
encapsulation. And `add_providers`' strictness (raising on a duplicate
`bound_type`) is a deliberate feature that catches accidental
double-registration; option (b) would loosen it globally to serve one
adapter, a large blast radius. grpc's guard is two legible, local lines that
belong with grpc's unusual "the interceptor is the setup" shape.

## Revisit trigger

A **second** adapter needs to query registration state (making the seam real
under the two-adapter rule), or a decision to privatize
`container.providers_registry` as an implementation detail — at which point a
blessed `is_registered` becomes the migration path for grpc.
