# Decline binding an `Alias` to its source at compile time

**Decision:** an `Alias` keeps its own resolver, which looks the source up and calls the source's
resolver on every hop. It is not replaced by the source's resolver at compile time, even though
that is a measured −35% on an alias hop.

**The measurement.** In the ablation study behind [ADR-0030](0030-exec-template-resolver.md), the
alias resolver was replaced by the source's own resolver (`registry.resolver_for(source)` returned
directly from `compile_resolver`). G18 (a warm resolve through an alias to a cached source) dropped
from 242 ns to 156 ns, −35%, which is the whole cost of the hop: the alias becomes a name for the
same function object. Registry mutation already drops every compiled resolver, so a source
registered later is still picked up on the next resolve; nothing about correctness needed the
per-resolve lookup.

**Why it was declined anyway: the runtime error chain stops naming the alias.** The alias
resolver's `try`/`except` is what prepends the alias's resolution step to a scope or resolution
error passing through it. Bound at compile time there is no alias frame to prepend from, so an error
raised beneath a `Protocol`-to-implementation chain renders the implementation only. Seven tests
describe the current behaviour: the alias appearing in a resolution error chain, prepending its step
on a scope error, `validate()` and the runtime naming the same chain for one scope violation, and
an override applied to the alias itself rather than to its source.

That last consistency is recent and deliberate: [ADR-0029](0029-scope-violations-draw-the-redirect-chain.md)
made `validate()` draw the redirect chain at effective scope precisely so that the static and
runtime diagnostics agree. Binding the alias away would reintroduce the divergence one release after
it was removed, in exchange for 86 ns on a hop that the request-lifecycle scenario does not
contain. The override-on-alias case is solvable (check the alias's override before returning the
source's resolver); the breadcrumb is not, short of a per-hop frame, which is the cost being removed.

**Revisit trigger:** a design that restores the alias step at *render* time rather than at raise
time — re-deriving the redirect chain from the static graph when a chain-shaped error is rendered,
the way `validate()` already does through `terminal_chain()` — would keep the diagnostic and take
the 35%. That is a change to error rendering, not to the compiler, and would need the
`test_dependency_path` suite to pass as written. An alias-heavy real workload where the hop is
measurable end to end would also qualify. A bare re-measurement of the binding does not; the number
is recorded here.
