# ScopeNotInitializedError

**Symptom**

A resolution fails naming a provider's scope and the current container's scope, optionally with a
dependency-path breadcrumb when the failing provider was captured by a shallower one. Each
breadcrumb line may end with a pointer to where that provider was declared (module and line
number), so you can jump straight to the declaration.

**Cause**

A provider's scope is deeper than any container currently in the chain — you resolved (directly or
transitively) a provider whose scope has no matching container built yet. For example, a
`REQUEST`-scoped provider resolved straight from the `APP` container, with no `REQUEST` child ever
built.

**Fix**

Build the deeper-scoped container before resolving from it:

```python
app_container = Container(scope=Scope.APP, groups=[MyGroup], validate=True)

# Wrong: no REQUEST container exists yet
app_container.resolve(RequestScopedThing)  # raises ScopeNotInitializedError

# Right
request_container = app_container.build_child_container(scope=Scope.REQUEST)
request_container.resolve(RequestScopedThing)
```

When the breadcrumb shows a captive dependency (a shallower provider depending on this deeper one),
the real fix is usually to move the *depending* provider to the deeper scope instead — see the scope
dependency rule below, which `validate()` catches ahead of time as `InvalidScopeDependencyError`.

## See also

- [Scope chain violation](scope-chain.md) — the related, statically-detected form of this problem.
- [Scopes: the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule).
