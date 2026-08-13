---
summary: An override value bypasses the scope check, cache lookup and creator, so it need not be an instance of the declared type and a REQUEST-scoped provider can be overridden and resolved from an APP container.
---

# An override value is not type-checked or scope-checked

**Decision:** `container.override(provider, obj)` does not require `obj` to be an instance of the
provider's declared type, and does not require the resolving container to satisfy the provider's
declared scope. Both checks are structurally bypassed by where the override short-circuit sits in
`resolve_provider`, and neither is going to be added.

## Context

`resolve_provider` checks the override registry *before* delegating to the provider at all. If an
override is present, its value is returned directly — bypassing the scope check, the cache lookup, and
the creator invocation entirely. This is what makes overrides fast and simple to reason about
mechanically, but it also means none of the machinery that would normally validate a resolved value
ever runs on an override.

Two concrete consequences fall out of that positioning:

- **No type check.** The override object does not need to be an instance of the provider's declared
  type at runtime — Python does not enforce it, and modern-di adds no check of its own. A caller who
  passes an incompatible object gets no error at override time and no error at resolve time; they get
  exactly the wrong object back, silently.
- **No scope check.** An overridden provider is resolved from whichever container `resolve_provider`
  is called on — the original provider's declared scope is irrelevant, because the short-circuit fires
  before `find_container` ever runs. In practice, a REQUEST-scoped provider can be overridden and
  resolved from an APP-scoped container without raising `ScopeNotInitializedError`.

Overrides also don't interact with the cache: if a singleton was already resolved before
`container.override(...)` was called, subsequent `resolve_provider` calls return the override value,
not the cached instance, and after `reset_override` the original cache entry (if any) is still present
and returned again. That's a related but separate behaviour from the two checks above — it follows
from the same "override fires first" positioning but isn't itself a missing check.

## Decision & rationale

**The scope bypass is a feature, not an oversight — it's often exactly what tests want.** A test that
overrides a REQUEST-scoped database provider with a stub, then resolves it from the APP-scoped root
container without building a child container down to REQUEST first, is a common and legitimate
pattern. Requiring the caller to build the full scope chain just to install a stub defeats much of the
point of having overrides at all. This is also why the mechanism lives ahead of the scope check
structurally, not behind it: putting it behind would mean paying the scope-chain-walk cost that
overrides exist partly to let callers skip.

**The type bypass is an accepted cost of the same positioning, not a separately chosen feature.**
Adding a runtime `isinstance` check would mean either checking it against `bound_type` (which doesn't
handle generics, protocols, or duck-typed test doubles — the exact things overrides are commonly used
for) or against nothing meaningful. A check narrow enough to be correct would reject legitimate test
doubles; a check loose enough to accept them would catch almost nothing. So the responsibility is left
with the caller: "callers should pass a compatible object for type safety" is a documented expectation,
not an enforced one.

**Consequence worth naming together:** these two bypasses compound. An override can supply an object
of the wrong type *and* be resolved from a container that could never have satisfied the original
provider's scope, and nothing in the resolve path will catch either. That's the accepted shape of the
mechanism, not a partially-fixed bug.

## Revisit trigger

A real report of a production bug caused by an override silently returning a type-incompatible object
— as opposed to a test-time convenience use, which is the mechanism working as designed. At that point
the design question is narrower than "add type checking to overrides" — it's whether an *opt-in*
strict-override mode is worth the API surface, given that the common case (test doubles, protocols)
is exactly what a blanket check would break.
