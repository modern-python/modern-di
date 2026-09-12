# No per-provider `compile()` seam

**Decision:** the resolver compiler keeps its central type dispatch and its per-type builders; they
do not move into a `provider.compile(registry)` method. The compiler's reads of `Factory` and
`Alias` privates stay, suppressed per file rather than per line.

**Why:** there is exactly one compiler, so nothing varies across the proposed seam and `compile()`
would be cleanliness, not a swap point. The provider-type set is closed and tiny, so polymorphic
dispatch buys extensibility for types that are never added. Concentration is deliberate: every
hot-path template lives in one file and is reviewed together. The private reaches are the compiler
co-evolving with the classes it compiles; the markers label a friendship, not a leak.
