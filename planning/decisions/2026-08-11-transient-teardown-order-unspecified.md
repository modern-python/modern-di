---
summary: The order in which a resolver collects transient (uncached) dependencies is not part of the contract, even though the arity ladder happens to preserve it today.
---

# Transient teardown order is unspecified

**Decision:** The order in which transient dependencies are collected during resolution is not
part of modern-di's contract. A future change to the resolver's shape may alter it without that
being a breaking change.

## Context

An uncached (transient) dependency that its consumer's creator uses and drops — never retains — is
freed by CPython's ordinary refcounting the moment the resolver's local reference to it goes out of
scope. modern-di manages no finalizer for such an object: `CacheSettings(finalizer=)` only applies to
cached providers, and `close_sync`/`close_async` only tear down what a container owns. So the *only*
place this order is observable at all is the drop order of objects a creator never kept a reference
to — and that order falls out of however the resolver's compiled closure happens to hold its locals,
not from any stated rule.

The question came up concretely when the positional fast-path's arity ladder landed: arity 0 and 1
compile to a closure that names its argument and calls the creator directly; arity 2+ still builds a
list and star-calls it. Naming vs. list-building are different mechanisms for holding intermediate
values, so it was worth checking whether they drop objects in a different order.

## Decision & rationale

**Nothing observable changed when the arity ladder landed, and the reason generalizes.** The ladder
caps at arity 1, so it never holds more than one named local at a time — there is no order to alter
between one item and itself. Measured directly, main vs. ladder, on CPython 3.10 and 3.14, across
arities 1 through 3: the collection order is identical in every case tested.

The rule is stated in advance of the case that would actually test it. A rung added at arity 2+ would
release named locals with the frame teardown rather than through the star-call's intermediate list —
and on CPython below 3.12, frame-local release order and list-teardown order are not the same thing.
Such a rung would be a legitimate performance change, not a breaking one, because the order was never
promised. Declaring the contract now means that future work doesn't have to treat "does this change
teardown order" as a correctness question — only a "did anyone tell users this order was reliable"
question, and the answer is no.

**Accepted cost:** a user who has silently relied on today's incidental order (for example, using
transient side effects on drop as a poor man's ordering signal) gets no deprecation warning if a
future resolver shape changes it. This is deliberate — retaining that order would pin the resolver's
internal representation of arity 2+ closures indefinitely, for a guarantee nobody asked for and the
library never advertised.

## Revisit trigger

A rung is added to the arity ladder at arity 2 or higher (or the star-call path is otherwise
restructured) and CPython's frame-local teardown order diverges from list-teardown order on a
supported version. At that point, re-measure whether the divergence is observable by any real
finalizer-adjacent use case before deciding whether it's worth stabilizing rather than continuing to
disclaim it.
