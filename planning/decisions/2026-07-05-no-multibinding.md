---
summary: No multibinding / collection injection — resolving `list[T]` to every provider registered for `T` contradicts the type→provider map the registry is built on; revisit only on concrete user demand, not on field precedent.
---

# No multibinding or collection injection

**Decision:** `modern-di` does not support registering several providers for one
type and injecting them together as a collection. There is no `multi=True`, no
`list[T]` fan-in, no binder-set API.

## Context

Multibinding is common in the wider field and users arriving from those
ecosystems expect it:

- MEDI resolves `IEnumerable<T>` to every registration for `T`
- Spring injects `List<T>` / `Map<String, T>`
- `injector` exposes an explicit multibind API
- Angular uses `{ provide: TOKEN, useValue: x, multi: true }`

The usual motivation is plugin-style extension: several handlers, validators, or
middleware registered independently and consumed as a set.

## Decision & rationale

The registry is a **type → provider map**. Multibinding requires that map to
become type → *collection of* providers, which changes the meaning of every
operation built on it:

- Registration stops being "this type is now wired" and becomes "this type has
  one more contributor", so `DuplicateProviderTypeError` — a deliberate
  declaration-time guard — has to become conditional on an opt-in flag.
- Resolution by type stops having one answer. `resolve(T)` and `resolve(list[T])`
  would resolve different things from the same registration, and the wiring plan
  would need a third parameter category alongside provider-resolved and context
  kwargs.
- Overrides get ambiguous: overriding `T` in a test either replaces the whole
  collection or one contributor, and both readings are defensible.
- Validation loses a property it currently relies on — that a missing type is
  unambiguous. An empty collection is indistinguishable from a wiring mistake.

That is new registry semantics for a feature nobody has asked for here. It sits
outside the conservative feature set for the same reason the other borrowed
subsystems do: the cost is permanent and structural, the demand is inferred from
other ecosystems rather than observed in this one.

The workaround costs a user one provider: declare a `Factory` that takes the
individual dependencies and returns the list. That is explicit, traceable to a
declaration site, and needs nothing from the framework.

## Revisit trigger

Concrete user demand — an actual request describing a real plugin-style use case
that the one-Factory workaround does not serve. Field precedent alone is not the
trigger; that is what was already weighed here. If it is ever reopened, the
registry-semantics consequences above are the design problem to solve first, not
the API spelling.
