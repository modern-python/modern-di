---
summary: The resolver compiler reads provider internals across module lines (22 reads, 5 attributes, 4 provider types); a compile-spec handoff would remove the coupling, but it is a design change and the coupling is currently static, so SLF001 is suppressed per-file instead.
---

# Hand the compiler a compile-spec instead of reading provider internals

`modern_di/resolver_compiler.py` builds each provider's resolver by reaching
directly into that provider's private attributes — `Factory._creator`,
`_parsed_kwargs`, `_kwargs`, `_resolution_step`, `_resolve_context_value`,
`_call_creator`, `_argument_resolution_error`, `_has_positional_only_gap`,
`Alias._find_source`. `SLF001` is now suppressed for that whole file via
`per-file-ignores` rather than on individual lines. The alternative — giving
each provider type a method that returns an explicit compile-spec, so no
underscored attribute crosses a module boundary — was not taken.

## Why it is open

The coupling is real but it is **static and small**: 22 private reads across 5
attribute groups on 4 provider types (`Factory`, `Alias`, `ContextProvider`,
`_ContainerProvider`), and it has not grown as the compiler has. A per-file
suppression is an honest description of a file whose documented job is exactly
this: CLAUDE.md's key-files entry calls `resolver_compiler.py` "the **single
resolve path**", and the coupling is what lets each resolver hold its per-node
frame budget at 1.

Doing the spec handoff properly is a design change, not a refactor, and it has
a cost on both sides:

- Every provider type gains a compile-spec method, and the spec object becomes
  a second surface that must stay in sync with the attributes it mirrors.
- `compile_resolver` already requires a new branch per provider type (it raises
  `TypeError` for an unknown one); a spec adds a second thing a new provider
  type must implement, so the "add a provider type" cost goes up, not down.
- It is compile-time only, so it buys **no** hot-path nanoseconds — the reads
  are hoisted into closure locals once per provider. The whole case for it is
  coupling hygiene.

The reason not to do it opportunistically is that the per-file suppression is
only defensible while the coupling stays still. A suppression that quietly
absorbs new private reads stops being a description and becomes a blindfold.

## Revisit trigger

`resolver_compiler.py` needs to read a private attribute it does not already
read — most likely because a new provider type was added and `compile_resolver`
grew a branch. That is the signal that the coupling is growing rather than
sitting still, and it is checkable in a diff against the baseline recorded
above (22 reads, 5 attribute groups, 4 provider types). At that point the
per-file `SLF001` ignore should be replaced by the compile-spec handoff rather
than extended.
