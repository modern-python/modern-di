# Eager child-container allocation

**Decision:** `Container.__init__` keeps eagerly building the per-child lock, `CacheRegistry` and
`ContextRegistry`; none is lazily allocated.

**Why:** measured, lazy allocation saves about 0.4% on a realistic caching request cycle (a
caching child uses its lock, so laziness only defers the allocation and adds a `None` check on the
hot path) and at most 3.5% on a child that caches nothing. A lazily created lock must itself be
created atomically, which reintroduces the creation race the lock exists to prevent. The
registries save even less because realistic children use them. If the allocations ever dominate a
real request profile, the design to measure is one lock per tree, not laziness.
