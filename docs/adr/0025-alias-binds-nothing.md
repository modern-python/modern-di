# An alias keeps its own resolver; it is not bound to its source at compile time

**Decision:** the alias resolver looks its source up and calls the source's resolver on every hop.
It is not replaced by the source's resolver at compile time, although that measured −35% on an
alias hop (G18 242 → 156 ns, whole cost of the hop).

**Why:** the alias resolver's `try` / `except` is what prepends the alias's step to a scope or
resolution error passing through it. Bound away, an error under a `Protocol`-to-implementation
chain would name only the implementation, and `validate()` and the runtime would stop drawing the
same chain, which [ADR-0029](0029-scope-violations-draw-the-redirect-chain.md) made them do. The
older objections no longer apply: registry mutation drops every compiled resolver, and since
[ADR-0030](0030-exec-template-resolver.md) every generated resolver already captures its
dependencies' resolvers by reference and an overridden alias compiles to its override before its
source is touched. Recovering the alias step at render time from the static graph, the way
`validate()` already draws it, would keep the diagnostic and take the win; that is an error-rendering
change, and the one worth making if the hop ever shows up in a real profile.
