---
summary: Free-threaded (PEP 703) support is Beta, not Stable, because it relies on object-publication ordering that CPython's implementation provides but does not formally guarantee.
---

# Free-threaded support is Beta, not Stable

**Decision:** modern-di's free-threaded (PEP 703) support is labeled Beta. It stays Beta rather than
graduating to Stable until the one guarantee it currently borrows from CPython's implementation
behaviour, rather than from CPython's spec, is either formalized upstream or removed from modern-di's
own reliance.

## Context

Free-threaded CPython makes single built-in-container operations (`dict.setdefault`, `dict[k] = v`,
`dict.get`, `list.append`) internally atomic — no single such operation can corrupt the structure.
modern-di's concurrency design leans on that: every compound check-then-act sequence over shared state
in the resolve path is either idempotent (a rebuild-if-stale race just produces a duplicate, discarded
build) or already runs under the container's own lock. Registry *mutation* (`register`,
`add_providers`, removal) is guarded by the registry's own lock; the cycle-guard `_building` set is
thread-local, so a same-thread cycle is still caught while a concurrent first-resolve of the same
provider on another thread just compiles it independently.

That much is sound on the guarantees CPython actually documents. But one more thing is needed for
correctness: when one thread publishes a newly-built object (a compiled resolver, a cached instance)
by storing a reference where another thread will read it, the reading thread must see that object's
fully-initialized fields, not a partially-constructed one. That's object-publication ordering, and
CPython's language spec does not formally guarantee it — CPython publishes no memory model.

## Decision & rationale

**The gap is between implementation behaviour and spec guarantee, and that gap is exactly what Beta
means here.** In the current CPython implementation, publication that happens through a container's
internal critical section does provide the necessary ordering — so today's behaviour is correct on
every free-threaded build tested. But "correct because of how the interpreter happens to be built"
and "correct because the language promises it" are different claims, and only the second one is safe
to call Stable. A future CPython release is free to change unspecified implementation behaviour
without that being a compatibility break by CPython's own rules, even though it would be one for
modern-di's free-threaded users.

Two adjacent things are explicitly *not* what keeps this at Beta, and are worth separating out because
they get conflated with the ordering question:

- **Thread-safety itself is not in question.** Concurrent resolve is thread-safe under the compound-op
  analysis above; that part doesn't move.
- **Throughput is a separate, already-tracked concern.** Concurrent resolve is thread-safe but its
  throughput does not scale with thread count on a free-threaded build — diagnosed as atomic
  refcount contention on shared hot-path objects (the returned singleton value, then the shared
  provider objects, then the compiled-resolver closures' captured cells), not the per-container lock.
  That's a performance ceiling CPython itself would have to lift (deferred reference counting
  expanding to ordinary instances and cells), not a correctness gap, and it's tracked separately in
  [`2026-07-19-free-threaded-throughput.md`](../deferred/2026-07-19-free-threaded-throughput.md).

**Caveats that hold regardless of Beta/Stable status:** configure and close are single-threaded edges.
`override`/`reset_override` and `set_context` mutate shared state without a lock — racing them against
a live `resolve()` is inherently unordered, GIL or not. `close`/`open` are the same: tear a container
down only after concurrent resolution has stopped. These are usage contracts, not bugs, and staying at
Beta doesn't change them.

## Revisit trigger

CPython documents a formal memory model for free-threaded builds that covers the publication ordering
this relies on — at that point the reliance becomes a spec guarantee rather than an implementation
behaviour, and Beta can graduate to Stable. Absent that, a CPython release that changes unspecified
publication-ordering behaviour and breaks modern-di's free-threaded tests would confirm the gap is real
rather than theoretical, and is itself grounds to keep the label at Beta indefinitely rather than
guessing at a graduation date.
