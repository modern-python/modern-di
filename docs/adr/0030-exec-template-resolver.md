# Generate `Factory` resolvers from a source template; compile overrides in

**Decision:** a `Factory` resolver is generated from a source template specialised to the factory's
resolver shape (arity or kwarg names, static kwargs, context kwargs, cached) and `exec`'d with the
factory's constants as its globals; one code object per shape, shared by every factory of that
shape. Overrides are compiled in: an overridden provider compiles to `return value`, and an override
change drops the compiled resolvers so the next resolve recompiles. `Container.resolve` memoizes
type → resolver directly. This reverses the earlier decline of `exec` codegen, which had measured it
only as an optimisation over the closures.

**Why:** the closure compiler had grown seven near-identical closures with the context-fold loop
copied twice and a comment on every copy explaining why it could not be shared. Every all-Python
single-copy design was measured first, and every one pays:

| Design | G1 transient | G3 chain | G4 wide |
|---|---|---|---|
| Arity ladder folded into one closure with branches | +31% | +26% | +35% |
| Shared `build()` helper | +66% | +47% | +47% |
| Shared `build()` and `call()` helpers | +79% | +62% | +58% |
| Template, one code object per provider | −2% | −21% | −30% |
| **Template, one code object per shape** | −5% | +4% | −13% |

Two facts the closures hid: on CPython 3.12+ a closure's size costs on every call, not only its
frames (the folded ladder lost 26% with every extra branch untaken); and a code object shared
across providers turns its call sites polymorphic for the specialising interpreter, which is why
the per-provider row is faster. Per shape is the default because `compile()` costs ~70 µs per
provider and a pytest suite building a container per test would pay it per test; per shape costs
about 2 µs per provider on first resolve (G8 cold +12%).

Shipped together against `main` on the same machine: G1 −10%, G2 −11%, G4 −19%, G9 −16%, G12
(override active) −30%, G16/G17 by-type −23%, G18 alias −12%, G7 request lifecycle −6%.

**Accepted costs:** the hot path is a string, with no `ruff` or `ty` over it and whitespace by hand;
the templates are complete functions and every shape is enumerated by a test so a template /
namespace mismatch is a test failure. Coverage cannot see generated lines. Kwarg names enter the
source only as `repr` string keys. Generated source is registered in `linecache` and the resolvers
carry a `__qualname__`, so tracebacks and profilers read normally. Overriding drops and recompiles
lazily and is not coordinated with concurrent resolves. The free-threaded CI job (3.14t) passes.
