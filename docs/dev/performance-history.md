# Performance history

How modern-di's resolve and request paths reached the numbers on [Performance](../introduction/performance.md),
in release order. Unless a paragraph says otherwise, a percentage is a guard-tier figure from the
change that made it, measured against the commit before it. The guard tier's scenarios (G1-G18) and
the comparative tier's (C1-C6) are listed in
[`benchmarks/README.md`](https://github.com/modern-python/modern-di/blob/main/benchmarks/README.md).

## 2.29 to 3.4: one compiled closure per provider

From 2.29.0 through 3.4.0, modern-di compiled one specialized closure per provider on first
resolve and memoized it on the providers registry. That replaced a generic resolver interpreted on
every call. Each closure hoisted its scope navigation, override check and cache lookup out of the
per-call path and called its dependencies' resolvers directly.

3.1.0 removed a frame from the top of every resolve. `resolve_provider` opens with an inline
`closed` check instead of an unconditional method call, and `build_child_container` has no such
check at all. On the guard suite against 3.0.0 that was worth roughly 5-11% on C1- and C2-shaped
resolves and on child construction. The deeper scenarios already had the check inline in their
compiled resolvers and did not move.

3.1.1 fixed a reference cycle. Every `Container` stored itself in its own ancestor map, so
reference counting could never free one, and a request-scoped application handed the garbage
collector work at its request rate. Seeding the map from the parent removed the cycle. The C1-C3
cells did not move. C4's median fell from 232.7 µs to 194.8 µs per 100-request batch, and its
standard deviation from 123.0 µs to 7.9 µs: the tail C4 used to carry was the collector reclaiming
containers.

3.1.2 removed two frames from the warm-hit path. A cached resolve reached its compiled resolver and
its cache item through two internal lookup methods, each opening with a dict lookup that hits and
returns. Both lookups are now inlined at the call site, and the method runs only on a miss, where it
still owns the cycle guard, the memo write and the `setdefault` that makes concurrent first
resolvers share one `CacheItem`. That is worth about 42 ns on a warm hit. The first lookup sits in
`resolve_provider`, so every top-level resolve gets it, cached or not.

3.2.0 trimmed three paths:

- The cached resolver's cold-miss thunk is built with `functools.partial` instead of a lambda over
  the target container. The closure had promoted that variable to a cell for the whole resolver, so
  `MAKE_CELL` ran on every call, including a warm hit (−11.3% on a warm hit).
- The context-kwarg path checks `has_overrides` before its override lookup (−6.0%). Every framework
  integration takes this path for its per-request values.
- An `Alias` inlines its source lookup and calls the source's compiled resolver directly: one Python
  frame per hop instead of four (~322 to ~252 ns). No comparative scenario covers aliases.

3.3.0 made the call itself cheaper. `resolve_positional` built its arguments with a list
comprehension and star-called the creator, although the dependency count is fixed once a resolver
compiles. A factory with 0 or 1 provider dependencies now compiles to a closure that names its
argument and calls the creator directly, with no list, no `CALL_FUNCTION_EX` and, below 3.12, no
comprehension frame. The ladder stops at 1 because that is where the measured win was: leaves have
arity 0 and chain nodes arity 1. Rungs beyond it were built, measured and dropped.
`Container.resolve` also stopped delegating to `resolve_provider` and carries that body itself,
which cut the by-type surcharge from 54-65 ns to 21/17/23 ns on C1/C2/C3. A context-backed
parameter had its binding folded into the compiled closure. Together these were worth −27 to −34%
across C1, C3 and the whole by-type column, against rivals whose absolute times did not move
between the two publications.

## 3.5: generated source

[#470](https://github.com/modern-python/modern-di/issues/470), in 3.5.0, replaced the closures with
a source template. The closure compiler had grown seven near-identical closures, each with a comment
on why it could not share code with the others. A `Factory` resolver is now generated from a
template specialised to its resolver shape and `exec`'d with the factory's constants as globals,
one code object per shape. Every arity is unrolled, so a wide node no longer builds a list and
star-calls its creator. The same change compiled overrides in, so no resolver checks the overrides
registry on the hot path, and gave `Container.resolve` a direct type → resolver memo. The by-type
and by-reference cells have differed by 3-4 ns since.

Every all-Python single-copy design was measured on the guard tier first:

| Design | G1 transient | G3 chain (6) | G4 wide (10) |
|---|---|---|---|
| Arity ladder folded into one closure with branches | +31% | +26% | +35% |
| Shared `build()` helper | +66% | +47% | +47% |
| Shared `build()` and `call()` helpers | +79% | +62% | +58% |
| Template, one code object per provider | −2% | −21% | −30% |
| Template, one code object per shape (shipped) | −5% | +4% | −13% |

The folded ladder lost about a quarter even though each call takes only one branch: on CPython
3.12+ a closure's size costs on every call. The per-provider template is faster because a code
object shared across providers makes its call sites polymorphic for the specialising interpreter.
Per shape shipped anyway, because `compile()` costs about 70 µs per provider, and a test suite that
builds a container per test would pay that in every test.
[ADR 0001](https://github.com/modern-python/modern-di/blob/main/docs/adr/0001-resolver-hot-path-generated-source.md)
records the decision.

## After 3.5: the request path

Three smaller changes moved the per-request path:

- [#540](https://github.com/modern-python/modern-di/issues/540) inlined the cross-scope hop. The
  generated resolver reads the container's ancestor map itself instead of calling
  `find_container`, so a REQUEST resolve that needs an APP dependency spends no extra frame on the
  hop (−15 to −17% on a cross-scope resolve, −7.5 to −11% on a context resolve).
- [#541](https://github.com/modern-python/modern-di/issues/541) gave a container tree one `RLock`,
  created by the root and shared by every child, where each child had allocated its own (−14% on a
  child build, −3.5% on a request cycle).
- [#542](https://github.com/modern-python/modern-di/issues/542) made `close_async` clear a
  finalizer-less cached item directly instead of awaiting a coroutine that only did that (−8% on a
  request cycle closing ten such items).

In the 3.x publication at `630de77`, C6 fell 10% and C4 5%, the sum of the first two. The third has
no comparative scenario.

## 4.0

[#557](https://github.com/modern-python/modern-di/issues/557) made a context value an ordinary
dependency. A `ContextProvider` compiles to its own resolver, and a factory that depends on one
takes the same generated path as any other factory. The per-resolve loop that looked up each context
value is gone (−28% on a context resolve, G9).

[#559](https://github.com/modern-python/modern-di/issues/559) compiles an `Alias` to its source's
resolver, so a hop through an alias runs no frame of its own (−33% on an alias hop, G18, which now
matches a plain cached resolve). An error that crosses an alias still shows the alias in its chain:
the parent puts the hop back when it adds its own step.

[#585](https://github.com/modern-python/modern-di/issues/585) made the request cycle and the cold
path cheaper. A child container builds its registries without a keyword-only dataclass constructor,
compiled resolver code is memoized by shape, the `ContextProvider` resolver reads context values
directly, and closing a container that created nothing skips the cache teardown. That is −15.6% on
a child build (G6, 716 to 605 ns), −13.4% on a cold first resolve (G8, 24.58 to 21.29 µs), −5.9%
on a context resolve (G9) and −2.9% on a batch of request cycles (G7).
[#593](https://github.com/modern-python/modern-di/issues/593) rebuilt the resolver templates from
shared fragments and left the generated source byte-identical.

[#596](https://github.com/modern-python/modern-di/issues/596) matches scopes by enum member instead
of integer value. Every generated `Factory` resolver checks its scope first, and the check went from
`==` to `is`: a same-scope cached resolve got about 5 ns faster and a cross-scope one about 5 ns
slower. Between the 3.x publication and 4.0 before #605, modern-di's C1-C3 cells fell 3-4%
(11 ns on C1, 5 ns on C2, 29 ns on C3) while the rivals' stayed within about 2%. #596 fits that
size, though no guard run isolated it.

[#561](https://github.com/modern-python/modern-di/issues/561) removed `Container(use_lock=)`, so
every container locks a cache miss. A cache hit never reaches the lock, and an uncontended acquire
costs about 54 ns, about 0.2% of a cold first resolve.
[#597](https://github.com/modern-python/modern-di/issues/597) then replaced the tree lock from #541
with one lock per cache item, so creating one cached factory no longer waits for another, and a miss
builds the factory's dependencies under that lock. A child build still allocates no lock. The cost
moved to the first resolve of a cached factory in each container: about 120 ns to allocate its lock,
+7.7% on G7b (one request cycle with a sync close) and +4.6% on G7.

[#605](https://github.com/modern-python/modern-di/issues/605) was a series of small changes to the
request cycle and the cold path:

- A container holds its cache items, creation order and context in its own slots instead of in two
  registry objects, so a child build allocates two fewer objects.
- The child's ancestor map is copied instead of rebuilt by unpacking, a plain dict context is copied
  with `dict.copy`, and an auto-scoped child skips scope checks it cannot fail.
- On close, a finalizer that returns `None` skips `inspect.isawaitable`, the async close loop calls
  finalizers itself instead of awaiting a coroutine per item, and a cache miss passes its target
  container instead of building a `functools.partial`.
- On the cold path, a factory decides its positional-call names once, each resolver's globals start
  from a copied dict, `validate()` dispatches events on their exact type, and building a `Factory`
  reads a plain class's signature from its `__init__` without `typing.get_origin`.

Against the commit before the series: −31% on a child build (G6), −37% with an automatic scope
(G6b), −24% on G7b, −17% on G7, −27% on ten sync finalizers (G13), −12% on a cold first resolve
(G8), −9 to −11% on `validate()` (G10, G11) and about −23% on building a `Factory`. A child
container takes 504 bytes instead of 584. Warm resolves (G1-G4) moved less than 2% either way.

## Comparative cells across publications

C4 and C6 are the per-request scenarios, and 4.0 moved both. C6 builds a REQUEST child seeded with a
context value, resolves a handler that needs that value and an APP dependency, and closes the child.
It benefits from #557, #585 and #605, and pays for #596's cross-scope check. C4 builds a child,
first-resolves one request-scoped cached factory with an async finalizer and closes the child, so it
benefits from #585 and #605 and pays for #597's lock allocation.

| | 3.x (`630de77`) | 4.0 before #605 (`f300c2e`) | 4.0.0 |
|---|---|---|---|
| C1 / C2 / C3 by reference, modern-di | 253 / 151 / 789 ns | 242 / 146 / 760 ns | 242 / 143 / 756 ns |
| C4 request lifecycle, modern-di | 2.29 µs | 2.28 µs | 1.85 µs |
| C4 vs that-depends / dishka / wireup | **0.18** / 1.08 / **0.14** | **0.18** / 1.12 / **0.14** | **0.15** / **0.88** / **0.12** |
| C6 context, modern-di | 1.45 µs | 1.09 µs | 806 ns |
| C6 vs dependency-injector / that-depends | **0.38** / **0.48** | **0.28** / **0.36** | **0.21** / **0.27** |
| C6 vs dishka / wireup | 1.15 / 1.02 | **0.88** / **0.78** | **0.65** / **0.57** |

Before #605, C6 fell 25% from 3.x, close to the guard tier's prediction: G9, C6's guard twin, fell
28% with #557 and another 5.9% with #585. That put modern-di ahead of dishka and wireup on C6. C4
did not move then, because on G7 #585 measured −2.9% and #597 +4.6%.

#605 then took C4 down 19% and C6 down 26%, and moved modern-di ahead of dishka on C4 (1.12 to
0.88). dishka's own C4 time, as the ratios imply it, stayed within about 4% across the three runs,
so the change in that ratio is modern-di's.

The two publications after 4.0.0 (`ab327b3` and `8845e6a`) measured the 4.0.0 library plus
[#631](https://github.com/modern-python/modern-di/issues/631), which adds checks at provider
definition and runs nothing during a resolve, against that-depends 4.2.0 and wireup 2.12.1. Every
ratio stayed within 0.03 of 4.0.0 except dependency-injector's C2 (2.20 to 2.13, then 2.14) and,
at `8845e6a`, dishka's C4 (0.88 to 0.84). No cell crossed 1.0. modern-di's C4 fell from 1.85 to 1.80 µs at `ab327b3` and 1.74 µs at
`8845e6a`; #631 adds nothing to that path, and neither run explains the drop.
