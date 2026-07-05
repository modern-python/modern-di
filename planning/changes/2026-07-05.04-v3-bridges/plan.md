# v3-bridges — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 2.x bridges for the ruled 3.0 breaks: reworked validation
error rendering, tri-state `validate` FutureWarning, ContextProvider
unset-value DeprecationWarning, and the to-3.x migration guide.

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/v3-bridges`

**Commit strategy:** Per-task commits.

**Global constraints:** zero dependencies (stdlib only); sync-only resolution;
no global state; line length 120; `ruff` `select = ["ALL"]`; `ty` (use
`ty: ignore`, never `type: ignore`); module-level imports only; annotate all
function arguments; 100% line coverage gate (`just test-ci`); error messages
are inline f-strings in the class that raises them; `asyncio_mode = "auto"`.

---

### Task 1: CircularDependencyError arrow-chain rendering

**Files:**
- Modify: `modern_di/exceptions.py:256-260` (`CircularDependencyError.__init__`)
- Test: `tests/test_error_rendering.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `CircularDependencyError` message is now multi-line
  (`cycle_path` attribute unchanged, still `list[str]`). Task 2's grouped
  rendering indents these continuation lines.

- [ ] **Step 1: Write the failing test**

Create `tests/test_error_rendering.py`:

```python
from modern_di import exceptions


def test_circular_dependency_error_renders_cycle_as_arrow_chain() -> None:
    error = exceptions.CircularDependencyError(cycle_path=["A", "B", "A"])
    assert error.cycle_path == ["A", "B", "A"]
    assert str(error) == (
        "Circular dependency detected:\n"
        "  A\n"
        "  └─> B\n"
        "      └─> A\n"
        "Check your provider graph for unintended cycles."
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_error_rendering.py -v`
Expected: FAIL — current message is the inline
`Circular dependency detected: A -> B -> A. ...` form.

- [ ] **Step 3: Implement the rendering**

In `modern_di/exceptions.py`, replace `CircularDependencyError.__init__`
(currently builds the inline `' -> '.join(cycle_path)` message) with:

```python
    def __init__(self, *, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        rendered = "\n".join(
            f"  {'    ' * (i - 1)}└─> {name}" if i else f"  {name}" for i, name in enumerate(cycle_path)
        )
        super().__init__(f"Circular dependency detected:\n{rendered}\nCheck your provider graph for unintended cycles.")
```

(The `└─>` continuation style matches `ResolutionError.__str__`'s breadcrumb
rendering at `exceptions.py:155-166`.)

- [ ] **Step 4: Run the new test, then the whole suite**

Run: `just test tests/test_error_rendering.py -v` → PASS.
Run: `just test` → any test asserting the old one-line format fails; find
them with `grep -rn "Circular dependency detected" tests/` (expect hits in
`tests/test_container.py`, `tests/providers/test_alias.py`) and update those
assertions to match the new multi-line message (assert on
`"Circular dependency detected:"` plus the relevant `└─>` line rather than
the full string where the cycle names are the point).
Run: `just test` again → PASS.

- [ ] **Step 5: Commit**

```bash
git add modern_di/exceptions.py tests/
git commit -m "feat: render CircularDependencyError cycle path as an arrow chain (ERR-5)"
```

---

### Task 2: ValidationFailedError grouped rendering

**Files:**
- Modify: `modern_di/exceptions.py:364-367` (`ValidationFailedError.__str__`)
- Test: `tests/test_error_rendering.py` (extend)

**Interfaces:**
- Consumes: Task 1's multi-line `CircularDependencyError` message.
- Produces: grouped `ValidationFailedError` rendering; `.errors` list and the
  one-line header (`Container.validate() found N issue(s): <kinds>`) keep
  their current content.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_error_rendering.py`:

```python
def test_validation_failed_error_groups_by_kind_and_indents_multiline() -> None:
    cycle = exceptions.CircularDependencyError(cycle_path=["A", "B", "A"])
    error = exceptions.ValidationFailedError(errors=[RuntimeError("boom"), cycle])
    assert error.errors == [RuntimeError("boom"), cycle] or len(error.errors) == 2  # list preserved
    assert str(error) == (
        "Container.validate() found 2 issue(s): CircularDependencyError, RuntimeError\n"
        "\n"
        "CircularDependencyError (1):\n"
        "  - Circular dependency detected:\n"
        "      A\n"
        "      └─> B\n"
        "          └─> A\n"
        "    Check your provider graph for unintended cycles.\n"
        "\n"
        "RuntimeError (1):\n"
        "  - boom"
    )
```

(First line of each sub-error gets `  - `; its continuation lines get four
spaces, so multi-line messages — cycles, "Did you mean" blocks — stay aligned
instead of being mangled by the old flat `  - {e}` join.)

- [ ] **Step 2: Run test to verify it fails**

Run: `just test tests/test_error_rendering.py -v`
Expected: the new test FAILS against the current flat rendering.

- [ ] **Step 3: Implement the rendering**

Replace `ValidationFailedError.__str__` (keep `__init__` untouched):

```python
    def __str__(self) -> str:
        lines = [super().__str__()]
        by_kind: dict[str, list[Exception]] = {}
        for error in self.errors:
            by_kind.setdefault(type(error).__name__, []).append(error)
        for kind in sorted(by_kind):
            errors = by_kind[kind]
            lines.append(f"\n{kind} ({len(errors)}):")
            for error in errors:
                first, *rest = str(error).splitlines()
                lines.append(f"  - {first}")
                lines.extend(f"    {line}" for line in rest)
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `just test tests/test_error_rendering.py -v` → PASS.
Run: `just test` → update any assertion on the old flat format (grep
`"found "` / `"issue(s)"` in `tests/`); full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add modern_di/exceptions.py tests/
git commit -m "feat: group ValidationFailedError report by error kind (ERR-5)"
```

---

### Task 3: Tri-state `validate` + UnvalidatedContainerWarning

**Files:**
- Modify: `modern_di/exceptions.py` (new warning class after
  `ContainerClosedWarning`, `exceptions.py:125-135`)
- Modify: `modern_di/container.py:42-93` (`Container.__init__` signature and
  tail)
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`, after
  `asyncio_mode`, line ~77)
- Test: `tests/test_container.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `exceptions.UnvalidatedContainerWarning(FutureWarning)`;
  `Container.__init__(..., validate: bool | None = None)`. Task 5's docs and
  Task 6's architecture promotion reference both.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_container.py` (it already imports `Container`, `Scope`,
`exceptions`, `pytest`, `warnings` — add any missing import at module level):

```python
def test_root_container_without_validate_arg_warns_about_3_0_default() -> None:
    with pytest.warns(exceptions.UnvalidatedContainerWarning, match="modern-di 3.0 runs validate"):
        Container(scope=Scope.APP)


def test_explicit_validate_false_never_warns() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Container(scope=Scope.APP, validate=False)


def test_explicit_validate_true_validates_and_never_warns() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Container(scope=Scope.APP, validate=True)


def test_child_container_does_not_warn_about_validate() -> None:
    root = Container(scope=Scope.APP, validate=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        root.build_child_container(scope=Scope.REQUEST)


def test_unvalidated_container_warning_is_escalatable() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)
        with pytest.raises(exceptions.UnvalidatedContainerWarning):
            Container(scope=Scope.APP)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/test_container.py -k "validate_arg or never_warns or does_not_warn_about_validate or escalatable" -v`
Expected: FAIL — `UnvalidatedContainerWarning` does not exist.

- [ ] **Step 3: Add the warning class**

In `modern_di/exceptions.py`, directly after `ContainerClosedWarning`
(mirroring its docstring shape):

```python
class UnvalidatedContainerWarning(FutureWarning):
    """A root container was built without an explicit ``validate`` argument — transitional.

    modern-di 3.0 runs :meth:`Container.validate` at root construction by
    default. Pass ``validate=True`` to adopt the 3.0 behavior now, or
    ``validate=False`` to keep validation off (also after 3.0). Opt into strict
    behavior early by escalating this warning::

        warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)
    """
```

- [ ] **Step 4: Make `validate` tri-state**

In `modern_di/container.py` change the `__init__` parameter
`validate: bool = False` to `validate: bool | None = None`, and replace the
tail `if validate: self.validate()` with:

```python
        if validate:
            self.validate()
        elif validate is None and parent_container is None:
            warnings.warn(
                "This root container was created without an explicit `validate` argument. "
                "modern-di 3.0 runs validate() at root construction by default. Pass validate=True "
                "to adopt the 3.0 behavior now, or validate=False to keep validation off. "
                "See https://modern-di.modern-python.org/migration/to-3.x/.",
                exceptions.UnvalidatedContainerWarning,
                stacklevel=2,
            )
```

Update the `__init__` docstring's `validate` sentence to describe the
tri-state (unset warns on roots; explicit `False` opts out silently).

- [ ] **Step 5: Silence the warning for the repo's own suite**

In `pyproject.toml` under `[tool.pytest.ini_options]` (after
`asyncio_mode = "auto"`):

```toml
filterwarnings = [
    "ignore::modern_di.exceptions.UnvalidatedContainerWarning",
]
```

(166 root constructions in tests would otherwise warn; targeted tests above
override this via `pytest.warns` / `catch_warnings`.)

- [ ] **Step 6: Run tests**

Run: `just test tests/test_container.py -v` → PASS, then `just test` → full
suite PASS with no warning spam in the summary.

- [ ] **Step 7: Commit**

```bash
git add modern_di/exceptions.py modern_di/container.py pyproject.toml tests/test_container.py
git commit -m "feat: tri-state validate= with UnvalidatedContainerWarning ahead of the 3.0 default flip (API-1 bridge)"
```

---

### Task 4: ContextProvider unset-value deprecation pair

**Files:**
- Modify: `modern_di/exceptions.py` (two new classes after
  `CircularDependencyError`, `exceptions.py:251-260`)
- Modify: `modern_di/providers/context_provider.py:42-46` (`resolve`)
- Test: `tests/providers/test_context_provider.py` (extend + update existing)
- Test: `tests/test_error_rendering.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `exceptions.ContextValueNotSetError(ResolutionError)` (unraised in
  2.x; the cut-3.0 bundle raises it) and
  `exceptions.ContextValueNoneWarning(DeprecationWarning)`. Task 5's docs
  reference both.

- [ ] **Step 1: Write the failing tests**

Append to `tests/providers/test_context_provider.py` (module defines groups
with an unset `context_provider`; reuse its existing fixtures/idioms):

```python
def test_unset_context_provider_direct_resolve_warns_and_returns_none() -> None:
    app_container = Container(groups=[MyGroup], validate=False)
    with pytest.warns(exceptions.ContextValueNoneWarning, match="modern-di 3.0 raises ContextValueNotSetError"):
        assert app_container.resolve_provider(MyGroup.context_provider) is None


def test_set_context_provider_direct_resolve_does_not_warn() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container(groups=[MyGroup], context={datetime.datetime: now}, validate=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert app_container.resolve_provider(MyGroup.context_provider) is now
```

(The module already defines `MyGroup` with
`context_provider = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)`;
it currently imports exception classes directly from `modern_di.exceptions` —
add `warnings` and the new names as module-level imports in the file's
existing style. `test_context_provider_not_found` at line 40 is one of the
existing assertions Step 5 wraps in `pytest.warns`.)

Append to `tests/test_error_rendering.py`:

```python
def test_context_value_not_set_error_message_and_hierarchy() -> None:
    error = exceptions.ContextValueNotSetError(context_type=str, scope_name="APP")
    assert isinstance(error, exceptions.ResolutionError)
    assert str(error) == (
        "No context value is set for <class 'str'> (scope APP). "
        "Pass context={...} to the container or call set_context()."
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test tests/providers/test_context_provider.py tests/test_error_rendering.py -v`
Expected: FAIL — neither class exists.

- [ ] **Step 3: Add the exception + warning pair**

In `modern_di/exceptions.py`, after `CircularDependencyError` (mirroring the
`ContainerClosedError`/`ContainerClosedWarning` pair at 100-135):

```python
class ContextValueNotSetError(ResolutionError):
    """An unset ``ContextProvider`` was resolved directly.

    Raised in modern-di 3.0; until then direct resolve emits
    :class:`ContextValueNoneWarning` and returns ``None``. Inspect
    ``.context_type``.
    """

    __slots__ = ("context_type",)

    def __init__(self, *, context_type: type, scope_name: str) -> None:
        self.context_type = context_type
        super().__init__(
            f"No context value is set for {context_type!r} (scope {scope_name}). "
            "Pass context={...} to the container or call set_context()."
        )


class ContextValueNoneWarning(DeprecationWarning):
    """Direct resolve of an unset ``ContextProvider`` returned ``None`` — transitional.

    The ``None`` return works today but modern-di 3.0 raises
    :class:`ContextValueNotSetError` here. Opt into strict behavior now by
    escalating this warning::

        warnings.filterwarnings("error", category=exceptions.ContextValueNoneWarning)
    """
```

- [ ] **Step 4: Emit the warning in `ContextProvider.resolve`**

In `modern_di/providers/context_provider.py` (add `import warnings` and
`from modern_di import exceptions` at module level; keep imports sorted):

```python
    def resolve(self, container: "Container") -> types.T_co | None:
        value = self.fetch_context_value(container)
        if value is types.UNSET:
            warnings.warn(
                f"No context value is set for {self.context_type!r} (scope {self.scope.name}); returning None. "
                "modern-di 3.0 raises ContextValueNotSetError here. Pass context={...} to the container or call "
                "set_context(). See https://modern-di.modern-python.org/migration/to-3.x/.",
                exceptions.ContextValueNoneWarning,
                stacklevel=2,
            )
            return None
        return typing.cast(types.T_co, value)
```

Also update the class docstring's "Resolving it directly when no value is set
returns ``None``" sentence to mention the warning and the 3.0 error.

- [ ] **Step 5: Update existing unset-direct-resolve tests**

`grep -n "is None" tests/providers/test_context_provider.py` — the existing
direct-resolve assertions (lines 42 and 174 today) now warn; wrap each in
`pytest.warns(exceptions.ContextValueNoneWarning)`. Dependent-parameter tests
(`.ctx is None`, `.value is None` via Factory params) must stay green
**unmodified** — they go through `fetch_context_value`, not `resolve`; if any
of them starts warning, the implementation is wrong (fix the code, not the
test).

- [ ] **Step 6: Run tests**

Run: `just test tests/providers/test_context_provider.py tests/test_error_rendering.py -v` → PASS.
Run: `just test` → full suite PASS.

- [ ] **Step 7: Commit**

```bash
git add modern_di/exceptions.py modern_di/providers/context_provider.py tests/
git commit -m "feat: warn on direct resolve of an unset ContextProvider ahead of the 3.0 raise (API-6 bridge)"
```

---

### Task 5: to-3.x migration guide + docs updates

**Files:**
- Create: `docs/migration/to-3.x.md`
- Modify: `mkdocs.yml:48` (nav — add `To 3.x` after `To 2.x`)
- Modify: `docs/providers/errors-and-exceptions.md` (add the three new
  classes where the hierarchy/warnings are enumerated)

**Interfaces:**
- Consumes: warning/error names and messages from Tasks 3-4 exactly as
  implemented (re-read the source, do not trust this plan's copies).
- Produces: the page the warning messages link to
  (`https://modern-di.modern-python.org/migration/to-3.x/`).

- [ ] **Step 1: Write `docs/migration/to-3.x.md`**

Follow the voice/structure of `docs/migration/to-2.x.md`. Required content:

1. Intro: 3.0 flips five switches; every one has a 2.x signal; a green 2.x
   suite with the recipe below guarantees a clean upgrade.
2. The switch table:

   | 3.0 change | 2.x signal |
   |---|---|
   | Reusing a closed container raises `ContainerClosedError` | `ContainerClosedWarning` |
   | `Alias(scope=)` parameter removed | `DeprecationWarning` |
   | `Factory(cache_settings=)` removed | `DeprecationWarning` |
   | `validate()` runs by default at root construction | `UnvalidatedContainerWarning` |
   | Direct resolve of an unset `ContextProvider` raises `ContextValueNotSetError` | `ContextValueNoneWarning` |

3. One section per switch with a before/after code pair (source the exact 2.x
   spellings from `architecture/containers.md`, `architecture/providers.md`,
   and the warning messages in code).
4. Readiness recipe — because `ContainerClosedWarning` and
   `ContextValueNoneWarning` subclass `DeprecationWarning` and
   `UnvalidatedContainerWarning` subclasses `FutureWarning`, two lines cover
   all five signals:

   ```python
   import warnings

   warnings.filterwarnings("error", category=DeprecationWarning, module=r"modern_di(\..*)?")
   warnings.filterwarnings("error", category=FutureWarning, module=r"modern_di(\..*)?")
   ```

   plus the pytest variant:

   ```toml
   [tool.pytest.ini_options]
   filterwarnings = [
       "error::DeprecationWarning",
       "error::FutureWarning",
   ]
   ```

   **Verify the `module=` regex actually matches** (the `module` filter arg
   matches the *triggering* frame's `__name__` under `stacklevel`, which for
   `stacklevel=2` is the caller, not `modern_di`) — write a 5-line scratch
   script; if it does not match, drop `module=` from the recipe and present
   the per-category escalation instead.
5. Deprecation policy paragraph: warn at least one minor cycle, flip/remove at
   the major.

- [ ] **Step 2: Add the nav entry**

In `mkdocs.yml` after `- To 2.x: migration/to-2.x.md`:

```yaml
      - To 3.x: migration/to-3.x.md
```

- [ ] **Step 3: Update the exceptions docs page**

In `docs/providers/errors-and-exceptions.md`, add
`UnvalidatedContainerWarning`, `ContextValueNoneWarning`, and
`ContextValueNotSetError` wherever `ContainerClosedWarning` /
`ContainerClosedError` are listed, matching the page's existing format.

- [ ] **Step 4: Build docs strictly and run gates**

Run: `just docs 2>&1 | tail -5` (or the docs recipe `just --list` shows; CI
builds with `mkdocs --strict`) — no broken links/anchors.
Run: `just lint-ci` → PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/ mkdocs.yml
git commit -m "docs: add to-3.x migration guide covering all five 3.0 switches (DOC-1)"
```

---

### Task 6: Architecture promotion + gates

**Files:**
- Modify: `architecture/validation.md` (rendering rework; 3.0 default-on note)
- Modify: `architecture/containers.md` (tri-state `validate` row + warning)
- Modify: `architecture/providers.md` (ContextProvider warning + 3.0 error)
- Modify: `planning/changes/2026-07-05.04-v3-bridges/design.md` (finalize
  `summary:` to the realized result)

**Interfaces:**
- Consumes: everything shipped in Tasks 1-5 (read the merged source, not this
  plan).

- [ ] **Step 1: Promote to architecture/**

Update the three capability files to describe the shipped behavior:
`containers.md` constructor table (`validate` default `None`, unset-root
warning, explicit `False` opt-out); `validation.md` (grouped report format
with a rendered example, arrow-chain cycles, the pending 3.0 default flip);
`providers.md` ContextProvider section (warning on unset direct resolve, the
3.0 `ContextValueNotSetError`, dependent-parameter dispositions unchanged).

- [ ] **Step 2: Finalize the bundle summary**

Rewrite `design.md`'s `summary:` line to state the realized result.

- [ ] **Step 3: Run all gates**

Run: `just test-ci` → PASS at 100% coverage (new warning/error lines covered).
Run: `just lint-ci` → PASS.
Run: `just check-planning` → OK.

- [ ] **Step 4: Commit**

```bash
git add architecture/ planning/
git commit -m "docs: promote v3-bridges behavior into architecture/ capability files"
```
