# privatize-container-internals — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Container.scope_map` and `Container.lock` private (`_scope_map` /
`_lock`) behind deprecated property aliases, switching all internal callers to
the private names; update docs and release notes.

**Spec:** [`design.md`](./design.md)

**Branch:** `chore/privatize-container-internals` (already created; holds the spec commit).

**Commit strategy:** Per-task commits.

## Global Constraints

- **Only two attributes are renamed:** `lock`→`_lock`, `scope_map`→`_scope_map`.
  Do **not** touch `find_container`, `parent_container` (attribute or constructor
  kwarg), or `use_lock=`.
- **Backward compatible:** old names remain readable via `@property` that emits
  `DeprecationWarning`. No setters.
- **Warning style matches the existing `cache_settings=` deprecation:**
  `warnings.warn(<msg>, DeprecationWarning, stacklevel=2)`, message ending
  "will be removed in a future release." `warnings` is already imported in
  `modern_di/container.py`.
- **100% line coverage** is gated by `just test-ci` (CI). Targeted runs use
  `just test <path>` (no coverage gate). Lint/type via `just lint-ci`.
- **No `DeprecationWarning` on the resolve hot path** — internal code uses
  `_lock` / `_scope_map` directly.
- Run `just check-planning` before the final push (bundle must stay valid).

---

### Task 1: Rename internals + deprecation shim + tests

**Files:**
- Modify: `modern_di/container.py`
- Modify: `modern_di/providers/factory.py`
- Modify: `tests/test_container.py`

Rename the two slots and every internal caller, add the deprecated property
aliases, update the one existing test that reads `.lock`, and add tests for the
new private attributes + deprecated aliases. This is one atomic change: the
suite is red between the slot rename and the caller updates, so they land in a
single commit.

- [ ] **Step 1: Write the new tests (they fail first)**

  Append to `tests/test_container.py` (`warnings`, `pytest`, `Container`,
  `Group`, `Scope`, `providers` are already imported there; no new imports
  needed). Imports must stay at module level, never inside a function body.

```python
def test_private_lock_and_scope_map_back_the_machinery() -> None:
    root = Container(use_lock=True)
    child = root.build_child_container(scope=Scope.REQUEST)

    # _lock is a reentrant lock (threading.RLock is a factory, not a type, so
    # assert behavior, not isinstance)
    assert root._lock is not None
    assert root._lock.acquire()
    assert root._lock.acquire()  # reentrant
    root._lock.release()
    root._lock.release()
    # child inherits the parent's scope map plus its own scope
    assert set(child._scope_map) == {Scope.APP, Scope.REQUEST}
    assert child._scope_map[Scope.APP] is root


def test_use_lock_false_yields_no_private_lock() -> None:
    root = Container(use_lock=False)
    child = root.build_child_container(scope=Scope.REQUEST)
    assert root._lock is None
    assert child._lock is None


def test_scope_map_alias_warns_and_forwards() -> None:
    container = Container()
    with pytest.warns(DeprecationWarning, match="scope_map"):
        aliased = container.scope_map
    assert aliased is container._scope_map


def test_lock_alias_warns_and_forwards() -> None:
    container = Container(use_lock=True)
    with pytest.warns(DeprecationWarning, match="lock"):
        aliased = container.lock
    assert aliased is container._lock


def test_resolve_emits_no_deprecation_warning() -> None:
    class _Dep:
        pass

    class _Group(Group):
        dep = providers.Factory(scope=Scope.APP, creator=_Dep, cache=True)

    container = Container(groups=[_Group])
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        container.resolve(_Dep)  # touches _lock and _scope_map internally
        container.build_child_container(scope=Scope.REQUEST)
```

- [ ] **Step 2: Run the new tests to confirm they fail**

  Run: `just test tests/test_container.py -k "private_lock_and_scope_map or use_lock_false_yields or scope_map_alias or lock_alias or resolve_emits_no"`
  Expected: FAIL (AttributeError: `_lock`/`_scope_map` don't exist; `.scope_map`/`.lock` don't warn).

- [ ] **Step 3: Rename the slots in `modern_di/container.py`**

  In `__slots__`, change `"lock",` → `"_lock",` and `"scope_map",` → `"_scope_map",`.

- [ ] **Step 4: Update `__init__` and navigation in `container.py`**

  - The line `self.lock = threading.RLock() if use_lock else None` becomes
    `self._lock = threading.RLock() if use_lock else None`.
  - The `scope_map` assignment becomes:
    ```python
    self._scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
        {**parent_container._scope_map, scope: self} if parent_container else {scope: self}
    )
    ```
  - In `build_child_container`, the return line's `use_lock=self.lock is not None`
    becomes `use_lock=self._lock is not None`.
  - In `find_container`, `if scope not in self.scope_map:` → `if scope not in self._scope_map:`
    and `return self.scope_map[scope]` → `return self._scope_map[scope]`.

- [ ] **Step 5: Add the deprecated property aliases in `container.py`**

  Insert immediately after the `find_container` method (before `resolve`):

```python
    @property
    def scope_map(self) -> "dict[enum.IntEnum, typing_extensions.Self]":
        warnings.warn(
            "`Container.scope_map` is private; it will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._scope_map

    @property
    def lock(self) -> "threading.RLock | None":
        warnings.warn(
            "`Container.lock` is private; it will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._lock
```

- [ ] **Step 6: Update the lock gate in `modern_di/providers/factory.py`**

  In `Factory.resolve`, change the four references:
  - `if container.lock:` → `if container._lock:`
  - `container.lock.acquire()` → `container._lock.acquire()`
  - `if container.lock:` → `if container._lock:`
  - `container.lock.release()` → `container._lock.release()`

- [ ] **Step 7: Update the existing test that reads `.lock`**

  In `tests/test_container.py`, `test_build_child_container_propagates_use_lock_false`:
  change `assert root.lock is None` → `assert root._lock is None` and
  `assert child.lock is None` → `assert child._lock is None`.

- [ ] **Step 8: Confirm no stray internal callers remain**

  Run: `grep -rnE "self\.lock\b|self\.scope_map\b|container\.lock\b|container\.scope_map\b" modern_di/`
  Expected: no output — every internal attribute access now uses the underscore
  name. (This pattern deliberately ignores the property `def scope_map`/`def lock`
  and the warning-message strings, which are not attribute reads.) If any hit
  remains, fix it to the private name.

- [ ] **Step 9: Run the full suite with the coverage gate**

  Run: `just test-ci`
  Expected: PASS, 100% line coverage (the two property warning branches are
  covered by the alias tests).

- [ ] **Step 10: Lint / type check**

  Run: `just lint-ci`
  Expected: clean (`ruff`, `ty`, planning validation).

- [ ] **Step 11: Commit**

  ```bash
  git add modern_di/container.py modern_di/providers/factory.py tests/test_container.py
  git commit -m "chore: privatize Container.scope_map/lock behind deprecated aliases"
  ```

---

### Task 2: Docs — extension point vs internals

**Files:**
- Modify: `docs/providers/advanced-api.md`
- Modify: `architecture/containers.md`

Promote `find_container` to a supported extension point, and update the internals
section for the renamed attributes.

- [ ] **Step 1: `advanced-api.md` — move `find_container` to extension points**

  Move the `find_container(scope)` bullet out of the
  `## Container internals — no stability guarantee` section and into
  `## Supported extension points` as its own `### find_container(scope)`
  subsection. Keep the existing description text, and add one sentence framing it
  as the primitive a custom `AbstractProvider.resolve` calls to locate the
  container at its scope. Cross-reference the "Subclassing `AbstractProvider`"
  subsection.

- [ ] **Step 2: `advanced-api.md` — update the internals bullets**

  In `## Container internals — no stability guarantee`, rename the bullets:
  - `**`scope_map`**` → `**`_scope_map`**` (keep the description).
  - `**`lock`**` → `**`_lock`**` (keep the description).
  Add one line after the two bullets: "The former public names `scope_map` and
  `lock` remain as read-only properties that emit `DeprecationWarning` and will
  be removed in a future release." Leave the `parent_container` bullet unchanged.

- [ ] **Step 3: `architecture/containers.md` — update the scope_map mention**

  Lines ~47-48 describe the child's `scope_map` dict and
  `find_container(scope)`. Change `scope_map` → `_scope_map` in that prose
  (the attribute is now private); `find_container(scope)` stays as written (it
  is public). Keep the meaning identical.

- [ ] **Step 4: Build the docs**

  Run: `just docs-build`
  Expected: success (mkdocs `--strict`).

- [ ] **Step 5: Commit**

  ```bash
  git add docs/providers/advanced-api.md architecture/containers.md
  git commit -m "docs: find_container is an extension point; _scope_map/_lock are internal"
  ```

---

### Task 3: Release notes

**Files:**
- Create: `planning/releases/2.22.0.md`

Pre-stage the deprecation entry. `2.22.0` is the next minor (a deprecation is
additive/back-compatible); the maintainer may adjust the version at tag time.

- [ ] **Step 1: Write the release notes**

  Create `planning/releases/2.22.0.md`, mirroring the house style of
  `planning/releases/2.21.0.md`:

```markdown
# modern-di 2.22.0 — private `Container` internals

Back-compatible. Two `Container` attributes become private, with deprecated aliases; one member is reclassified as a supported extension point.

## Deprecation

- **`Container.scope_map` and `Container.lock` are now private** (`_scope_map` / `_lock`). Reading the old names still works but emits `DeprecationWarning` and will be removed in a future release. These attributes were already documented "internal, no stability guarantee"; the thread-safety knob `use_lock=` and the `Container(...)` constructor are unchanged.

## Clarification

- **`find_container(scope)` is a supported extension point.** It is the primitive a custom `AbstractProvider.resolve` calls to locate the container at its scope, and is now documented as such (moved out of the internals section).

## Downstream

No action required. Nothing in the official integrations reads `scope_map` or `lock`. Advanced users who inspected them should switch to `_scope_map` / `_lock` (or, for scope lookup, `find_container`).

## Internals

- 100% line coverage maintained across Python 3.10–3.14; `ruff` and `ty` clean.
```

- [ ] **Step 2: Validate the bundle and commit**

  Run: `just check-planning`  (Expected: `planning: OK`)
  ```bash
  git add planning/releases/2.22.0.md
  git commit -m "docs: release notes for 2.22.0 (private Container internals)"
  ```

---

### Task 4: Final validation, push, PR

**Files:** none (validation only).

- [ ] **Step 1: Full gates**

  ```bash
  just test-ci      # Expected: PASS, 100% coverage
  just lint-ci      # Expected: clean
  just docs-build   # Expected: success
  just check-planning  # Expected: planning: OK
  ```

- [ ] **Step 2: Finalize the bundle summary**

  Confirm `design.md`'s `summary:` still matches the shipped result; edit if the
  scope shifted. Commit any change:
  ```bash
  git add planning/changes/2026-07-05.02-privatize-container-internals/design.md
  git commit -m "docs: finalize privatize-container-internals bundle summary" || true
  ```

- [ ] **Step 3: Push and open the PR**

  ```bash
  git push -u origin chore/privatize-container-internals
  gh pr create --fill --title "chore: privatize Container scope_map/lock internals"
  ```
  Then watch CI (lint, pytest 3.10–3.14, docs) until green.
