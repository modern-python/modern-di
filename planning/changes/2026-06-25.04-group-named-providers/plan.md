# group-named-providers — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `Group.get_named_providers()` (name→provider dict) and
reimplement `get_providers()` on top of it, so the MRO traversal and
dedup/masking semantics live in one place.

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/group-named-providers`

**Commit strategy:** Per-task commits.

## Global Constraints

- Run tests via `just test [args]` and the gate via `just test-ci` (100% line
  coverage) — never call `pytest` directly.
- Lint via `just lint` (autofix) / `just lint-ci` (CI check).
- Type suppression, if ever needed, is `# ty: ignore` — none expected here.
- All imports at module level.
- Annotate test function arguments (these tests take none).
- A behavior change to `Group` must promote into `architecture/providers.md`
  **in this same PR** (Task 4).
- `just check-planning` must pass before pushing.

---

### Task 1: Add `get_named_providers()` with its behavior tests

**Files:**
- Modify: `modern_di/group.py`
- Test: `tests/test_group.py`

**Interfaces:**
- Produces: `Group.get_named_providers() -> dict[str, AbstractProvider[typing.Any]]`
  — classmethod returning the MRO-collected providers keyed by declared
  attribute name; first-seen name wins; a non-provider override masks the
  parent provider (name absent from the dict); dict order matches MRO order
  (most-derived first).

Add the name-preserving accessor and pin its semantics test-first. The
existing module-level dataclasses `_A`, `_B` in `tests/test_group.py` are
reused.

- [ ] **Step 1: Write the failing tests**

  Append to `tests/test_group.py`:

  ```python
  def test_get_named_providers_maps_each_provider_to_its_attribute_name() -> None:
      class Base(Group):
          a = providers.Factory(creator=_A)

      class Child(Base):
          b = providers.Factory(creator=_B)

      assert Child.get_named_providers() == {"a": Base.a, "b": Child.b}


  def test_get_named_providers_masks_non_provider_override() -> None:
      class Base(Group):
          a = providers.Factory(creator=_A)

      class Child(Base):
          a = "not a provider"

      assert Child.get_named_providers() == {}


  def test_get_named_providers_diamond_keeps_single_named_entry() -> None:
      class Base(Group):
          a = providers.Factory(creator=_A)

      class Left(Base): ...

      class Right(Base): ...

      class Diamond(Left, Right): ...

      assert Diamond.get_named_providers() == {"a": Base.a}
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  Run: `just test tests/test_group.py -k get_named_providers -v`
  Expected: FAIL — `AttributeError: type object 'Child' has no attribute 'get_named_providers'`.

- [ ] **Step 3: Implement `get_named_providers()`**

  In `modern_di/group.py`, add the classmethod to `Group` (above
  `get_providers`):

  ```python
  @classmethod
  def get_named_providers(cls) -> dict[str, AbstractProvider[typing.Any]]:
      seen_names: set[str] = set()
      collected: dict[str, AbstractProvider[typing.Any]] = {}
      for klass in cls.__mro__:
          if klass is Group or klass is object:
              continue
          for name, value in klass.__dict__.items():
              if name in seen_names:
                  continue
              seen_names.add(name)
              if isinstance(value, AbstractProvider):
                  collected[name] = value
      return collected
  ```

- [ ] **Step 4: Run the tests to verify they pass**

  Run: `just test tests/test_group.py -k get_named_providers -v`
  Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

  ```bash
  git add modern_di/group.py tests/test_group.py
  git commit -m "feat: add Group.get_named_providers()"
  ```

---

### Task 2: Reimplement `get_providers()` on top of `get_named_providers()`

**Files:**
- Modify: `modern_di/group.py`
- Test: `tests/test_group.py`

**Interfaces:**
- Consumes: `Group.get_named_providers()` from Task 1.
- Produces: `Group.get_providers()` unchanged in contract — returns
  `list(cls.get_named_providers().values())`.

Collapse the duplicated MRO traversal so dedup/masking live in one place,
proven behavior-neutral by the existing `get_providers` tests plus a new
consistency test.

- [ ] **Step 1: Write the failing consistency test**

  Append to `tests/test_group.py`:

  ```python
  def test_get_providers_matches_named_provider_values() -> None:
      class Base(Group):
          a = providers.Factory(creator=_A)

      class Child(Base):
          b = providers.Factory(creator=_B)

      assert Child.get_providers() == list(Child.get_named_providers().values())
  ```

- [ ] **Step 2: Run the test to verify it passes (already consistent) — then proceed to refactor**

  Run: `just test tests/test_group.py -k get_providers_matches -v`
  Expected: PASS — the old and new implementations already agree; this test
  guards the refactor in Step 3 against drift.

- [ ] **Step 3: Replace the `get_providers()` body**

  In `modern_di/group.py`, replace the existing `get_providers` method body
  with the one-line adapter:

  ```python
  @classmethod
  def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
      return list(cls.get_named_providers().values())
  ```

- [ ] **Step 4: Run the full group suite to verify behavior is unchanged**

  Run: `just test tests/test_group.py -v`
  Expected: PASS — all existing `get_providers` tests (inheritance, override,
  diamond, masking) plus the new tests stay green.

- [ ] **Step 5: Commit**

  ```bash
  git add modern_di/group.py tests/test_group.py
  git commit -m "refactor: derive get_providers from get_named_providers"
  ```

---

### Task 3: Verify the full coverage gate

**Files:** none (verification only).

Confirm the new method and the reimplementation hit 100% line coverage and the
whole suite is green before touching docs.

- [ ] **Step 1: Run the gated suite**

  Run: `just test-ci`
  Expected: PASS — 100% line coverage, no `term-missing` lines in
  `modern_di/group.py`.

- [ ] **Step 2: If any `group.py` line is uncovered, add a targeted test**

  Only if coverage flags a line: add the minimal test to `tests/test_group.py`
  that exercises it, re-run `just test-ci`, and fold it into the Task 2 commit
  with `git commit --amend --no-edit` (no new commit for a coverage top-up).

---

### Task 4: Promote into `architecture/providers.md`

**Files:**
- Modify: `architecture/providers.md`

CLAUDE.md mandates the capability doc move in the same PR as the behavior
change. Document the new accessor and that `get_providers()` is derived.

- [ ] **Step 1: Update the `Group` section**

  In `architecture/providers.md`, replace the sentence (around line 22):

  ```markdown
  `Group.get_providers()` walks the MRO and collects every class attribute that is an `AbstractProvider` instance,
  respecting inheritance order and de-duplicating by name.
  ```

  with:

  ```markdown
  `Group.get_named_providers()` walks the MRO and returns a `dict[str, AbstractProvider]` mapping each declared
  attribute name to its provider — respecting inheritance order, de-duplicating by first-seen name, and letting a
  non-provider override mask the parent provider of the same name. `Group.get_providers()` is derived from it as
  `list(cls.get_named_providers().values())`, so the traversal and de-duplication rules live in one place.
  ```

- [ ] **Step 2: Verify docs build**

  Run: `just docs-build`
  Expected: PASS — no broken links / nav warnings.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/providers.md
  git commit -m "docs: document Group.get_named_providers in providers catalog"
  ```

---

### Task 5: Finalize the planning bundle and full CI check

**Files:**
- Modify: `planning/changes/2026-06-25.04-group-named-providers/design.md` (only if the realized result differs from the written summary).

Confirm the bundle validates and the full non-fixing CI gate passes, then open
the PR.

- [ ] **Step 1: Confirm the bundle summary still states the realized result**

  The `summary:` in `design.md` already describes the shipped behavior; edit
  only if implementation diverged. No folder move, no post-merge bookkeeping.

- [ ] **Step 2: Run the planning validator**

  Run: `just check-planning`
  Expected: PASS — bundle frontmatter valid.

- [ ] **Step 3: Run the full non-fixing CI gate**

  Run: `just lint-ci && just test-ci`
  Expected: PASS — lint clean, 100% coverage, planning index valid.

- [ ] **Step 4: Push and open the PR**

  ```bash
  git push -u origin feat/group-named-providers
  gh pr create --fill
  ```

  Watch CI after pushing. Once merged to green main, cut tag `2.20.0` to
  publish to PyPI — that release unblocks the downstream
  `modern-di-litestar` PR.

---

## Self-review notes

- **Spec coverage:** `get_named_providers()` (Task 1), `get_providers()`
  reimplementation (Task 2), coverage gate (Task 3), `architecture/` promotion
  (Task 4), bundle finalize + CI + release pointer (Task 5). All design
  sections mapped.
- **Type consistency:** `get_named_providers` returns
  `dict[str, AbstractProvider[typing.Any]]` everywhere; `get_providers`
  returns `list[AbstractProvider[typing.Any]]` (unchanged). Generic param
  matches `AbstractProvider`'s existing `typing.Any` usage in this file.
- **No placeholders:** every code and command step is concrete.
