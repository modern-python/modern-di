# A scope violation draws the chain that reached it, at effective scope

**Decision:** `InvalidScopeDependencyError` renders the same arrow tree as every other chain-shaped
error, and each redirect hop in that tree is drawn at the scope it **resolves** at, not the scope the
provider object reports. The redirect walk moves to one module-level `terminal_chain()` in
`dependency_graph.py`; `.dep_chain` joins the public attribute surface, with `.dep_provider` and
`.dep_terminal` as its two ends.

**The blind spot was specific to redirects, and `Alias` is how abstract-to-implementation binding is
spelled.** `_walk_errors` compared `terminal_scope(dep)` against `terminal_scope(parent)`, then built
a message naming `dep.display_name` — the alias's bound type — beside a scope belonging to the
provider at the far end of the chain. Two facts about two objects, presented as one edge, with the
terminal named nowhere. A three-hop `Protocol` chain reported `provider of IA at deeper scope
REQUEST` where `IA` declares no scope at all and `Impl`, the provider to change, never appeared. The
source was not recoverable programmatically either: `.dep_provider` was the alias, and its source
type is private.

**Its sibling out of the same walk already did this right.** A cycle through the same alias drew
every hop with definition sites via `_render_chain`, because `build_cycle_error` keeps the providers
it walked. Two errors from one `validate()` call, one drawing the chain and one printing a line, is
the drift [0009](0009-error-text-is-not-a-contract.md) unified the drawers to prevent — and 0009 is
also what licenses changing this text with no deprecation cycle. The tree pays even with no alias
present: the old message carried no `module:line` for either provider.

**Effective scope, not declared scope, and not a blank.** `Alias` sets `_takes_group_scope = False`
and passes `scope=UNSET`, so `AbstractProvider.scope` returns the `Scope.APP` default for every
alias. Three renderings were compared on a three-hop chain. Drawing `provider.scope` (the shipped
behaviour, and still what the cycle renderer did) prints `APP APP APP REQUEST`, which reads as "the
aliases are fine, only the source is deep" and points at the wrong fix. Blanking the column for
providers with no scope of their own is honest but supplies nothing: the reader still scans to the
bottom. Drawing each hop at its terminal's scope puts the APP/REQUEST boundary on the offending edge,
which is the fix the reader is looking for. `Alias.scope` keeps returning `APP` — scope ordering
depends on it — so this is a rendering rule, deliberately not a change to the provider.

**The walk moved rather than being copied.** `Alias` cannot import `dependency_graph`
(`dependency_graph` → `providers.abstract` → `providers/__init__` → `alias`), so a container-aware
step on the provider would have re-hand-rolled the chain walk that
[0007](0007-unify-graph-traversal.md) deleted. `resolver_compiler` has no such cycle, so the alias
resolver builds its step through `redirect_step()` and `Alias._resolution_step` is gone. That keeps
0007 intact: the walk stays in the traversal module and providers still expose only the generic
`redirect_target` hook. Cost is off the hot path — the step is built inside `except`, and the
compiled closure binds nothing new.

**`RegistrationError` stays the base**, though nothing registers when this fires and the error is
aggregated into a `ContainerError`. Under 0009 the hierarchy *is* the contract: reparenting would
silently break a caller catching `RegistrationError`, to fix a misfiling that costs nobody anything.

Pinned by `test_validate_and_runtime_name_the_same_chain_for_one_scope_violation` (the two detectors
must agree, which is the defect stated as a property),
`test_alias_scope_violation_names_the_source_behind_the_alias` (the terminal is recoverable without
parsing the message) and `test_invalid_scope_dependency_error_draws_the_chain_that_reached_the_terminal`
(the alias hop draws REQUEST while its own `.scope` is APP).

**Revisit trigger:** a second provider type implements `redirect_target`. Effective-scope rendering
assumes a redirect is a pure forward with no lifetime of its own, which is true of `Alias` and was
never true of anything else; a redirect that *does* own a scope would make the terminal's scope the
wrong thing to draw, and the column would need the hop's own band back.
