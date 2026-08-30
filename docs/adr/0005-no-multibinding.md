# No multibinding or collection injection

**Decision:** `modern-di` does not support registering several providers for one type and injecting
them together as a collection. There is no `multi=True`, no `list[T]` fan-in, no binder-set API.
Field precedent is broad (MEDI's `IEnumerable<T>`, Spring's `List<T>`, `injector`'s multibind,
Angular's `multi: true`), and the usual motivation is plugin-style extension.

The registry is a **type → provider map**. Multibinding turns it into type → *collection of*
providers, which changes every operation built on it:

- Registration stops being "this type is now wired" and becomes "this type has one more
  contributor", so `DuplicateProviderTypeError` has to become conditional on an opt-in flag.
- Resolution by type stops having one answer: `resolve(T)` and `resolve(list[T])` would resolve
  different things from one registration, and the wiring plan would need a third parameter category.
- Overrides get ambiguous — overriding `T` either replaces the collection or one contributor, and
  both readings are defensible.
- Validation loses the property that a missing type is unambiguous: an empty collection is
  indistinguishable from a wiring mistake.

That is permanent, structural registry cost for demand inferred from other ecosystems rather than
observed in this one. The workaround costs a user one provider: a `Factory` that takes the
individual dependencies and returns the list.

**Revisit trigger:** concrete user demand — a real plugin-style use case the one-Factory workaround
does not serve. Field precedent alone is not the trigger; it is what was already weighed here. If
reopened, the registry-semantics consequences above are the design problem, not the API spelling.
