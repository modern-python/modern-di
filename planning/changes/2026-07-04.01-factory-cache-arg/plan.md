# Factory `cache=` Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `cache` argument to `Factory` accepting `bool | CacheSettings | None`, so the common "just cache it" case is `cache=True`, and deprecate the `cache_settings=` alias.

**Architecture:** All sugar lives in `Factory.__init__`: the new `cache` input is normalized once into the existing internal attribute `self.cache_settings` (still a `CacheSettings | None`), so `resolve()`, the cache registry, and `__repr__` are untouched. `cache_settings=` remains a warn-only deprecated alias. `CacheSettings` is unchanged.

**Tech Stack:** Python 3.10+, `uv`, `just`, `pytest` (+ pytest-asyncio auto mode), `ruff` (`select=ALL`), `ty`.

## Global Constraints

- Zero runtime dependencies. Line length 120. `ruff` `select=["ALL"]` and `ty` must pass (`just lint-ci`).
- Full gated suite `just test-ci` must stay at **100% line coverage** (`TYPE_CHECKING` blocks excluded).
- All imports at module level. Annotate every function argument. Use `# ty: ignore`, never `# type: ignore`.
- Resolution is sync-only; finalizers may be sync or async (unchanged here).
- Conventional-commit subjects. Branch off `main` (suggested: `feat/factory-cache-arg`); ship via PR, never local-merge.
- Spec: `planning/changes/2026-07-04.01-factory-cache-arg/design.md`. Decision record: `planning/decisions/2026-07-04-cache-arg-over-singleton-class.md`.

---

### Task 1: `cache=` argument, normalization, and `cache_settings=` deprecation

**Files:**
- Modify: `modern_di/providers/factory.py:34-75` (`Factory.__init__` signature + normalization; the assignment at line 74)
- Test: `tests/providers/test_factory.py` (append new tests at end of file)

**Interfaces:**
- Consumes: `types.UNSET`, `types.UnsetType` (already imported in `factory.py`); `CacheSettings` (defined in the same module); `warnings` (already imported).
- Produces: `Factory(*, ..., cache: bool | CacheSettings[T] | None = None, cache_settings: CacheSettings[T] | None | UnsetType = UNSET, ...)`. After construction, `provider.cache_settings` is a normalized `CacheSettings | None` (unchanged type). Later tasks (docs) rely only on the public spelling `cache=True` / `cache=CacheSettings(...)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/providers/test_factory.py` (imports `warnings`, `pytest`, `Container`, `Group`, `Scope`, `providers` are already present at the top of the file):

```python
def test_cache_true_returns_same_instance() -> None:
    class G(Group):
        f = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache=True)

    container = Container(groups=[G])
    assert container.resolve_provider(G.f) is container.resolve_provider(G.f)
    assert isinstance(G.f.cache_settings, providers.CacheSettings)


def test_cache_absent_returns_fresh_instances() -> None:
    class G(Group):
        f = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"})

    container = Container(groups=[G])
    assert container.resolve_provider(G.f) is not container.resolve_provider(G.f)
    assert G.f.cache_settings is None


@pytest.mark.parametrize("cache_value", [False, None])
def test_cache_falsy_disables_caching(cache_value: bool | None) -> None:
    class G(Group):
        f = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache=cache_value)

    container = Container(groups=[G])
    assert container.resolve_provider(G.f) is not container.resolve_provider(G.f)
    assert G.f.cache_settings is None


def test_cache_accepts_cache_settings_and_finalizes() -> None:
    cleaned: list[object] = []

    class G(Group):
        f = providers.Factory(creator=dict, cache=providers.CacheSettings(finalizer=cleaned.append))

    container = Container(groups=[G])
    instance = container.resolve_provider(G.f)
    assert container.resolve_provider(G.f) is instance
    container.close_sync()
    assert cleaned == [instance]


def test_cache_settings_is_deprecated_but_functional() -> None:
    with pytest.warns(DeprecationWarning, match="cache_settings"):
        provider = providers.Factory(
            creator=SimpleCreator, kwargs={"dep1": "x"}, cache_settings=providers.CacheSettings()
        )
    container = Container()
    assert container.resolve_provider(provider) is container.resolve_provider(provider)


def test_cache_settings_none_emits_no_deprecation_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        provider = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache_settings=None)
    assert provider.cache_settings is None


def test_cache_and_cache_settings_together_raise() -> None:
    with pytest.raises(TypeError, match="pass only `cache`"):
        providers.Factory(
            creator=SimpleCreator, kwargs={"dep1": "x"}, cache=True, cache_settings=providers.CacheSettings()
        )


def test_repr_reports_cached_for_cache_true() -> None:
    provider = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache=True)
    assert "cached=True" in repr(provider)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `just test tests/providers/test_factory.py -k "cache_true or cache_absent or cache_falsy or cache_accepts or deprecated or none_emits or together_raise or repr_reports"`
Expected: FAIL — `Factory.__init__` has no `cache` parameter (`TypeError: __init__() got an unexpected keyword argument 'cache'`).

- [ ] **Step 3: Implement the signature + normalization**

In `modern_di/providers/factory.py`, replace the `__init__` signature and the start of its body. Change the signature (lines 34-43) to add `cache` and make `cache_settings` a sentinel-defaulted deprecated alias:

```python
    def __init__(  # noqa: PLR0913
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        creator: typing.Callable[..., types.T_co],
        bound_type: type | None | types.UnsetType = types.UNSET,
        kwargs: dict[str, typing.Any] | None = None,
        cache: bool | CacheSettings[types.T_co] | None = None,
        cache_settings: CacheSettings[types.T_co] | None | types.UnsetType = types.UNSET,
        skip_creator_parsing: bool = False,
    ) -> None:
        if not isinstance(cache_settings, types.UnsetType):
            if cache is not None:
                msg = "pass only `cache`, not both `cache` and the deprecated `cache_settings`"
                raise TypeError(msg)
            if cache_settings is not None:
                warnings.warn(
                    "`cache_settings=` is deprecated; use `cache=` "
                    "(pass cache=True for defaults, or cache=CacheSettings(...) to tune). "
                    "It will be removed in a future release.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            cache = cache_settings
        if cache is True:
            resolved_cache: CacheSettings[types.T_co] | None = CacheSettings()
        elif cache:  # a CacheSettings instance
            resolved_cache = cache
        else:  # None or False
            resolved_cache = None
```

The `CacheSettings` symbol is defined above `Factory` in the same file — no import needed. Then change the assignment (old line 74) from `self.cache_settings = cache_settings` to:

```python
        self.cache_settings = resolved_cache
```

Leave the rest of `__init__` (the `skip_creator_parsing` branch, `parse_creator`, `super().__init__`, `self._creator`, `self._kwargs`) unchanged.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `just test tests/providers/test_factory.py -k "cache_true or cache_absent or cache_falsy or cache_accepts or deprecated or none_emits or together_raise or repr_reports"`
Expected: PASS (all 9 including the 2 parametrized).

- [ ] **Step 5: Run lint + the full gated suite**

Run: `just lint && just test-ci`
Expected: lint clean; all tests pass at 100% coverage. (Pre-existing `cache_settings=` call-sites still pass — no `filterwarnings=error` is configured — they just emit `DeprecationWarning`, which Task 4 clears.)

- [ ] **Step 6: Commit**

```bash
git add modern_di/providers/factory.py tests/providers/test_factory.py
git commit -m "feat: add Factory(cache=...) toggle and deprecate cache_settings="
```

---

### Task 2: Promote `cache=` into the `architecture/` truth home

**Files:**
- Modify: `architecture/providers.md` (signature block ~lines 35-45; the `## CacheSettings` section ~lines 84-106)
- Modify: `architecture/containers.md` (user-facing `Factory(cache_settings=...)` spelling)

**Interfaces:**
- Consumes: the shipped `Factory(cache=...)` API from Task 1.
- Produces: authoritative capability prose reviewers treat as truth. No code depends on this task.

- [ ] **Step 1: Update the `Factory` signature block in `architecture/providers.md`**

Replace the signature code block (the ```` ```python ```` block starting `Factory(` around lines 35-45) with:

```python
Factory(
    *,
    scope: IntEnum = Scope.APP,
    creator: Callable[..., T],
    bound_type: type | None = UNSET,
    kwargs: dict[str, Any] | None = None,
    cache: bool | CacheSettings[T] | None = None,
    cache_settings: CacheSettings[T] | None = UNSET,  # deprecated alias of `cache`
    skip_creator_parsing: bool = False,
)
```

- [ ] **Step 2: Reframe the `## CacheSettings` section around `cache=`**

In `architecture/providers.md`, replace the `## CacheSettings — singleton behavior` intro (the paragraph and example around lines 84-91) with prose stating: caching is opted into via the `cache` argument — `cache=True` enables it with defaults, `cache=CacheSettings(...)` tunes it (finalizer / `clear_cache`), and absent/`None`/`False` means a fresh instance each resolve. Show:

```python
providers.Factory(scope=Scope.APP, creator=Database, cache=True)
providers.Factory(scope=Scope.APP, creator=Database, cache=providers.CacheSettings(finalizer=close))
```

Then add a short deprecation note: "`cache_settings=` is a deprecated alias of `cache` (it emits a `DeprecationWarning` and will be removed in a future release); passing both raises `TypeError`." Keep the existing `CacheSettings` field table (`clear_cache` / `finalizer` / `is_async_finalizer`) and the "Without caching, `Factory.resolve` calls the creator on every resolution" sentence — rewording the latter to reference "Without `cache`" instead of "Without `cache_settings`". Leave the `Public exports` section (`providers.CacheSettings` still exported) unchanged.

- [ ] **Step 3: Update user-facing spelling in `architecture/containers.md`**

Run `rg -n "cache_settings=" architecture/containers.md`. For each hit that is **user-facing API spelling** (e.g. the "A cached provider (`Factory(cache_settings=...)`)" mention around line 154), change `Factory(cache_settings=...)` to `Factory(cache=...)`. **Do not** change references to the `CacheSettings` type, its `.clear_cache` field, or the internal `.cache_settings` attribute — those names are unchanged.

- [ ] **Step 4: Verify `architecture/resolution.md` needs no change**

Run `rg -n "cache_settings" architecture/resolution.md`. Confirm every hit describes the **internal attribute** `self.cache_settings` or the resolve() algorithm (e.g. `if self.cache_settings and ...`). Because the attribute name is preserved, these stay correct — make no edits. (If any hit is user-facing `Factory(cache_settings=...)` API spelling, update it to `cache=`.)

- [ ] **Step 5: Commit**

```bash
git add architecture/providers.md architecture/containers.md
git commit -m "docs(architecture): promote cache= into the provider truth home"
```

---

### Task 3: Switch `docs/` examples to the `cache=` idiom

**Files (all under `docs/`, verify with the grep in Step 1):**
- Modify: `docs/providers/factories.md`, `docs/providers/lifecycle.md`, `docs/providers/alias.md`, `docs/providers/advanced-api.md`, `docs/index.md`, `docs/introduction/about-di.md`, the integration pages (`docs/integrations/*.md`), the recipes (`docs/recipes/*.md`), the troubleshooting page (`docs/troubleshooting/scope-chain.md`), and the migration guides (`docs/migration/from-that-depends.md`, `docs/migration/to-2.x.md`).

**Interfaces:**
- Consumes: the shipped API and the deprecation contract from Task 1. No code depends on this task.

- [ ] **Step 1: Inventory the call-sites**

Run: `rg -n "cache_settings=" docs/`
Expected: the ~30 doc hits listed in the design's Docs section. Keep this list to verify the sweep at the end.

- [ ] **Step 2: Apply the two mechanical transformations**

For each doc file, apply in this order (empty-parens first, then the general kwarg rename), handling both the `providers.CacheSettings` and bare `CacheSettings` spellings:

1. Bare enable → `cache=True`:
   - `cache_settings=providers.CacheSettings()` → `cache=True`
   - `cache_settings=CacheSettings()` → `cache=True`
2. Tuned (keeps the object, renames only the kwarg):
   - `cache_settings=providers.CacheSettings(` → `cache=providers.CacheSettings(`
   - `cache_settings=CacheSettings(` → `cache=CacheSettings(`

Example transformations:
- `docs/index.md`: `cache_settings=providers.CacheSettings(),  # one Settings for the whole app` → `cache=True,  # cache the singleton for the whole app`
- `docs/recipes/sqlalchemy.md`: `cache_settings=providers.CacheSettings(finalizer=close_engine),` → `cache=providers.CacheSettings(finalizer=close_engine),`
- Migration tables in `docs/migration/from-that-depends.md` (e.g. `| Singleton | providers.Factory(..., cache_settings=CacheSettings()) |`) → `| Singleton | providers.Factory(..., cache=True) |`; the `Resource` row's `cache_settings=CacheSettings(finalizer=...)` → `cache=CacheSettings(finalizer=...)`.

Also update surrounding prose that names the argument (e.g. `about-di.md`'s "the presence of `cache_settings` means one shared instance" → "the presence of `cache` …"; `lifecycle.md`'s "With `cache_settings=CacheSettings()`, the provider returns the same instance" → "With `cache=True`, …"; `factories.md`'s `### cache_settings` heading and its body → `### cache`).

- [ ] **Step 3: Add the deprecation note in `docs/providers/advanced-api.md`**

Add a short subsection (the one place `cache_settings=` is mentioned intentionally):

```markdown
## Deprecated: `cache_settings=`

`Factory(cache_settings=...)` is a deprecated alias of `cache=`. It still works but
emits a `DeprecationWarning`; pass `cache=True` (defaults) or `cache=CacheSettings(...)`
(tuned) instead. Passing both `cache` and `cache_settings` raises `TypeError`.
```

- [ ] **Step 4: Verify the sweep — only intentional mentions remain**

Run: `rg -n "cache_settings=" docs/`
Expected: the **only** remaining hits are intentional prose describing the deprecated alias — the new note in `docs/providers/advanced-api.md`, and any migration-guide sentence explicitly explaining the deprecation. Every code example must now read `cache=`. Fix any stragglers.

- [ ] **Step 5: Verify docs render + lint**

Run: `just lint-ci`
Expected: passes (lint + planning-bundle validation). Manually skim the three highest-traffic pages (`docs/index.md`, `docs/providers/factories.md`, `docs/providers/lifecycle.md`) to confirm the examples read naturally.

- [ ] **Step 6: Commit**

```bash
git add docs/
git commit -m "docs: switch examples to the cache= idiom and note the cache_settings deprecation"
```

---

### Task 4: Dogfood the `cache=` spelling in the test suite

> **Scope note (surface to the maintainer):** This goes one step beyond the design's explicit "Docs (this PR)" scope. It keeps the suite `DeprecationWarning`-free and makes the tests use the API we now recommend. Drop this task if you prefer to keep the PR strictly to the approved scope — the suite passes either way.

**Files:**
- Modify: `tests/providers/test_singleton.py` (22 sites), `tests/test_container.py` (3), `tests/providers/test_factory.py` (existing 4 sites — **not** the Task 1 additions), `tests/providers/test_alias.py` (2), `tests/providers/test_context_provider.py` (1), `tests/test_custom_scope.py` (1)

**Interfaces:**
- Consumes: the shipped API from Task 1. Keeps the Task 1 deprecation tests (`test_cache_settings_is_deprecated_but_functional`, `test_cache_settings_none_emits_no_deprecation_warning`, `test_cache_and_cache_settings_together_raise`) **using `cache_settings=`** — they are the coverage for the deprecated path and must not be migrated.

- [ ] **Step 1: Apply the same two transformations to the test files**

Apply the Task 3 Step 2 transformations to the test files listed above:
- `cache_settings=providers.CacheSettings()` → `cache=True`
- `cache_settings=providers.CacheSettings(` → `cache=providers.CacheSettings(`

**Exclude** the three deprecation tests added in Task 1 — they intentionally exercise `cache_settings=`.

- [ ] **Step 2: Verify only the deprecation tests still use `cache_settings=`**

Run: `rg -n "cache_settings=" tests/`
Expected: hits only inside `test_cache_settings_is_deprecated_but_functional`, `test_cache_settings_none_emits_no_deprecation_warning`, and `test_cache_and_cache_settings_together_raise` in `tests/providers/test_factory.py`. Everything else reads `cache=`.

- [ ] **Step 3: Run the full gated suite**

Run: `just test-ci`
Expected: PASS at 100% coverage. The suite now emits no `DeprecationWarning` from its own provider declarations.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: dogfood the cache= spelling across the suite"
```

---

## Finalize the bundle (before opening the PR)

- [ ] Finalize the `summary:` line in `planning/changes/2026-07-04.01-factory-cache-arg/design.md` to state the realized result.
- [ ] Run `just check-planning` and `just lint-ci` one final time.
- [ ] Push the branch and open a PR (never local-merge); watch CI. Add a `planning/releases/<next-version>.md` note only when cutting the release (separate, tag-driven flow).
