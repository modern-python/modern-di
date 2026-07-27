# Container reference cycles — every container is garbage the refcounter cannot free

Sweep date: 2026-07-27. Subject: `modern_di/container.py`. Found while investigating why
modern-di's C4 cell was the least stable measurement on the comparative benchmark page
(within-run IQR ~51% against every rival's ≤6.6%), during the
[benchmark fidelity work](2026-07-27-benchmark-fidelity-audit-report.md).

All measurements below were taken on the audit machine (Apple M4, macOS 26.5, CPython 3.14.6)
against `modern-di` at branch `bench-measurement-fidelity`.

**Finding.** `Container.__init__` stores the container inside its own `_scope_map`, so every
`Container` is a reference cycle. No container — root or child — can ever be freed by
reference counting; each one waits for a generational GC pass. A request-scoped application
therefore produces cyclic garbage at exactly its request rate.

**It appears to be removable at no cost.** `find_container` never reads the self-entry, so
dropping it does not touch the resolution hot path (verified below).

---

## The cycle

`modern_di/container.py:121-123`:

```python
self._scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
    {**parent_container._scope_map, scope: self} if parent_container else {scope: self}
)
```

`scope: self` makes `container._scope_map[container.scope] is container`. The container
references the dict; the dict references the container. Reference counting cannot break that,
so `Container` instances are only ever reclaimed by the cycle collector.

Measured — objects that survive `del` under `gc.disable()` and are then reclaimed by an
explicit `gc.collect()`:

| closed REQUEST children | objects reclaimable only by GC |
|---|---|
| 1 | 8 |
| 100 | 792 |
| 1000 | 7992 |

Eight objects per container, including the container itself. `Container` defines `__slots__`
without `__weakref__`, so this cannot be observed with `weakref` — the count above is measured
via `gc.collect()`'s return value instead.

## What it costs at runtime

The cycle does not leak — the collector reclaims it — but it moves every container's
reclamation onto the GC's schedule, which converts a steady per-request cost into a periodic
pause. On the C4 benchmark (100 request cycles per timed batch, each building and closing a
REQUEST child):

| | median | within-run IQR | max |
|---|---|---|---|
| GC enabled | 190.9 µs | **51.4%** | 318.1 µs |
| `gc.disable()` | 193.5 µs | **3.5%** | 256.5 µs |

The median is unchanged (it moves ~1%, in the *wrong* direction, i.e. noise). What collapses
is the dispersion: 51.4% → 3.5%. The tail is entirely GC, and it is the reason modern-di's C4
cell is an order of magnitude less stable than any rival's on the published page.

This also explains a discrepancy the benchmark work surfaced independently. On C4 the true
amortized per-request cost — total wall clock ÷ 60 000 requests — is **2.33 µs**, but a median
of single batch measurements reads **1.86 µs**, understating the real cost by ~20%, because the
median steps over the GC tail that a long-running process must actually pay.

## The fix appears to be free

`find_container` (`modern_di/container.py:160-168`) short-circuits on its own scope *before*
consulting the map:

```python
def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
    if scope == self.scope:
        return self
    target = self._scope_map.get(scope)
```

So the `scope: self` entry is **never read** on the resolution path. The only other consumer is
the `scope_map` property (`:170-178`), which is already deprecated and warns on access.

Building the map from the parent instead of from self removes the cycle:

```python
self._scope_map = {**parent_container._scope_map, parent_container.scope: parent_container} if parent_container else {}
```

A child then holds `{APP: root}` rather than `{APP: root, REQUEST: self}`. Every container still
reaches every ancestor; no container reaches itself; the graph becomes acyclic, so refcounting
frees children the moment they go out of scope.

Prototyped on this branch and reverted:

- cross-scope resolution (`REQUEST` provider depending on an `APP` provider) still resolves;
- 1000 closed children leave **0** objects for the collector, down from 7992;
- 448 of 449 tests pass unchanged.

The one failure is `tests/test_container.py::test_private_lock_and_scope_map_back_the_machinery`,
which asserts the current map contents including the self-entry. It encodes the behaviour being
changed and would be updated as part of the fix, not worked around.

## Why this is worth doing beyond the benchmark

The benchmark is how it was found, not why it matters. A container per request means cyclic
garbage per request, in every application using REQUEST scope — which is the framework's
primary use case and what every integration does. The cost is invisible in a median and shows
up as latency variance, which is what a production service actually feels.

## Scope note

This is a library change, deliberately not made on the benchmark-fidelity branch that surfaced
it: it touches core container construction, changes the contents of a (deprecated) public
property, and needs its own failing-test-first cycle. Specced in
[`changes/2026-07-27.03-container-reference-cycles.md`](../changes/2026-07-27.03-container-reference-cycles.md).
