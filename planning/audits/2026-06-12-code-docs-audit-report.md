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
- **Evidence:** `modern_di/container.py:132` — `_visit` calls `provider.get_dependencies(self)` unguarded; `modern_di/providers/alias.py:32` raises `AliasSourceNotRegisteredError` from `_find_source` when the alias source is unregistered. Probe: a group with a dangling `Alias` plus a second broken provider, `Container(..., validate=True)` → raw `AliasSourceNotRegisteredError: Alias source type <class '...NotRegistered'> is not registered...` — no `ValidationFailedError`, and the second issue is never reported. Repro precondition: the alias must be bound under a type different from its source (`Alias(source_type=X, bound_type=Y)`); with the default `bound_type` the cycle path aggregates correctly, and with `bound_type=None` the alias is never registered.
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

#### B-7: Finalizers run in cache-item insertion order, not the documented reverse-resolve (LIFO) order
- **Severity:** high
- **Evidence:** `modern_di/registries/cache_registry.py:54,64` — `close_async`/`close_sync` iterate `self._items.values()` in dict insertion order; an item is inserted when `fetch_cache_item` is first called (`modern_di/providers/factory.py:197`), i.e. when a provider's resolve *starts*, before its dependencies are fetched. Within a single resolve chain this happens to give dependent-first teardown (probe S1: `['svc', 'dep', 'leaf']`), but if a dependency is resolved directly before its dependent, it is finalized first: probe S1b printed `teardown order (leaf resolved first): ['leaf', 'svc', 'dep']` — the leaf (dependency) finalized before `svc` (its dependent). `docs/providers/lifecycle.md:64` promises "Closing a container runs its finalizers in reverse-resolve order", and `docs/providers/lifecycle.md:12-17` *recommends* the exact trigger pattern (warm low-level resources at startup via `container.resolve(AsyncEngine)` before dependents are resolved).
- **Why it's a problem:** A dependent's finalizer (e.g. `session.close()`) can run after its dependency (e.g. the engine) was already disposed — exactly what reverse-order teardown exists to prevent — and the docs-recommended warmup pattern is what triggers it.
- **Proposed fix:** Record creation-completion order (e.g. append the CacheItem to an ordered list when `cache_item.cache` is set in `Factory.resolve`) and finalize in reverse of that order, or finalize `reversed(self._items.values())` after moving item insertion to creation time.
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` sections S1/S1b, quoted above)

#### B-8: Finalizer that is a sync callable returning an awaitable is called but never awaited — silent resource leak
- **Severity:** medium
- **Evidence:** `modern_di/providers/factory.py:23` types `finalizer` as `Callable[[T_co], None | typing.Awaitable[None]]` — explicitly admitting sync callables that *return* an awaitable — but `factory.py:27` sets `is_async_finalizer` solely via `inspect.iscoroutinefunction(self.finalizer)`. For `finalizer=lambda obj: real_async_cleanup(obj)`, `is_async_finalizer` is `False`, so `cache_registry.py:27` (close_async) and `:36` (close_sync) call it and discard the returned coroutine. Probe S2b: `events: []`, `warnings: ["coroutine 'real_async_cleanup' was never awaited"]`, `is_async_finalizer flag: False` — cleanup never ran, yet `finalized` was set to `True`.
- **Why it's a problem:** The cleanup silently never executes (resource leak) while the registry marks the item finalized; the only symptom is a `RuntimeWarning` that is easy to miss.
- **Proposed fix:** In `close_async`, after calling a non-coroutine-function finalizer, `await` the result if `inspect.isawaitable(result)`; in `close_sync`, raise `AsyncFinalizerInSyncCloseError` in that case instead of marking finalized. Alternatively narrow the type hint and reject awaitable-returning sync callables at `CacheSettings` construction.
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` section S2b, quoted above)

#### B-9: `set_context` on the same container is silently ignored after a dependent factory's kwargs were compiled
- **Severity:** medium
- **Evidence:** `modern_di/providers/factory.py:115-126` — at kwargs-compile time, a ContextProvider dep whose value is UNSET and whose parameter has a default is *dropped* from the compiled kwargs (`continue` at line 126); `factory.py:145-160` caches that decision per container via `cache_item.kwargs_compiled`, so it is never revisited. Probe S7: resolve a factory with `ctx: ReqCtx | None = None` (prints `ctx = None`), then `c.set_context(ReqCtx, ReqCtx(name="late"))`, resolve again on the *same* container → still `ctx = None`; a fresh container with the context at init prints `ReqCtx(name='early')`. The `set_context` docstring (`modern_di/container.py:169-177`) warns only about already-built *child* containers, not about the same container.
- **Why it's a problem:** The documented API for late context registration silently does nothing once any dependent factory has resolved on that container — values are dropped with no error and no docs warning for this case.
- **Proposed fix:** Invalidate compiled kwargs on `set_context` (e.g. bump a context-generation counter checked in `_ensure_kwargs_cached`), or defer the optional-ContextProvider decision to resolve time instead of compile time.
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` section S7, quoted above)

#### B-10: Failed group registration on a child container permanently pollutes the shared providers registry
- **Severity:** low
- **Evidence:** `modern_di/container.py:58-60` — groups are registered into `self.providers_registry`, which for a child is the parent's shared registry; `modern_di/registries/providers_registry.py:48-53` — `add_providers` registers one provider at a time with no rollback, raising `DuplicateProviderTypeError` mid-loop. Probe R1: `Container(scope=Scope.SESSION, parent_container=app, groups=[GR1child])` raised `DuplicateProviderTypeError` (group had `Extra` then a duplicate `Impl`), yet afterwards `app.providers_registry.find_provider(Extra) is not None` → `True`.
- **Why it's a problem:** A constructor that raises should not leave shared state mutated; the parent container silently gains providers from a child that was never created, and re-attempting registration of the same group then fails on `Extra` instead.
- **Proposed fix:** Validate the whole batch against the registry (and against itself) before registering, or roll back providers added in the failed `add_providers` call.
- **Verified by:** probe script output (`/tmp/audit_probe_alias_ctx.py` section R1, quoted above)

### Drift (docs vs code)

(none found in the core-code pass; the providers/registries pass added D-1 below — CLAUDE.md's registry-sharing claim table was cross-checked against `container.py:47-57` and is accurate: ProvidersRegistry shared, CacheRegistry per-container, ContextRegistry per-container, OverridesRegistry shared)

#### D-1: Docs promise "reverse-resolve order" finalization; code finalizes in cache-item insertion order
- **Severity:** medium
- **Evidence:** `docs/providers/lifecycle.md:64` — "Closing a container runs its finalizers in reverse-resolve order"; `docs/migration/from-that-depends.md:238` — "exiting it runs finalizers in reverse order". Actual behavior (`modern_di/registries/cache_registry.py:54,64`) is first-fetch insertion order, which differs from reverse-resolve order whenever a dependency is resolved directly before its dependent (probe S1b: `['leaf', 'svc', 'dep']`).
- **Why it's a problem:** Users design finalizers (close session before disposing engine) around the documented guarantee, which the code does not provide.
- **Proposed fix:** Fix the code per B-7; if B-7 is instead ruled intentional, rewrite both doc sentences to state the real insertion-order rule and its warmup caveat.
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` section S1b) + doc/code diff

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
- **Verified by:** code-path trace (cross-check of every `raise` in the eight audited files against errors.py; all 15 named strings (11 `*_ERROR` + 4 `SUGGESTION_*`) are used, no orphans)

#### Q-6: `pytest benchmarks/` collects zero tests — the run command documented inside the benchmark files silently runs nothing
- **Severity:** medium
- **Evidence:** Benchmark files are named `bench_*.py`, which does not match pytest's default `python_files = test_*.py` (no override in `pyproject.toml:69-73`). `uv run pytest benchmarks/ --collect-only -q --no-cov` → `no tests collected`; passing the three files explicitly collects 22 tests and all pass with `--benchmark-disable`. Yet `benchmarks/bench_override_fastpath.py:13` documents exactly the broken form: `uv run pytest benchmarks/ --benchmark-only --no-cov -v`.
- **Why it's a problem:** Anyone following the in-file instructions gets "no tests ran" (exit 5) and may conclude the benchmarks are gone; regressions in the measured fast paths go unbenchmarked.
- **Proposed fix:** Add `python_files = ["test_*.py", "bench_*.py"]` to `[tool.pytest.ini_options]` (benchmarks stay out of default runs since pytest-benchmark only activates with `--benchmark-*` flags — verify), or rename the files `test_bench_*.py` and exclude `benchmarks/` from default collection via `testpaths`.
- **Verified by:** probe commands (collect-only outputs quoted above; 22 tests pass with `--benchmark-disable`)

#### Q-7: bench_scope_map.py baseline formats an error template with a missing field — latent `KeyError`
- **Severity:** low
- **Evidence:** `benchmarks/bench_scope_map.py:34` — `errors.CONTAINER_SCOPE_IS_SKIPPED_ERROR.format(provider_scope=scope.name)`, but the template (`modern_di/errors.py:13-17`) now also requires `{container_scope}` (and mentions `{provider_scope}` twice). The baseline `_baseline_find_container` would raise `KeyError: 'container_scope'` instead of the simulated error if its skipped-scope branch were ever hit; current scenarios never hit it.
- **Why it's a problem:** The "pre-fix baseline" no longer reproduces pre-fix behavior; the first person to extend the benchmark into an error path gets a confusing `KeyError`.
- **Proposed fix:** Format with both fields, or replace the simulated raise with a plain `RuntimeError("skipped scope")` since the message text is irrelevant to the measurement.
- **Verified by:** code-path trace (template fields vs `format` kwargs)

#### Q-8: bench_kwargs_split.py dead container setup and wrong-variable isinstance in the micro-benchmark
- **Severity:** low
- **Evidence:** `benchmarks/bench_kwargs_split.py:98-116` — `test_singleton_optimized` builds a full container with a dynamically created `type("G", (Group,), {...})` group, then immediately rebuilds `container` from `SGroup` at line 125, discarding the first (dead code that still registers three providers). `benchmarks/bench_kwargs_split.py:183` — the "unified" micro-benchmark dict-comp reads `k if isinstance(k, AbstractProvider) else v`, testing the *key* (always `str`) instead of the value `v` it intends to simulate.
- **Why it's a problem:** The dead setup wastes provider ids and confuses readers about which group is measured; the wrong-variable isinstance means the micro-benchmark measures `isinstance(str, ...)` rather than the value-side check it documents.
- **Proposed fix:** Delete lines 98-116; change line 183 to `v if isinstance(v, AbstractProvider) else v` (or mirror the real pre-fix expression on `v`).
- **Verified by:** code-path trace (first `container` binding never used; comprehension variable inspection)

#### Q-9: `AbstractProvider` defines no `__slots__`, so every provider instance carries a `__dict__` and all subclass `__slots__` are defeated
- **Severity:** low
- **Evidence:** `modern_di/providers/abstract.py:15-16` — the class declares `BASE_SLOTS` (a ClassVar consumed by subclasses) but no `__slots__` of its own, so it contributes `__dict__` to every instance. Probe R2: `Factory instance has __dict__: True`, and assigning an arbitrary attribute (`f.totally_new_attribute = 1`) succeeds despite `Factory.__slots__`.
- **Why it's a problem:** The memory/typo-protection benefits the five subclasses' `__slots__` declarations are written to provide are silently nullified; misspelled attribute writes on providers go undetected.
- **Proposed fix:** Add `__slots__ = ("scope", "bound_type", "provider_id")` (i.e. the BASE_SLOTS) on `AbstractProvider` and drop `BASE_SLOTS` from subclass slot lists (keeping each subclass declaring only its own fields).
- **Verified by:** probe script output (`/tmp/audit_probe_alias_ctx.py` section R2, quoted above)

### DX (public API)

#### X-1: Resolving from a closed container silently succeeds and re-creates singletons
- **Severity:** low
- **Evidence:** `modern_di/container.py:158-161` — `close_sync` runs finalizers and clears caches but sets no closed flag; nothing in `resolve`/`resolve_provider` checks one. Probe: after `close_sync()` (finalizer ran), `resolve(Svc)` returns a fresh instance (`same instance as before close: False`), and a second `close_sync()` runs the finalizer again.
- **Why it's a problem:** A use-after-close bug in application code (e.g. resolving from an APP container after shutdown) is invisible: resources are silently re-created after their finalizers ran, and may never be finalized if no further close happens.
- **Proposed fix:** Either document container reuse after close as a supported pattern, or track a closed state and raise a clear `ContainerError` on resolve-after-close (re-arming via context-manager re-entry if reuse is desired).
- **Verified by:** probe script output (`/tmp/audit_probe_container.py` section 1, quoted above)

#### X-2: `skip_creator_parsing=True` with missing required arguments fails at resolve time with a raw `TypeError`
- **Severity:** low
- **Evidence:** `modern_di/providers/factory.py:43-52` — with `skip_creator_parsing=True`, `_parsed_kwargs` is empty and kwargs validation is skipped entirely, so nothing checks that `kwargs` covers the creator's required parameters; `factory.py:212` then calls the creator. Probe S5: `resolve raised: TypeError: needs_args() missing 2 required positional arguments: 'x' and 'y'` — no DI exception type, no dependency-chain rendering, no hint that the fix is the Factory's `kwargs`.
- **Why it's a problem:** Every other resolution failure raises a `ResolutionError` with chain context; this one surfaces as a bare `TypeError` pointing at the creator, with the misconfiguration (incomplete `kwargs` on the provider) nowhere in the message.
- **Proposed fix:** When `skip_creator_parsing=True`, still call `inspect.signature` best-effort at declaration time and raise a registration error for required params absent from `kwargs`; or wrap the creator call's `TypeError` in an `ArgumentResolutionError` naming the provider.
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` section S5, quoted above)

#### X-3: An `AbstractProvider` instance passed as a static `kwargs` value is silently resolved instead of passed through
- **Severity:** low
- **Evidence:** `modern_di/providers/factory.py:141-142` merges `self._kwargs` into the compiled kwargs, and `factory.py:152-156` classifies every merged value by `isinstance(v, AbstractProvider)` — so a provider object given as a *value* lands in `provider_kwargs` and is resolved at each resolve. Probe S4b: `Factory(creator=Holder, kwargs={"leaf": side_provider})` injected a `Leaf` instance, not the provider object. (Static kwargs winning over type-resolution for the same param name is correct and documented — `docs/providers/factories.md:25-28`; probe S4 confirmed.)
- **Why it's a problem:** "Manual values for creator parameters" (the documented contract of `kwargs`) is violated for one value type, invisibly; whether this is an intentional explicit-wiring feature or an accident of the isinstance split is undocumented either way.
- **Proposed fix:** Decide and document: either support it explicitly ("a provider passed in kwargs is resolved — use this for manual wiring") in `docs/providers/factories.md`, or treat `kwargs` values as opaque (skip the isinstance reclassification for keys originating from `self._kwargs`).
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` sections S4/S4b, quoted above)

#### X-4: `validate()` rejects a working graph when an Alias's decorative scope is shallower than its source's scope
- **Severity:** medium
- **Evidence:** `modern_di/providers/alias.py:20` — `Alias` defaults to `scope=Scope.APP` and its `resolve` (`alias.py:38-39`) never consults `self.scope`; resolution works regardless. But `Container.validate` (`modern_di/container.py:133-140`) applies the `dep_provider.scope > provider.scope` check to the alias's `source` edge. Probe A3: `Alias(source_type=Impl, bound_type=IfaceA)` over a REQUEST-scoped `Impl` — `req.resolve(IfaceA)` returns `Impl`, yet `validate()` raises `ValidationFailedError: ... InvalidScopeDependencyError: Provider IfaceA (scope APP) declares parameter 'source' ... at deeper scope REQUEST`. (prior wont-fix, new angle: "Alias scope is decorative" was accepted for resolution, but `validate()` treats that decorative scope as load-bearing, producing a false positive that forces users to either annotate redundant scopes on aliases or abandon `validate=True`.)
- **Why it's a problem:** The library's recommended safety net (`docs/providers/lifecycle.md:93` — "Turn it on") fails on graphs that work, training users to disable validation.
- **Proposed fix:** Have `validate()` skip the scope check for `Alias` edges (or make `Alias` inherit its source's scope at validation time), consistent with the wont-fix decision that alias scope is decorative.
- **Verified by:** probe script output (`/tmp/audit_probe_alias_ctx.py` section A3, quoted above)

#### X-5: Mutual alias cycle on an unvalidated container surfaces as a raw `RecursionError`
- **Severity:** low
- **Evidence:** `modern_di/providers/alias.py:38-39` — `Alias.resolve` recurses into `container.resolve_provider(source)` with no cycle guard. Probe A2: two aliases pointing at each other — `validate=True` correctly raises `ValidationFailedError` with `CircularDependencyError: IfaceA -> IfaceB -> IfaceA`, but plain `resolve(IfaceA)` raises a bare `RecursionError` with no DI context (alias chains also get no `ResolutionStep` in dependency-chain rendering, unlike Factory edges — `factory.py:207-209`).
- **Why it's a problem:** Without opt-in validation, a two-line alias typo produces a thousand-frame `RecursionError` instead of the rich cycle error the library can already produce.
- **Proposed fix:** Track a small per-resolve visited set for alias hops (alias chains are short), or at minimum have `Alias.resolve` prepend a `ResolutionStep` so the recursion is attributable; document `validate=True` as the cycle guard in `docs/providers/alias.md`.
- **Verified by:** probe script output (`/tmp/audit_probe_alias_ctx.py` section A2, quoted above)

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

#### G-4: Same-container `set_context` staleness is missing from the context troubleshooting page
- **Severity:** medium
- **Evidence:** `docs/troubleshooting/context-not-set.md:17-45` documents two failure modes ("set_context on the parent after the child was built", "scope mismatch between provider and registry"), and `docs/recipes/async-lifespan.md:52-53` warns about ordering vs children — but no page mentions that `set_context` on the *same* container is ignored once a dependent factory has resolved (B-9, probe S7: ctx stays `None` after `set_context` on the very container being resolved from). The ContextProvider scope-selects-registry semantics themselves are documented (`docs/troubleshooting/context-not-set.md:43-45`, confirmed accurate by probe C2) — no gap there.
- **Why it's a problem:** This is precisely the "context not set" symptom that page exists to triage, and its third cause is absent; users following the page's two fixes won't find this one.
- **Proposed fix:** If B-9 is fixed, no doc change needed; if it is ruled intentional, add a third numbered cause to `docs/troubleshooting/context-not-set.md` ("set_context after the dependent factory already resolved on this container") with the fresh-container workaround.
- **Verified by:** probe script output (`/tmp/audit_probe_factory.py` section S7) + docs grep
