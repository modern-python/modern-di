# ScopeSkippedError

**Symptom**

A resolution fails naming a provider's scope and the current container's scope, optionally with a
dependency-path breadcrumb — the requested scope is shallower than the current container, but no
container at that scope exists anywhere in this chain. Each breadcrumb line may end with a pointer
to where that provider was declared (module and line number), so you can jump straight to the
declaration.

**Cause**

The container chain skipped an intermediate scope when it was built. For example, a chain built
`APP → ACTION` (skipping `SESSION` and `REQUEST` entirely) has no `REQUEST` container to satisfy a
`REQUEST`-scoped provider, even though `REQUEST` is shallower than the current `ACTION` container.

**Fix**

Build child containers through every intermediate scope your providers need, rather than jumping
straight to a deep one:

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup], validate=True)

# Wrong: jumps straight past REQUEST
action_container = app_container.build_child_container(scope=Scope.ACTION)
action_container.resolve(RequestScopedThing)  # raises ScopeSkippedError

# Right: build through REQUEST first
request_container = app_container.build_child_container(scope=Scope.REQUEST)
action_container = request_container.build_child_container(scope=Scope.ACTION)
action_container.resolve(RequestScopedThing)
```

If a framework integration builds the chain for you, check which scopes it actually instantiates per
request/message and align your providers to those, not to the full built-in hierarchy.

## See also

- [Scope chain violation](scope-chain.md) — the related, statically-detected form of this problem.
- [Scopes](../providers/scopes.md) — how container chains map to the scope hierarchy.
