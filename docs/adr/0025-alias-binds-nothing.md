# The alias hop inlines, but binds nothing

**Decision:** `_compile_alias`'s closure reads `container.providers_registry` per resolve and inlines
both the source lookup and the source's resolver-memo read. It holds no reference to the source, its
resolver, or the registry. Inline-only ships at **~322 → ~252 ns (-22%)** and 4 frames → 1, giving up
roughly a third of the available win: an eager bind (resolve the source at compile time, close over
its resolver) measured **305.5 → 192.0 ns (-36%)**, reproduced by two independent verifiers, and a
lazy bind behind a `bound is None` branch has the same steady-state cost.

**A bind buys an invalidation invariant; the inline buys none.** Both bind variants are sound only
because `ProvidersRegistry._invalidate()` clears `_resolvers`, so a stale binding dies with the
closure holding it. True today, but a *second* place the invariant has to hold — stated, defended,
and re-checked by anyone who later touches memo publication. The inline re-reads the live registry
and cannot go stale by construction. Same reasoning that dropped the
[warm-singleton memo swap](0015-warm-singleton-memo-swap-dropped.md): a bounded win does not buy a
permanent cross-cutting invariant.

**Eager bind additionally escapes the override front-guard**, compiling the alias's whole source
subtree even when the alias is overridden and the source is never touched — the `modern-di-pytest`
mock pattern. `len(_resolvers)` after resolving an overridden alias goes from 1 to 1+depth (11 at
depth 10), cold cost +404%; it also raises `TypeError` eagerly for a source type `compile_resolver`
does not know, and drops the maximum pure alias chain from 494 to 329 hops. Lazy bind avoids all of
this; only the invariant argument rules it out.

**Capturing the registry was declined on the same grounds one level down.** The first shipped form
took the registry as a compile-time parameter, saving one attribute load per hop. Since the registry
memoizes the closure in `_resolvers`, that made this the only compiled resolver forming
`registry → _resolvers → closure → cell → registry` — freeable then only by cyclic GC, never by
refcounting. Not a leak, but the repo already took the opposite position for containers (`64b7cec`),
and registries are per-root-container, so a suite building a container per test builds one per test.
Reading the registry off the `container` argument removed the cycle and measured **free** (250 → 249
ns, inside noise), which also puts the alias in the shape every other closure in the module uses.

Pinned by `test_alias_hop_costs_exactly_one_resolver_frame`,
`test_no_compiled_resolver_closes_over_its_registry`,
`test_overridden_alias_compiles_nothing_of_its_source`, and
`test_alias_picks_up_a_source_registered_after_a_failed_resolve` — that last catches only a
*negative* cache; a success-path cache is undetectable by construction, since a registered type's
provider can never be replaced and any registration clears `_resolvers`.

**Revisit trigger:** an alias hop shows up hot in a profile from a real integration, **and** the
`_invalidate()`-clears-`_resolvers` invariant has acquired an explicit owner and test of its own — at
which point lazy bind (never eager) is worth the remaining ~60 ns. A second compiled closure needing
the registry at resolve time would reopen the capture question separately.
