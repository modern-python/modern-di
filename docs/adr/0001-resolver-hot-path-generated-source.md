# The resolve hot path is generated source, one frame per node

A `Factory` resolver is generated from a source template specialised to the factory's resolver
shape and `exec`'d with the factory's constants as its globals. Nothing on the hot path calls a
shared helper, and `test_resolve_costs_exactly_one_resolver_frame_per_node` enforces it. Every
all-Python single-copy design was measured first and lost 25-80% on a chain: folding the arity
ladder into one closure costs even for the branches not taken (closure size is paid on every call
on CPython 3.12+), and a shared `build()` or `call()` helper is a frame per node. So the
duplication the template removes cannot be removed with functions. Overrides are compiled in for
the same reason: an override change drops the compiled resolvers instead of every resolver
checking the overrides registry.

## Consequences

- The hot path is a string. `ruff`, `ty` and coverage do not see it; the shape-enumeration test
  in `tests/test_resolver_compiler.py` is the gate for a template / namespace mismatch.
- A shape is compiled once, and each factory runs on its own copy of the compiled code. The
  specialising interpreter keeps its caches on the code object, so a copy shared across a shape's
  factories makes every call site in it polymorphic, which costs 20-30% on chains. `compile()` costs
  ~70 µs, too much to pay per provider in a suite that builds a container per test, so it stays per
  shape. The per-factory copy is a `code.replace()`, about 1 µs on a factory's first compile and
  again after each override change drops the compiled resolvers.
