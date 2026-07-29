---
summary: Opt-in DEBUG resolution tracing through a module-level `logging.getLogger("modern_di")` — narrating resolve start, cache hit vs creator call, override short-circuit, context reads, and finalizer order, all silent under default logging config.
---

# Opt-in DEBUG resolution tracing

A module-level `logging.getLogger("modern_di")` that narrates resolution at DEBUG
level: resolve start (provider, scope, container), cache hit against creator call,
override short-circuit, context reads, and finalizer order at close. All of it is
dropped by default logging configuration, so it costs nothing to a user who does
not opt in.

## Why it is open

Field precedent: Uber Fx narrates lifecycle events; Koin exposes an opt-in
`logger(Level.DEBUG)`. Both treat "why did the container do that" as a first-class
diagnostic rather than a debugging exercise for the library author.

Cost: one `isEnabledFor(DEBUG)` boolean per chokepoint on the hot path, plus 5-8
log statements threaded through resolution code.

The shape matters. A *pluggable structured event-logger subsystem* — Fx's
`fxevent.Logger`, Koin's Logger abstraction — was considered alongside this and
rejected against the conservative-feature-set principle: it is a public event API
to maintain forever, and an invented event vocabulary to keep stable. The
narration value is real; it should ride stdlib logging rather than a bespoke
event system. If this is ever built, build it as the logger, not the subsystem.

## Revisit trigger

The first user issue that a resolution trace would have answered.
