# Docs UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 16 Medium findings from the 2026-06-13 Docs UX audit — runnable examples, accuracy corrections, missing cross-links/sections, one nav split.

**Architecture:** Documentation-only edits across `README.md`, `docs/**`, and `architecture/**`. No `modern_di/` code changes. Each task is independently verifiable: runnable snippets are executed; rendering/links are checked with `mkdocs build --strict`.

**Tech Stack:** Markdown, MkDocs + Material, Python (for verifying example snippets via `uv run python`).

**Source of truth:** `planning/audits/2026-06-13-docs-ux-audit-report.md` — each task cites its finding ID(s); read the full finding for context.

**One-time setup for the executor:** ensure docs deps are importable for the strict-build verification used by several tasks:

```bash
uv run python -c "import material" 2>/dev/null || uv pip install mkdocs mkdocs-material
uv run mkdocs build --strict   # baseline: should currently build (it may already PASS)
```

If `--strict` fails on pre-existing warnings unrelated to a task, note it and fall back to a plain `mkdocs build` plus manual HTML inspection for that task.

---

### Task 1: README — add Install + minimal runnable Quick Start (O-1 / R-1)

**Files:**
- Modify: `README.md` (insert after the feature bullet list, before the "Usage examples:" block at line 28)

- [ ] **Step 1: Add an Install section and a self-contained Quick Start**

Insert this block immediately after line 26 (the pytest bullet), before line 28 (`Usage examples:`):

````markdown
## Install

```bash
uv add modern-di      # or: pip install modern-di
```

## Quick Start

```python
import dataclasses
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"


@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    settings: Settings  # auto-injected by type


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)
    user_repository = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)


with Container(groups=[Dependencies], validate=True) as container:
    with container.build_child_container(scope=Scope.REQUEST) as request:
        repo = request.resolve(UserRepository)
        print(repo.settings.database_url)
```

See the [documentation](https://modern-di.modern-python.org) for scopes, lifecycles, finalizers, and framework integrations.
````

- [ ] **Step 2: Verify the snippet runs**

Extract the Python block to a temp file and run it:

```bash
uv run python - <<'PY'
import dataclasses
from modern_di import Container, Group, Scope, providers

@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"

@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    settings: Settings

class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)
    user_repository = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)

with Container(groups=[Dependencies], validate=True) as container:
    with container.build_child_container(scope=Scope.REQUEST) as request:
        repo = request.resolve(UserRepository)
        print(repo.settings.database_url)
PY
```

Expected: prints `postgresql+asyncpg://localhost/app`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): add install + runnable Quick Start (audit O-1/R-1)"
```

---

### Task 2: index.md — lead the Quickstart with a runnable sync example (O-2)

**Files:**
- Modify: `docs/index.md` (section `## 4.2. Or use modern-di directly`, lines 101-120)

**Context:** the current first end-to-end example is `async def main()` / `async with`, never calls `asyncio.run(main())`, and does no async work (resolution is sync-only). Copy-pasting it silently no-ops.

- [ ] **Step 1: Replace the async example with a sync-first version**

Replace lines 103-120 (the ` ```python … ``` ` block) with:

````markdown
```python
from modern_di import Container, Scope


# Pass validate=True to detect cycles and scope-chain errors at startup
with Container(groups=[Dependencies], validate=True) as container:
    # APP-scoped providers resolve straight from the container
    settings = container.resolve(Settings)

    # REQUEST-scoped providers need a REQUEST child container
    with container.build_child_container(scope=Scope.REQUEST) as request:
        repo = request.resolve(UserRepository)
        user = repo.find(42)

    # Request-scope finalizers ran on `with` exit
# App-scope finalizers ran on the outer `with` exit
```

Resolution is always synchronous. Use `async with` (on both the container and
the child) only when a provider registers an **async** finalizer — see
[Lifecycle](providers/lifecycle.md).
````

- [ ] **Step 2: Verify the new example runs (with the page's earlier definitions)**

```bash
uv run python - <<'PY'
import dataclasses
from modern_di import Container, Group, Scope, providers

@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"

@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    settings: Settings
    def find(self, user_id: int) -> dict[str, int]:
        return {"id": user_id}

class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings, cache_settings=providers.CacheSettings())
    user_repository = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)

with Container(groups=[Dependencies], validate=True) as container:
    settings = container.resolve(Settings)
    with container.build_child_container(scope=Scope.REQUEST) as request:
        repo = request.resolve(UserRepository)
        user = repo.find(42)
print("ok", user)
PY
```

Expected: prints `ok {'id': 42}`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add docs/index.md
git commit -m "docs(index): lead Quickstart with runnable sync example (audit O-2)"
```

---

### Task 3: to-2.x.md — make the Dict/List replacement example resolvable + add the `.cast` recipe (O-3, D-21/X-4)

**Files:**
- Modify: `docs/migration/to-2.x.md` (section 3 "After (2.x)" lines 142-143; Breaking-change item 6 / §6 around lines 222-265)

**Context (O-3):** `UserService(name: str, age: int)` and `AuthService(token: str, expiry: int)` are wired with bare `Factory(creator=...)`; the primitive params have no provider, so resolving raises `ArgumentResolutionError`.

- [ ] **Step 1: Add static kwargs to the two provider definitions**

Replace lines 142-143:

```python
user_service_provider = providers.Factory(creator=UserService)
auth_service_provider = providers.Factory(creator=AuthService)
```

with:

```python
# Primitive fields (str/int) have no provider — supply them via kwargs
user_service_provider = providers.Factory(creator=UserService, kwargs={"name": "admin", "age": 30})
auth_service_provider = providers.Factory(creator=AuthService, kwargs={"token": "secret", "expiry": 3600})
```

- [ ] **Step 2: Verify the full Dict/List example resolves**

```bash
uv run python - <<'PY'
from dataclasses import dataclass
from modern_di import Container, Group, Scope, providers

@dataclass(kw_only=True, slots=True, frozen=True)
class UserService:
    name: str
    age: int

@dataclass(kw_only=True, slots=True, frozen=True)
class AuthService:
    token: str
    expiry: int

def create_services_dict(user_service: UserService, auth_service: AuthService) -> dict[str, object]:
    return {"user": user_service, "auth": auth_service}

def create_service_list(user_service: UserService, auth_service: AuthService) -> list[object]:
    return [user_service, auth_service]

class G(Group):
    user_service_provider = providers.Factory(creator=UserService, kwargs={"name": "admin", "age": 30})
    auth_service_provider = providers.Factory(creator=AuthService, kwargs={"token": "secret", "expiry": 3600})
    my_dict = providers.Factory(scope=Scope.REQUEST, creator=create_services_dict)
    my_list = providers.Factory(scope=Scope.REQUEST, creator=create_service_list)

with Container(groups=[G], validate=True) as c:
    with c.build_child_container(scope=Scope.REQUEST) as r:
        print(r.resolve_provider(G.my_dict), r.resolve_provider(G.my_list))
PY
```

Expected: prints the dict and list, exit 0 (no `ArgumentResolutionError`).

- [ ] **Step 3: Add a `.cast` migration subsection (D-21 / X-4)**

In §6 (around line 222) or right after the Breaking-change item 6 that says `.cast` is removed, add:

````markdown
#### Migrating `.cast`

In 1.x, `.cast` wired one provider into another's dependency, e.g.
`UserService(db_engine=database_engine.cast)`. In 2.x there is no `.cast`;
wiring is by type. Map each 1.x usage:

| 1.x | 2.x |
|---|---|
| `dep=other_provider.cast` (a provider dependency) | Drop the argument — annotate the creator param with the dependency's type; it's resolved by type automatically. |
| `value=settings.host` (a static/literal value) | Pass it in `kwargs={"value": ...}`. |
| a request/context value | Register a `ContextProvider` for that type (see [Context](../providers/context.md)). |

```python
# 1.x
service = providers.Factory(MyService, db_engine=database_engine.cast)

# 2.x — MyService.__init__(self, db_engine: DBEngine); db_engine resolved by type
service = providers.Factory(scope=Scope.APP, creator=MyService)
```
````

- [ ] **Step 4: Verify the page still builds**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
```

Expected: build succeeds (or no new warnings for this page).

- [ ] **Step 5: Commit**

```bash
git add docs/migration/to-2.x.md
git commit -m "docs(migration): fix Dict/List example + add .cast recipe (audit O-3, D-21/X-4)"
```

---

### Task 4: context.md — manual-first example, missing-value section, cross-links (O-4, X-1, D-11)

**Files:**
- Modify: `docs/providers/context.md`

**Context:** O-4 — the page opens with a FastAPI-only "Basic Usage" that needs an external package and never declares a `ContextProvider`; the framework-agnostic example is second (lines 48-91). X-1 — the page is silent on what happens when no context value is set (direct `resolve()` → `None`; injection into a non-nullable `Factory` param → `ArgumentResolutionError`). D-11 — the page has zero outbound links.

- [ ] **Step 1: Promote the manual example to "Basic Usage"; demote FastAPI**

Reorder the page so the existing framework-agnostic `ContextProvider` example (currently lines 48-91) becomes the first `## Basic Usage` section, and the FastAPI example (currently lines 13-46) becomes a later `## With a framework integration` subsection that links `integrations/fastapi.md`. Keep both examples' code intact; only their order and headings change.

- [ ] **Step 2: Add a "Missing context value" subsection (X-1)**

Add after Basic Usage:

````markdown
## When no value is set

A `ContextProvider` resolves to its bound scope's context. If nothing was supplied:

- Resolving it **directly** (`container.resolve(MyType)`) returns `None`.
- Injecting it into a `Factory` parameter that is **not** `Optional`/defaulted raises
  `ArgumentResolutionError`.

Annotate the consuming parameter as `X | None` (or give it a default) if the value
can be absent. See [ContextProvider has no value](../troubleshooting/context-not-set.md).
````

- [ ] **Step 3: Add inline cross-links (D-11)**

On first mention, link: `Factory` → `factories.md`, `Scope` / `Scope.REQUEST` → `scopes.md`, `build_child_container` → `container.md`. Add a trailing `## See also` listing those three pages plus `integrations/fastapi.md`, matching the style of `scopes.md`/`lifecycle.md`.

- [ ] **Step 4: Verify links resolve and any manual snippet runs**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
```

Expected: no broken-link warnings for `context.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/providers/context.md
git commit -m "docs(context): manual-first example, missing-value section, cross-links (audit O-4, X-1, D-11)"
```

---

### Task 5: duplicate-type-error.md — correct the exception name (X-2)

**Files:**
- Modify: `docs/troubleshooting/duplicate-type-error.md` (lines 9-11)

**Context:** banner shows `RuntimeError: Provider is duplicated by type ...`; the framework raises `DuplicateProviderTypeError` (verified: `modern_di/exceptions.py:216`, a `RegistrationError` → `ModernDIError` → `RuntimeError`).

- [ ] **Step 1: Fix the banner and add the hierarchy note + cross-link**

Replace the code banner (lines 9-11):

```
RuntimeError: Provider is duplicated by type <class 'SomeType'>.
```

with:

```
DuplicateProviderTypeError: Provider is duplicated by type <class 'SomeType'>.
```

Below it add: "It descends from `RegistrationError` → `ModernDIError` → `RuntimeError`, so `except DuplicateProviderTypeError`, `except RegistrationError`, and `except RuntimeError` all catch it. See [Errors and exceptions](../providers/errors-and-exceptions.md)."

- [ ] **Step 2: Verify the class name is exact**

```bash
uv run python -c "from modern_di.exceptions import DuplicateProviderTypeError, RegistrationError, ModernDIError; assert issubclass(DuplicateProviderTypeError, RegistrationError) and issubclass(RegistrationError, ModernDIError) and issubclass(ModernDIError, RuntimeError); print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add docs/troubleshooting/duplicate-type-error.md
git commit -m "docs(troubleshooting): correct exception name to DuplicateProviderTypeError (audit X-2)"
```

---

### Task 6: providers.md (architecture) — document UnsupportedCreatorParameterError (A-3)

**Files:**
- Modify: `architecture/providers.md` ("Declaration-time signature parsing" / "Static kwargs" area)

**Context:** the authoritative reference enumerates declaration-time failures but omits `UnsupportedCreatorParameterError`, raised at declaration time for a parameterized-generic param (e.g. `list[int]`) with no default and not in `kwargs` (also for positional-only params without defaults).

- [ ] **Step 1: Confirm the trigger empirically**

```bash
uv run python - <<'PY'
from modern_di import Group, Scope, providers
class Svc:
    def __init__(self, items: list[int]) -> None: ...
try:
    class G(Group):
        svc = providers.Factory(scope=Scope.APP, creator=Svc)
except Exception as e:
    print(type(e).__name__, "—", e)
PY
```

Expected: prints `UnsupportedCreatorParameterError — ...`. (If the name differs, use the actual class name in the doc.)

- [ ] **Step 2: Add a paragraph/row documenting it**

Add to the declaration-time-errors list/table: `UnsupportedCreatorParameterError` — raised at **declaration time** when a creator parameter is a parameterized generic (e.g. `list[Foo]`) or positional-only, has no default, and is not supplied via `kwargs`. Escape hatches: pass it via `kwargs={...}`, give the parameter a default, or set `skip_creator_parsing=True`.

- [ ] **Step 3: Verify build**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
```

Note: `architecture/` is not in the mkdocs `docs_dir`, so the strict build won't cover it — instead verify by re-reading the edited section. (`architecture/` is plain repo prose.)

- [ ] **Step 4: Commit**

```bash
git add architecture/providers.md
git commit -m "docs(architecture): document UnsupportedCreatorParameterError (audit A-3)"
```

---

### Task 7: architecture/scopes.md — add missing imports to the worked example (O-7)

**Files:**
- Modify: `architecture/scopes.md` ("Worked example", lines 64-94)

**Context:** imports only `Container, Scope, providers` but uses `class AppGroup(Group)` and bare `CacheSettings()` → `NameError`.

- [ ] **Step 1: Fix the imports**

Add `Group` to the `from modern_di import ...` line, and change bare `CacheSettings()` to `providers.CacheSettings()` (matching the `providers.Factory` style on the same page). Keep the comment noting `DatabasePool`/`UserFromRequest` are user-defined stand-ins.

- [ ] **Step 2: Verify the import line is sufficient**

```bash
uv run python -c "from modern_di import Container, Scope, Group, providers; providers.CacheSettings(); print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add architecture/scopes.md
git commit -m "docs(architecture): add Group import + providers.CacheSettings to scopes example (audit O-7)"
```

---

### Task 8: container.md — make the Explicit Injection example actually use the container (D-1)

**Files:**
- Modify: `docs/providers/container.md` ("Explicit Injection", lines 33-46)

**Context:** the comment says "use the container to manually resolve dependencies" but the body is `return "some value"` and never touches `di_container`, so explicit shows no advantage over automatic.

- [ ] **Step 1: Make the body use `di_container` and add a "when to use" sentence**

Change the creator body to reference the injected container (e.g. `return di_container.scope.name`) so the example demonstrably depends on it. Add one sentence: explicit injection (`kwargs={"di_container": providers.container_provider}`) is needed when the parameter is not annotated as `Container`, or when you want an explicit binding rather than type-based resolution.

- [ ] **Step 2: Verify the example runs**

```bash
uv run python - <<'PY'
from modern_di import Container, Group, Scope, providers

def make(di_container):
    return di_container.scope.name

class G(Group):
    thing = providers.Factory(scope=Scope.APP, creator=make, kwargs={"di_container": providers.container_provider})

with Container(groups=[G], validate=True) as c:
    print(c.resolve_provider(G.thing))
PY
```

Expected: prints `APP`, exit 0. (Adjust the snippet if the doc uses a different creator shape.)

- [ ] **Step 3: Commit**

```bash
git add docs/providers/container.md
git commit -m "docs(container): make Explicit Injection example use the container (audit D-1)"
```

---

### Task 9: contributing.md — fix clone command and add a Submitting section (D-23, D-25)

**Files:**
- Modify: `docs/dev/contributing.md`

**Context:** D-23 — the clone block shows a bare SSH URL with no `git clone`. D-25 — the page stops after "run the tests"; no branch/commit/PR guidance, planning convention, or the 100% coverage gate.

- [ ] **Step 1: Fix the clone command (D-23)**

Change line 8 from:

```
git@github.com:modern-python/modern-di.git
```

to:

```
git clone git@github.com:modern-python/modern-di.git   # or: git clone https://github.com/modern-python/modern-di.git
```

- [ ] **Step 2: Add a "Submitting changes" section (D-25)**

Append:

````markdown
## Submitting changes
1. Fork the repo and branch off `main`.
2. Make your change with tests; keep **100% line coverage** (CI runs `just test-ci` with `--cov-fail-under=100`).
3. Run `just lint` and `just test` locally before pushing (CI runs the non-fixing variants `just lint-ci` / `just test-ci`).
4. For non-trivial changes, see the [planning convention](https://github.com/modern-python/modern-di/blob/main/planning/README.md).
5. Open a pull request upstream.
````

- [ ] **Step 3: Verify build**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add docs/dev/contributing.md
git commit -m "docs(contributing): fix git clone + add Submitting changes section (audit D-23, D-25)"
```

---

### Task 10: Fix broken numbered-list rendering (D-19)

**Files:**
- Modify: `docs/integrations/pytest.md` (install block, lines 12-28) and the four other integration pages + `docs/index.md` where the same flush-left continuation pattern appears: `docs/integrations/fastapi.md`, `faststream.md`, `litestar.md`, `typer.md`.

**Context:** content following a numbered item (tabbed blocks / code) is flush-left (column 0) instead of indented to the list's content column, so MkDocs terminates the `<ol>` and every step renders as "1.".

- [ ] **Step 1: Establish the failure in built HTML (baseline)**

```bash
uv run mkdocs build --strict >/dev/null 2>&1 || uv run mkdocs build >/dev/null 2>&1
grep -c '<li>1\.' site/integrations/pytest/index.html 2>/dev/null || grep -o '>1\.' site/integrations/pytest/index.html | wc -l
```

Note the count of repeated "1." items (the bug signature).

- [ ] **Step 2: Indent continuation content under each numbered item**

For each affected page, indent the continuation content (the `=== "..."` tab blocks and fenced code) by 4 spaces so it nests under its `1.` / `2.` / … item, OR restructure the steps as `###` headings if indentation is impractical for that page. Apply the *same* approach consistently across all affected files.

- [ ] **Step 3: Rebuild and confirm the list renders sequentially**

```bash
uv run mkdocs build --strict >/dev/null 2>&1 || uv run mkdocs build >/dev/null 2>&1
python3 -c "import re,sys; html=open('site/integrations/pytest/index.html').read(); print('ordered items start values:', re.findall(r'<ol start=\"(\d+)\"', html) or 'single <ol>')"
```

Expected: a single sequential `<ol>` (or `start` values 1,2,3,4 — not four separate `start=\"1\"`/repeated "1.").

- [ ] **Step 4: Commit**

```bash
git add docs/integrations/pytest.md docs/integrations/fastapi.md docs/integrations/faststream.md docs/integrations/litestar.md docs/integrations/typer.md docs/index.md
git commit -m "docs: fix numbered-list rendering across install blocks (audit D-19)"
```

---

### Task 11: container.md / context.md — split the Container-Provider page concerns (X-3)

**Files:**
- Modify: `docs/providers/container.md` (move "Advanced"/low-level API lines 96-137 and the "Context Propagation" warning lines 67-94)
- Modify: `docs/providers/context.md` (receive the context-propagation warning)
- Create: `docs/providers/advanced-api.md` (the low-level / custom-provider API material)
- Modify: `mkdocs.yml` (add the new page under Providers)

**Context:** the "Container Provider" page also carries a low-level public-API reference and a context-propagation warning that duplicates `troubleshooting/context-not-set.md` cause #1 — neither discoverable from the page title.

> **Heaviest task — confirm placement before moving.** If a lighter touch is preferred, an acceptable alternative is to keep the material on `container.md` but add clear sub-headings + a `## See also`; note that choice in the commit. Default is the split below.

- [ ] **Step 1: Create the new Advanced API page**

Move the "Advanced"/low-level API section (lines 96-137) out of `container.md` into a new `docs/providers/advanced-api.md` with a `# Advanced / low-level API` heading. Leave a one-line pointer + link on `container.md`.

- [ ] **Step 2: Move the context-propagation warning into context.md**

Move the "Context Propagation" warning (lines 67-94) into `docs/providers/context.md` (near the new "When no value is set" section from Task 4), and delete the duplicate from `container.md`. Ensure it doesn't contradict `troubleshooting/context-not-set.md`.

- [ ] **Step 3: Register the new page in nav**

In `mkdocs.yml`, under the `Providers:` list, add:

```yaml
      - Advanced / low-level API: providers/advanced-api.md
```

- [ ] **Step 4: Verify build + no orphan/broken links**

```bash
uv run mkdocs build --strict 2>&1 | tail -8
```

Expected: build succeeds; no broken-link or "not in nav" warnings.

- [ ] **Step 5: Commit**

```bash
git add docs/providers/container.md docs/providers/context.md docs/providers/advanced-api.md mkdocs.yml
git commit -m "docs: split Container-Provider page; move advanced API + context warning (audit X-3)"
```

---

### Task 12: litestar.md — make the websocket snippet self-contained (O-5) — VERIFY SIBLING REPO FIRST

**Files:**
- Modify: `docs/integrations/litestar.md` (Websockets section, lines 111-131)

**Context & blocker:** the snippet references `MyService` (defined nowhere) and injects via a bare `di_container: Container` param. The audit could **not** confirm from this repo whether a bare `Container` param auto-resolves in the Litestar websocket plugin without `FromDI`/`autowired_groups`. The Litestar integration lives in the separate `modern-python/modern-di-litestar` repo.

- [ ] **Step 1: Confirm the actual injection mechanic**

Check the `modern-di-litestar` repo (or ask the maintainer): does the websocket path auto-resolve a bare `Container`-typed parameter, or is a `FromDI` marker / `autowired_groups` required (as on the typer page, `typer.md:105`)?

- [ ] **Step 2: Make the snippet self-contained and correct**

Define or reuse `MyService` and `ALL_GROUPS` on the page so there's no `NameError`, and align the injection with whatever Step 1 confirmed (use `FromDI`/`autowired_groups` if that's the real mechanic — do **not** assert bare-type auto-resolution unless verified).

- [ ] **Step 3: Verify build**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add docs/integrations/litestar.md
git commit -m "docs(litestar): self-contained websocket snippet, correct injection (audit O-5)"
```

---

### Task 13: from-that-depends.md — reconcile the two FastAPI wiring patterns (O-6) — VERIFY SIBLING REPO FIRST

**Files:**
- Modify: `docs/migration/from-that-depends.md` (§6 lines 324-332 vs §8 lines 393-407)

**Context & blocker:** §6 wires FastAPI with a hand-written `lifespan` (`async with container`), §8 uses `modern_di_fastapi.setup_di(app, container)`; the page never explains how they combine or whether `close_async` runs twice. Whether `setup_di` composes/replaces a custom lifespan lives in the separate `modern-python/modern-di-fastapi` repo.

- [ ] **Step 1: Confirm `setup_di` lifespan behavior**

Check `modern-di-fastapi` (or ask the maintainer): does `setup_di` install its own lifespan that opens/closes the container? Does it compose with a user-supplied `lifespan` or replace it? Can `close_async` run twice?

- [ ] **Step 2: Add a reconciling note**

Add 1-2 sentences explaining the canonical production pattern based on Step 1, and link `integrations/fastapi.md` as the authoritative wiring. Don't write the exact mechanic until Step 1 confirms it.

- [ ] **Step 3: Verify build**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add docs/migration/from-that-depends.md
git commit -m "docs(migration): reconcile FastAPI lifespan vs setup_di wiring (audit O-6)"
```

---

### Task 14: Final verification

- [ ] **Step 1: Full strict build**

```bash
uv run mkdocs build --strict 2>&1 | tail -15
```

Expected: build succeeds with no broken-link / nav warnings.

- [ ] **Step 2: Confirm every Medium is addressed**

Cross-check the 16 distinct Mediums against commits: O-1/R-1 (T1), O-2 (T2), O-3 + D-21/X-4 (T3), O-4 + X-1 + D-11 (T4), X-2 (T5), A-3 (T6), O-7 (T7), D-1 (T8), D-23 + D-25 (T9), D-19 (T10), X-3 (T11), O-5 (T12), O-6 (T13). Note any deferred (O-5/O-6 if sibling-repo behavior couldn't be confirmed).

- [ ] **Step 3: Ship the bundles**

Per `planning/README.md`: hand-edit any affected `architecture/*.md` (already done for scopes.md/providers.md in T6/T7), then move both `2026-06-13.01-docs-ux-audit` and `2026-06-13.02-docs-ux-fixes` from `active/` to `archive/` with `status: shipped`, `pr:`, and `outcome:` filled. Open the PR.

---

## Self-review notes

- **Spec coverage:** all 16 distinct Mediums mapped to tasks (see Task 14 Step 2). The 54 Lows are explicitly out of scope per design.
- **Verification realism:** runnable snippets use `uv run python`; rendering uses `mkdocs build --strict`. `architecture/` pages (T6/T7) are outside `docs_dir`, so they're verified by snippet + re-read, noted in those tasks.
- **Known blockers:** T12 (O-5) and T13 (O-6) depend on sibling-repo behavior not present in this workspace and are gated on confirmation — they may be deferred if the maintainer can't confirm now.
