# Generate `Factory` resolvers from a source template; compile overrides in

**Decision:** a `Factory` resolver is generated from a source template, specialised to the
factory's *resolver shape* (arity or kwarg names, static kwargs, context kwargs, cached) and
`exec`'d with the factory's constants as the function's globals. One code object is compiled per
shape and shared by every factory of that shape. Overrides are compiled in: an overridden provider
compiles to `return value`, and any override change drops the compiled resolvers so the next
resolve recompiles. Nothing on the resolve path consults the overrides registry. `Container.resolve`
memoizes type → resolver directly. Supersedes [ADR-0017](0017-exec-hot-path-declined.md).

**The motive is readability, and 0017 measured the wrong comparison.** The closure compiler held
seven near-identical closures (an arity ladder of three plus a kwargs path for transient factories,
three more for cached ones) with the context-fold loop copied verbatim twice, and a comment on
every copy explaining why it could not be shared. 0017 compared `exec` against those closures as an
*optimisation* and found 0-4%; it did not ask what the closures cost to read. Every all-Python
single-copy design was built and measured before this one, and every one pays:

| Design | G1 transient | G3 chain depth 6 | G4 wide | Why |
|---|---|---|---|---|
| Arity ladder folded into one closure with branches | +31% | +26% | +35% | closure size: every *untaken* branch costs (bisected: +7%, +12%, +20%, +27% as branches accumulate) |
| Shared `build()` helper, call inline | +66% | +47% | +47% | one frame per node |
| Shared `build()` and `call()` helpers | +79% | +62% | +58% | two frames per node |
| Template, one code object per **provider** | −2% | −21% | −30% | monomorphic call sites; `compile()` ≈ 70 µs per provider (G8 cold +1850%) |
| **Template, one code object per shape** (this ADR) | **−5%** | **+4%** | **−13%** | cold first-resolve +55% (≈ 2 µs per provider, once per registry) |

Warm paths are at baseline or better; the frame-per-node invariant
(`test_resolve_costs_exactly_one_resolver_frame_per_node`) holds by construction, since generated
functions have no free variables at all. Unrolling every arity (no list build, no `CALL_FUNCTION_EX`)
is what pays for G4.

**Two facts the closures were hiding.** On CPython 3.14 a closure's *size* costs on every call,
not only its frames: the bisect above added branches that never executed. And code objects
shared across providers turn every call site polymorphic for the specialising interpreter; the
per-provider row is 20-30% faster on chains for that reason alone. This ADR takes the per-shape
setting because a pytest suite building a container per test would pay the per-provider
`compile()` per test; per-provider stays available as a later opt-in.

**Overrides compiled in.** The front-guard (`has_overrides`, `fetch_override`) ran at the top of
every resolver on every resolve, so that a test could swap a value under a compiled graph. The
registry already drops every compiled resolver on mutation; treating an override as a mutation
reuses that path and removes the guard from all five resolver kinds. Measured against the template
with the guard: G1 −7%, G3 −6%, G16 −5%, and G12 (a chain resolved while an unrelated override is
active) −32%, which is the path every test using `override()` takes. All override behaviours
(handles, nesting, prior restore, propagation through an alias, scope bypass) pass unchanged. A
reset that changes nothing drops nothing, so `close()` on a root does not churn the memo.

**Shipped together, against `main` on the same machine** (CPython 3.14, medians): G1 transient −10%,
G2 cached −11%, G3 chain −3%, G4 wide −19%, G5 cross-scope −7%, G9 context −16%, G12 override-active
−30%, G16/G17 by-type −23%, G18 alias −12%, G7 request lifecycle −6%; G8 cold first-resolve +12%,
G8b cold cached +1%, child build unchanged.

**Accepted costs**, disclosed:

- The hot path is a string: no `ruff`, no `ty`, no syntax highlighting, whitespace by hand. The
  template is complete functions (`resolve`, and `build`/`create` for the cached form), never
  fragments, so it reads as the resolver one would write. The template and its namespace are
  coupled by name; `test_every_resolver_shape_compiles_and_resolves` enumerates every shape so a
  mismatch is a test failure, not a `NameError` in a user's application.
- Coverage cannot see generated lines. The behavioural suite covers them; the 100% line gate now
  measures the generator, not the resolver.
- `exec` (`S102`) appears once. Kwarg names enter the source only as `repr` string keys in a dict
  literal, never as identifiers; `test_kwarg_names_that_are_not_identifiers_are_quoted_into_the_source`
  pins it with a key containing a quote and a hyphen.
- Tracebacks: generated source is registered in `linecache` per shape, so a creator's exception shows
  the resolver's line. `__qualname__` is `resolve[<display name>]` for profilers.
- Cold first-resolve is ≈ 2 µs per provider slower (G8 +55%); the shape cache is bounded by the
  number of distinct shapes, at worst one per provider.
- An override change recompiles lazily: ≈ 2-5 µs per provider actually resolved afterwards. Overriding
  is a test-time operation and is not coordinated with concurrent resolves on other threads, which
  the `Container.override` docstring now says.
- 0017's free-threading concern (generated-module globals instead of closure cells) does not
  apply as stated: each resolver's namespace dict is written once by `exec` and read-only after,
  the same immutability cells had. `tests/test_free_threading.py` passes; a free-threaded build has
  not been run.

**Revisit trigger:** a measured cold-start or per-test regression attributable to `compile()`,
which is the per-provider code-object question above; or a CPython release where the per-shape and
per-provider rows converge, at which point the shape cache is complexity without a payoff.
