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
- One code object per shape, not per provider. Per provider is 20-30% faster on chains (call sites
  stay monomorphic) but costs ~70 µs of `compile()` per provider, which a suite building a
  container per test pays per test.
