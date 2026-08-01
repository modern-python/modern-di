---
summary: Arity-specialised creator calls measure ~-30% on transient chains (~45 ns/node) with call semantics verified identical across 3.10-3.14, but shipping needs a ruling on transient-dependency finalization order (reversed below 3.12) and an arity-aware frame-budget constant.
---

# Arity-specialise the positional creator call

`resolve_positional` builds its arguments with a comprehension and star-calls the
creator (`args = [r(target) for r in pos]`, then `creator(*args)`), even though
`len(pos)` is fixed the moment the resolver is compiled. Specialising on arity —
`creator()` for 0 deps, `a0 = r0(target); creator(a0)` for 1, and so on up to a
small cap — removes the list build and the `CALL_FUNCTION_EX` unpack.

## Why it is open

This is the largest measured single win found on the resolve path, and it applies
to essentially every node. In-process interleaved A/B (CPython 3.14.6, Apple M4,
medians of 9x500k, real containers, candidate closures injected into
`providers_registry._resolvers`): 0 deps 122.2 → 93.0 ns, and a depth-6 transient
chain 794 → 571 ns (**~-30%**, ~45 ns per node).

The semantics survived unusually hard probing: 56 callable kinds x 5
interpreters, 19 scenarios, with byte-identical error messages and breadcrumb
chains. Nothing about argument binding broke.

It was killed on two things it never claimed, both found by adversarial review:

- **Finalization order changes below 3.12.** The star-call's intermediate list
  owns the arguments, and `list_dealloc` frees them back-to-front. Removing the
  list changes the order in which transient dependencies with no finalizer hook
  are collected — reversed on 3.10/3.11/3.12, unchanged on 3.14. That is a
  cross-version behavioural divergence introduced by a performance change, and it
  is a maintainer call, not an implementation detail.
- **It breaks the frame-budget test as written.** Per-node Python calls drop from
  3 to 2 below 3.12, which red-fails
  `tests/test_resolver_compiler.py::test_resolve_costs_exactly_one_resolver_frame_per_node`
  and falsifies the PEP 709 paragraph in
  [`architecture/performance.md`](../../architecture/performance.md). The test is
  right and the candidate is right; the constant simply has to become
  arity-aware.

Two lesser notes for whoever picks it up: the cited cached-factory half is off
the warm path and was never measured, and one binding site becomes five, of which
four are untested by the single existing ordering test.

## Revisit trigger

A maintainer ruling on transient-dependency finalization order — either accepting
the below-3.12 reversal as immaterial, or CPython unifying frame-teardown order
across supported versions — **or** the transient-chain benchmark becoming the
binding constraint on a real workload. Any attempt must land with an arity-aware
`_CALLS_PER_NODE`, an arity-parameterised binding-order test, and a cap of
3-4 deps.
