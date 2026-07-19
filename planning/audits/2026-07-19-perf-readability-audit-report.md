# Perf & Readability Refactor Audit Report — 2026-07-19

**Spec:** planning/changes/2026-07-19.08-perf-readability-audit.md
**Baseline:** 8df6cff
**Method:** Two-lens multi-agent workflow (perf + readability finders; 3-lens adversarial verify: read-real-code, decision-conflict, invariant-safety; majority survive). No code changes; perf findings are bench-mapped hypotheses.

## Summary

| Bucket | Count |
|---|---|
| do-first | 2 |
| needs-decision | 0 |
| cleanup | 3 |
| skip | 0 |
| already-settled | 3 |

Two clean themes. First: **the resolve hot path is already at floor.** All three
performance findings (redundant override empty-check, unconditional context
override fetch, scope-navigation dict lookup) are micro-optimizations that shave
a single bool-check or dict.get per resolve, and all three collide with the
`child-lazy-alloc-declined` ruling — the maintainer has already set a measured
~2x-or-nothing bar for resolve-path branching, and none of these carry new
measurement, so they are recorded and not actioned. Second: **the readable gains
are all off-path**, concentrated in `types_parser.py`, `dependency_graph.py`,
`container.py`, and `wiring.py` — dense list-rotation and in-place-mutation
idioms, a duplicated init branch, an undocumented dual-exit, and a two-phase
method without a seam. The single most important takeaway: **there is no hot-path
work to do here** (perf is settled); the real yield is a handful of low-risk
clarity refactors in the parsing/graph/wiring modules, none touching an
invariant.

## do-first
### Cycle rotation to canonical form is dense
- Lens(es): readability
- File: modern_di/dependency_graph.py:69-72
- Leverage / Risk: high / low   ·   Confidence: high   ·   Hot path: no
- Invariant guarded: none (behavior preserved; verified 100% coverage intact)

**What.** The cycle-to-canonical rotation packs ring-slicing, an argmin over
`provider_id` via lambda, double-unpack rotation, and re-anchoring into four
terse lines. The intent (rotate so the lowest-id provider leads, then close the
ring) is buried in the list mechanics.

**Evidence.**
```python
ring = providers[:-1]
anchor = min(range(len(ring)), key=lambda i: ring[i].provider_id)
rotated = [*ring[anchor:], *ring[:anchor]]
canonical = [*rotated, rotated[0]]
```

**Direction.** Name each step (the ring, the anchor's role as canonical lead,
the closed cycle) so the rotation reads as its algorithm, not its slicing.

### Union type handling mutates args in-place
- Lens(es): readability
- File: modern_di/types_parser.py:35-44
- Leverage / Risk: high / low   ·   Confidence: high   ·   Hot path: no
- Invariant guarded: none (edge cases `Union[str,int,None]`, `Union[str,None]`, bare `None` traced identical; coverage intact)

**What.** Union decomposition builds `args`, conditionally `.remove()`s
`NoneType` in place, then branches on the mutated list's length. The reader must
track the list's changing state to follow the nullable/single-member logic.

**Evidence.**
```python
args = [typing.get_origin(x) or x for x in typing.get_args(type_)]
if types.NoneType in args:
    result["is_nullable"] = True
    args.remove(types.NoneType)
```

**Direction.** Split into `union_members` and `non_none_members` so the
filtering is expressed once, up front, without in-place state.

## needs-decision
(no findings)

## cleanup
### Registry initialization duplicates root-vs-child logic
- Lens(es): readability
- File: modern_di/container.py:104-110
- Leverage / Risk: medium / low   ·   Confidence: high   ·   Hot path: no
- Invariant guarded: none (logic unchanged, only relocated; helper always called from `__init__`, coverage intact)

**What.** `__init__` carries a 7-line if/else that either aliases the parent's
`providers_registry`/`overrides_registry` or constructs fresh ones (and registers
`Container`). It reads as inline plumbing inside the constructor.

**Evidence.**
```python
if parent_container:
    self.providers_registry = parent_container.providers_registry
    self.overrides_registry = parent_container.overrides_registry
else:
    self.providers_registry = ProvidersRegistry()
    self.providers_registry.register(Container, container_provider)
    self.overrides_registry = OverridesRegistry()
```

**Direction.** Extract a private `_setup_registries(parent_container)` so
`__init__` states the intent (share vs create) once.

### `_parse_parameter` has an unusual dual-exit control flow
- Lens(es): readability
- File: modern_di/types_parser.py:62-72
- Leverage / Risk: medium / low   ·   Confidence: high   ·   Hot path: no
- Invariant guarded: none (comment-only; behavior inert, coverage intact)

**What.** For a positional-only parameter the helper *returns None* when a
default exists but *raises* when it does not. The `None` return silently signals
`has_positional_only_gap` to `parse_creator`; that contract is non-obvious at the
call site. (CLAUDE.md explicitly allows a 1–2 line note for a genuinely
non-obvious constraint — this is one.)

**Evidence.**
```python
if param.kind is inspect.Parameter.POSITIONAL_ONLY:
    if param.default is not param.empty:
        return None
    raise exceptions.UnsupportedCreatorParameterError(...)
```

**Direction.** Add a one-line note that the `None` return signals a skippable
positional-only gap to `parse_creator`.

### `WiringPlan.build` has two phases without a visual seam
- Lens(es): readability
- File: modern_di/wiring.py:104-154
- Leverage / Risk: medium / low   ·   Confidence: medium   ·   Hot path: no
- Invariant guarded: none (pure code-move; mirrors existing `_apply_overlay` static-method pattern, coverage intact)

**What.** `build()` runs a by-type resolution loop that partitions
`parsed_kwargs`, then immediately runs an overlay pass over explicit `kwargs`.
The two-phase design is sound but the phases blend with no boundary marker.

**Evidence.**
```python
for name, item in parsed_kwargs.items():
    if kwargs and name in kwargs:
        continue
    provider = find_dep_provider(registry, owner, item)
    if provider is not None:
        ...
if kwargs:
    cls._apply_overlay(kwargs=kwargs, ...)
return cls(...)
```

**Direction.** Extract the by-type loop into a `_wire_by_type()` helper mirroring
the existing `_apply_overlay()`, making the by-type-then-overlay design explicit.

## skip
(no findings)

## already-settled
### Redundant empty-dict check in `fetch_override` hot path
- Matches: decision slug `child-lazy-alloc-declined` (planning/decisions/2026-07-19-child-lazy-alloc-declined.md)
- Lens(es): performance
- Note: read-real-code and invariant-safety both confirmed the redundancy is *real and safe* — every compiled resolver checks `has_overrides` before calling `fetch_override`, so the inner `if not self._overrides` never fails in that path. It is routed here purely because the fix is a resolve hot-path fast-path with no new measurement, which the ruling covers.

**Why settled.** The decision declines resolve hot-path branching for
sub-2x, unmeasured micro-optimizations: "measured saving is ~0 for realistic
caching request cycles … not worth a resolve hot-path branch." A single saved
bool-check per lookup falls far below that bar.

### Context resolution unconditionally checks for overrides
- Matches: decision slug `child-lazy-alloc-declined` (planning/decisions/2026-07-19-child-lazy-alloc-declined.md)
- Lens(es): performance
- Note: read-real-code and invariant-safety confirmed `_resolve_context_value` calls `fetch_override` per context param even when `has_overrides=False`; the proposed skip-flag is behavior-preserving. Settled by the same hot-path ruling — 1–3 saved `dict.get`s per resolve, unmeasured.

**Why settled.** Same ruling: resolve-path branches to skip work "not worth a
resolve hot-path branch" absent a measured, material win. Skipping an
override fetch that would return `UNSET` anyway is precisely such a branch.

### Scope navigation uses dict lookup even for the common path
- Matches: decision slug `child-lazy-alloc-declined` (planning/decisions/2026-07-19-child-lazy-alloc-declined.md)
- Lens(es): performance
- Note: read-real-code confirmed the `_navigate` → `find_container` → `_scope_map.get` lookup on cross-scope resolves. **invariant-safety declined** it independently: tuple-indexing by `scope.value - 1` breaks custom non-contiguous scope enums (`TENANT=6`, `JOB=10`) and the child-built `{**parent._scope_map, ...}` map, and CPython dict.get on small int keys is already near-optimal. So even setting the ruling aside, this one is unsafe as proposed.

**Why settled.** The ruling's stance — decline unmeasured resolve hot-path
branches — applies, and independently the invariant lens found the specific
tuple-index scheme would break custom-scope resolution. Recorded so it is not
re-raised; do not action.
