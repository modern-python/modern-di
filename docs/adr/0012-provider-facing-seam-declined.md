# No provider-facing seam on `Container`

**Decision:** no `ResolutionContext` view handed to providers, and no promotion of `Container`'s
provider-facing members into a declared interface. Resolution runs against the `Container` directly
and the existing `# noqa: SLF001` reaches stay.

The deciding evidence: **there is exactly one `Container` implementation.** Everything that resolves
does so against the same collaborator, so a `ResolutionContext` would be one interface with one
implementation — a hypothetical seam under the standing one-adapter/two-adapter rule, the same
reasoning that declined [the grpc introspection seam](0010-grpc-registry-introspection-declined.md).

The crossings it would formalize have since gone to zero. At decision time there were three
(`Factory._lock`, plus `_warn_and_reopen_if_closed` on `Factory` and `ContextProvider`); the
single-path compiled resolver dissolved `Factory.resolve` and `Alias.resolve`, moving the lock and
closed-state reaches into `resolver_compiler.py` — the compiler's business, ruled on in
[the per-provider compile seam](0014-per-provider-compile-seam-declined.md). The last one,
`ContextProvider.fetch_context_value` calling `container._prepare()`, has had no production caller
since #425. Option (a) would also have changed `AbstractProvider.resolve(container)` — then the
documented public extension contract — to `resolve(ctx)`: a large blast radius to formalize a
boundary only core code crosses, where `docs/providers/advanced-api.md` already declares which
members are supported (`find_container`) and which are internal (`_lock`, `_scope_map`,
`parent_container`).

**Revisit trigger:** a **second `Container` implementation** appears, making `ResolutionContext` a
real two-adapter seam. The original second limb — a custom-provider author blocked on "do not build
on" internals — is retired: [the provider set is closed](0013-custom-providers-retracted.md), so
that author does not exist. If the set reopens, the migration path is the polymorphic `compile()`
hook, not a provider-facing view of `Container`.
