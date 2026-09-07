# `modern-di-fastmcp` spells `FromDI` as a parameter default, not `Annotated`

**Decision:** in `modern-di-fastmcp`, `FromDI` is used as a parameter default,
`service: UserService = FromDI(Dependencies.user_service)`, with a `# noqa: B008` exemption at each
call site. The `typing.Annotated[T, FromDI(...)]` form that
[writing an integration](../integrations/writing-integrations.md) mandates does not work against
this host and is not offered. The exemption is scoped to this one integration.

FastMCP has a native injection seam, so by the rule in that guide `FromDI` returns the framework's
own marker (`fastmcp.dependencies.Depends`) rather than an inert `Marker` resolved by a decorator.
That marker is only detected as a default: `uncalled_for.introspection.get_dependency_parameters`
iterates `signature.parameters` and keeps the ones where `isinstance(parameter.default, Dependency)`.
Annotation metadata is never consulted, and there is no annotation-reading counterpart.

The failure is silent at registration and only appears at call time. Verified on both `fastmcp`
3.4.6 and 4.0.3, with one tool per form on the same server:

| Form | Generated schema | Call |
|---|---|---|
| `svc: str = Depends(...)` | `['name']` | succeeds, dependency resolved |
| `svc: Annotated[str, Depends(...)]` | `['name', 'svc']` | `ToolError`, missing required argument |

So the `Annotated` form does not merely fail to inject. It leaks the parameter into the tool schema,
advertises it to the model, and then rejects the call the model makes.

Rejected, with the reasoning that would otherwise be re-litigated:

- **Keep `Annotated` and strip the parameter with a decorator**, as the integrations for hosts
  without native DI do. It would mean duplicating resolution that FastMCP already performs and
  rewriting a signature FastMCP is itself introspecting, to reach a result the native marker gives
  directly. The decorator path exists for hosts with no seam; this host has one.
- **Offer both spellings.** One dependency would have two forms, and the one matching the family's
  house style would be the broken one. A form that produces a schema the model cannot satisfy is
  worse than a form that does not exist.
- **Wait for FastMCP to detect markers in `Annotated` metadata.** Not ours to schedule, and the
  default-value spelling is the one FastMCP documents.

The accepted cost is that one integration in the family reads differently from the other thirteen,
and that its docs page and `examples/app.py` carry `# noqa: B008`. The guide's mandate exists to
avoid `B008`, not for its own sake, and the lint rule targets shared mutable defaults, which a
resolution marker is not.

**Revisit trigger:** FastMCP's introspection reads `Annotated` metadata as well as defaults. At that
point the family form applies, the exemption is removed, and this integration stops being the
exception.
