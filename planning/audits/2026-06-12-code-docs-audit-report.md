# Code & Docs Audit Report — 2026-06-12

**Spec:** docs/superpowers/specs/2026-06-12-code-docs-audit-design.md
**Baseline:** lint-ci PASS, pytest PASS (100% coverage), at commit 9f07b08
**Prior audit:** planning/audits/2026-06-05-bug-hunt-audit-report.md

## Summary

(filled at the end of the audit)

## Finding format

Every finding uses:

#### <ID>: <one-line title>
- **Severity:** high | medium | low
- **Evidence:** `file.py:NN` — what the code/doc actually says/does
- **Why it's a problem:** one or two sentences
- **Proposed fix:** concrete change, one or two sentences
- **Verified by:** probe script output | code-path trace | doc/code diff

IDs: B-n Bugs, D-n Drift, Q-n Quality, X-n DX, G-n Docs gaps.

## Findings

### Bugs

#### B-1: Parameterized generic annotations are silently degraded to their origin type
- **Severity:** medium
- **Evidence:** `modern_di/types_parser.py:43-45` — for a generic annotation, `SignatureItem` stores only `typing.get_origin(type_)` as `arg_type` (`list[Svc]` → `list`); `modern_di/providers/factory.py:99-101` then looks up a provider for the bare origin. Probe: with a `Svc` provider registered, `def __init__(self, x: list[Svc])` fails with `Argument x of type <class 'list'> cannot be resolved` — the error names `list`, not the `list[Svc]` the user wrote. Worse, registering any provider with `bound_type=list` silently satisfies `list[Svc]` (and would satisfy `list[Anything]`): probe printed `NeedsList.x == ['sentinel']  (annotation was list[Svc]!)`.
- **Why it's a problem:** The error message points at a type the user never wrote, and the origin-only match can silently inject a value of the wrong element type with no warning.
- **Proposed fix:** Keep the original annotation on `SignatureItem` and use it in `ArgumentResolutionError` messages; either match the full parameterized type in the registry or raise a clear declaration-time error that parameterized generics are not resolvable.
- **Verified by:** probe script output (`/tmp/audit_probe_parser.py` sections 3, 3b, 3c, quoted above)

#### B-2: `functools.partial` creator crashes at declaration with an uncaught `TypeError` from `get_type_hints`
- **Severity:** medium
- **Evidence:** `modern_di/types_parser.py:64-65` — `typing.get_type_hints(creator)` is wrapped in `except NameError` only. For a `functools.partial` creator, `inspect.signature` succeeds but `get_type_hints` raises `TypeError`. Probe: `providers.Factory(creator=functools.partial(partial_target, y=1))` → `TypeError: functools.partial(<function partial_target ...>, y=1) is not a module, class, method, or function.`
- **Why it's a problem:** A plausible creator pattern fails at declaration with a raw `typing` internals message that never mentions modern-di, the Factory, or the `skip_creator_parsing=True` escape hatch.
- **Proposed fix:** Catch `TypeError` alongside `NameError` (warn-and-skip the same way), or resolve hints from `creator.func` for partials; the warning should mention `skip_creator_parsing=True`/`bound_type` as the workaround.
- **Verified by:** probe script output (`/tmp/audit_probe_parser.py` section 8, quoted above)

#### B-3: Positional-only creator parameters are parsed and resolved, then fail at resolve time with a raw `TypeError`
- **Severity:** medium
- **Evidence:** `modern_di/types_parser.py:75` skips only `VAR_POSITIONAL`/`VAR_KEYWORD`, so `POSITIONAL_ONLY` params land in `param_hints`; `modern_di/providers/factory.py:212/221` always calls `self._creator(**resolved_kwargs)`. Probe: `def pos_only_creator(x: Svc, /, y: Svc2)` with both deps registered → `TypeError: pos_only_creator() got some positional-only arguments passed as keyword arguments: 'x'`.
- **Why it's a problem:** Declaration succeeds silently and dependencies are actually resolved (side effects included) before the call blows up with a non-DI error lacking the dependency-chain context every other resolution failure gets.
- **Proposed fix:** Detect `POSITIONAL_ONLY` parameters in `parse_creator` and raise a clear declaration-time error (or pass them positionally in declaration order in `Factory.resolve`).
- **Verified by:** probe script output (`/tmp/audit_probe_parser.py` section 4b, quoted above)

#### B-4: Unannotated parameter failure reports "Argument x of type None"
- **Severity:** low
- **Evidence:** `modern_di/errors.py:23-25` (`FACTORY_ARGUMENT_RESOLUTION_ERROR`) is formatted with `arg_type=None` when the parameter has no annotation (`modern_di/providers/factory.py:128-135`). Probe: `def unannotated_creator(x) -> Svc` → `Argument x of type None cannot be resolved.` Same for `lambda x: Svc()`.
- **Why it's a problem:** "of type None" reads as if the parameter were annotated `None`/`NoneType`; the actual problem — a missing annotation, which type-based wiring can never satisfy — is not stated.
- **Proposed fix:** When `arg_type is None` and `args` is empty, render a dedicated message, e.g. "Argument {arg_name} has no type annotation, so it cannot be resolved by type; pass it via kwargs or add an annotation."
- **Verified by:** probe script output (`/tmp/audit_probe_parser.py` sections 6 and 8b, quoted above)

#### B-5: `validate()` aborts on a dangling Alias instead of aggregating it into ValidationFailedError
- **Severity:** medium
- **Evidence:** `modern_di/container.py:132` — `_visit` calls `provider.get_dependencies(self)` unguarded; `modern_di/providers/alias.py:32` raises `AliasSourceNotRegisteredError` from `_find_source` when the alias source is unregistered. Probe: a group with a dangling `Alias` plus a second broken provider, `Container(..., validate=True)` → raw `AliasSourceNotRegisteredError: Alias source type <class '...NotRegistered'> is not registered...` — no `ValidationFailedError`, and the second issue is never reported.
- **Why it's a problem:** Breaks the validate() contract of collecting all issues into one `ValidationFailedError`: callers catching `ValidationFailedError`/`ContainerError` miss this `ResolutionError`, and multi-issue graphs are reported one issue at a time.
- **Proposed fix:** In `_visit`, wrap the `get_dependencies` call in `try/except ResolutionError` and append to `validation_errors` (or give `Alias` an `iter_validation_issues` that yields the error and make its `get_dependencies` tolerate a missing source).
- **Verified by:** probe script output (`/tmp/audit_probe_container.py` section 5c, quoted above)
- **Note:** a dependency cycle *through* a ContextProvider is structurally impossible (it has no outgoing edges), so the probe validated a chain through one instead; this is the maximal realizable test for that spec item.

#### B-6: `Container.__init__` accepts a `parent_container` with a non-increasing scope, silently shadowing the parent's scope_map entry
- **Severity:** medium
- **Evidence:** `modern_di/container.py:30-46` — `__init__` takes the public `parent_container` kwarg with no scope-ordering check (the check exists only in `build_child_container`, `container.py:70-75`); `scope_map = {**parent_container.scope_map, scope: self}` overwrites the parent's entry for the same scope. Probe: `Container(scope=Scope.APP, parent_container=app_root)` is accepted; an APP-scoped singleton then resolves to a second, different instance through the shadow container (`a is not b` → True).
- **Why it's a problem:** A public constructor parameter bypasses the scope-hierarchy invariant with no error, silently duplicating "singletons" — exactly the failure `InvalidChildScopeError` exists to prevent.
- **Proposed fix:** In `__init__`, when `parent_container` is given, raise `InvalidChildScopeError` if `scope <= parent_container.scope` (same check as `build_child_container`).
- **Verified by:** probe script output (`/tmp/audit_probe_container.py` section 8, quoted above)

### Drift (docs vs code)

(none found in this pass — core-code pass; drift is covered by the docs pass)

### Quality (internals)

#### Q-1: `SignatureItem.is_nullable` is computed and tested but never read by resolution
- **Severity:** low
- **Evidence:** `modern_di/types_parser.py:14,32` — `is_nullable` is set for `X | None`/`Optional[X]`; grep shows the only other references are assertions in `tests/test_types_parser.py`. `Factory._compile_kwargs` (`modern_di/providers/factory.py:112-141`) never consults it: probe shows `def __init__(self, x: Svc | None)` with no `Svc` provider and no default raises `ArgumentResolutionError` instead of injecting `None`.
- **Why it's a problem:** Dead data that suggests nullable-aware behavior which doesn't exist; a user who annotated `Svc | None` has explicitly accepted `None`, yet resolution errors out.
- **Proposed fix:** Either use the flag (inject `None` for nullable params when no provider matches and no default exists) or delete the field and its tests, and document that nullability is ignored.
- **Verified by:** probe script output (`/tmp/audit_probe_parser.py` section 2) + grep (no reads outside tests)

#### Q-2: Unused module-level `T`/`P` type variables in group.py
- **Severity:** low
- **Evidence:** `modern_di/group.py:11-12` — `T = typing.TypeVar("T")` and `P = typing.ParamSpec("P")` are defined but referenced nowhere in the module, and no other module imports them (grep across `modern_di/` and `tests/`).
- **Why it's a problem:** Dead code; readers look for a generic protocol in `Group` that doesn't exist.
- **Proposed fix:** Delete both lines.
- **Verified by:** code-path trace (grep: no usages)

#### Q-3: Unused `T_co` and `_UNSET` in overrides_registry.py (adjacent file, found during cross-check)
- **Severity:** low
- **Evidence:** `modern_di/registries/overrides_registry.py:7,9` — `T_co = typing.TypeVar("T_co", covariant=True)` and `_UNSET = object()` are defined but unused; `fetch_override` uses `types.UNSET` instead.
- **Why it's a problem:** `_UNSET` is a leftover from before the shared `types.UNSET` sentinel; a future edit could accidentally compare against the wrong sentinel.
- **Proposed fix:** Delete both lines.
- **Verified by:** code-path trace (grep within the file)

#### Q-4: Redundant second `get_origin` pass in union parsing
- **Severity:** low
- **Evidence:** `modern_di/types_parser.py:30` already maps every union member through `typing.get_origin(x) or x`; line 35 re-applies the identical transform to the already-normalized list, which is a no-op.
- **Why it's a problem:** Dead transform that obscures the actual normalization step and invites "why twice?" confusion during maintenance.
- **Proposed fix:** Delete line 35.
- **Verified by:** code-path trace (`get_origin` of a non-generic origin/class returns `None`, so the second pass keeps every element unchanged)

#### Q-5: Error-message centralization is inconsistent between errors.py and exceptions.py
- **Severity:** low
- **Evidence:** `modern_di/errors.py` holds 11 `*_ERROR` message templates and 4 `SUGGESTION_*` constants (15 total), but five exception classes build their messages inline: `UnknownFactoryKwargError` (`modern_di/exceptions.py:214-223`), `ValidationFailedError` (:257-263), `FinalizerError` (:272-273), `AsyncFinalizerInSyncCloseError` (:283-286), `GroupInstantiationError` (:294).
- **Why it's a problem:** Half-applied convention: contributors can't tell where a message lives or where new ones belong, and the templates module no longer covers the error surface it implies it does.
- **Proposed fix:** Move the static parts of the five inline messages into `errors.py` templates (or document in errors.py that multi-line/loop-built messages stay inline).
- **Verified by:** code-path trace (cross-check of every `raise` in the eight audited files against errors.py; all 12 templates are used, no orphans)

### DX (public API)

#### X-1: Resolving from a closed container silently succeeds and re-creates singletons
- **Severity:** low
- **Evidence:** `modern_di/container.py:158-161` — `close_sync` runs finalizers and clears caches but sets no closed flag; nothing in `resolve`/`resolve_provider` checks one. Probe: after `close_sync()` (finalizer ran), `resolve(Svc)` returns a fresh instance (`same instance as before close: False`), and a second `close_sync()` runs the finalizer again.
- **Why it's a problem:** A use-after-close bug in application code (e.g. resolving from an APP container after shutdown) is invisible: resources are silently re-created after their finalizers ran, and may never be finalized if no further close happens.
- **Proposed fix:** Either document container reuse after close as a supported pattern, or track a closed state and raise a clear `ContainerError` on resolve-after-close (re-arming via context-manager re-entry if reuse is desired).
- **Verified by:** probe script output (`/tmp/audit_probe_container.py` section 1, quoted above)

### Docs gaps

#### G-1: Creator-signature support matrix is undocumented (generics, positional-only, partial, unannotated params)
- **Severity:** medium
- **Evidence:** Probes show four signature shapes that degrade or fail (`list[Svc]` matched by bare origin — B-1; positional-only params — B-3; `functools.partial` — B-2; unannotated params unresolvable by type). `grep -rE "positional-only|functools.partial"` over `docs/` finds no user-facing coverage (only the audit plan file); expected home: `docs/providers/factories.md:13` (introduces `creator` parameter) — no such section exists.
- **Why it's a problem:** Users cannot predict which creator signatures wire correctly; the failures are discovered at runtime instead of in the docs.
- **Proposed fix:** Add a "supported creator signatures" subsection to `docs/providers/factories.md` listing what is wired, what is skipped, and what raises — for the docs pass to confirm and place.
- **Verified by:** probe script output + docs grep

#### G-2: Container reuse after close is undocumented
- **Severity:** low
- **Evidence:** Probe shows `resolve()` after `close_sync()` re-creates and re-caches instances and a later close re-runs finalizers; `grep -rniE "after clos|reuse"` over `docs/` shows no statement either way (closest: `docs/providers/factories.md:146` about cache eviction at close).
- **Why it's a problem:** Whether a closed container is dead or reusable is core lifecycle semantics; today the behavior (reusable, silently) is discoverable only by experiment.
- **Proposed fix:** State the reuse-after-close semantics explicitly in the lifecycle docs (ties to X-1 — docs pass to confirm wording once the X-1 decision lands).
- **Verified by:** probe script output + docs grep

#### G-3: Nullable annotation semantics are undocumented (`X | None` never injects None)
- **Severity:** low
- **Evidence:** Probe: `def __init__(self, x: Svc | None)` with no provider and no default raises `ArgumentResolutionError`; `None` is injected only via a `= None` default. Docs grep for optional/nullable parameter semantics finds nothing user-facing; expected home: `docs/providers/factories.md:27` (discusses `kwargs` / manual parameter values, closest to optional-resolution semantics) — no such section exists.
- **Why it's a problem:** Inconsistent with `ContextProvider` returning `None` when unset (documented wont-fix), users may reasonably expect `Optional` params to receive `None`.
- **Proposed fix:** Document that union annotations resolve by their first registered member and that `None` is never injected without a default (ties to Q-1 — docs pass to confirm).
- **Verified by:** probe script output + docs grep
