# docs-accuracy-parity — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship one documentation-only PR that fixes Markdown rendering bugs,
corrects factual errors, de-drifts framework lists, and brings the aiohttp /
Litestar / Starlette integration pages to parity with FastAPI's.

**Spec:** [`design.md`](./design.md)

**Branch:** `docs/accuracy-parity` (already created and holds the design commit).

**Commit strategy:** Per-task commits.

## Global Constraints

- **Docs only.** No file under `modern_di/`, `tests/`, or any integration repo
  changes. Only `docs/**/*.md` and this bundle.
- **Line length 120** (matches repo style) for prose where practical; do not
  reflow unrelated lines.
- **Verification per task:** `just docs-build` (runs
  `mkdocs build --strict`, fails on broken links/nav) must pass. `just docs-build`
  uses `uvx --with-requirements docs/requirements.txt mkdocs build --strict`.
- **All symbol names in API tables are copied from each integration's
  `main.py` / `__all__`.** Do not invent symbols. Re-verify against source if in
  doubt: `src/pypi/modern-di-<pkg>/modern_di_<pkg>/__init__.py`.
- Run `just check-planning` before the final push (this bundle must stay valid).

---

### Task 1: Rendering fixes — collapsed lists and escaped pipes

**Files:**
- Modify: `docs/providers/factories.md`
- Modify: `docs/integrations/fastapi.md`
- Modify: `docs/integrations/litestar.md`
- Modify: `docs/migration/to-1.x.md`
- Modify: `docs/migration/to-2.x.md`

Add the missing blank line before every paragraph-followed-by-list (the list
otherwise renders inline), and fix the two escaped-pipe code spans in the
signature-support matrix.

- [ ] **Step 1: Audit — confirm the collapsed-list set**

  Run this from repo root to list every paragraph line (ends with `:`)
  immediately followed by a list item, ignoring code fences:

  ```bash
  cd docs && for f in $(find . -name '*.md'); do \
    awk 'prev ~ /:[[:space:]]*$/ && $0 ~ /^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]/ {print FILENAME":"NR} {prev=$0}' "$f"; \
  done
  ```

  Expected exactly these 9 lines (the list's first item; insert a blank line
  *above* each):
  `providers/factories.md:128`, `providers/factories.md:150`,
  `integrations/fastapi.md:76`, `integrations/fastapi.md:115`,
  `integrations/litestar.md:102`, `integrations/litestar.md:153`,
  `migration/to-1.x.md:12`, `migration/to-1.x.md:157`, `migration/to-2.x.md:8`.
  (Line numbers shift as you edit top-to-bottom; edit by matching the text
  below, not by number.)

- [ ] **Step 2: Fix `factories.md` — `### creator` list**

  Insert a blank line so the intro paragraph is separated from the list:

  ```
  Modern-DI analyzes the creator's signature to:

  1. Determine the return type (used for `bound_type` if not explicitly set)
  2. Identify parameter names and types for automatic dependency resolution
  ```

- [ ] **Step 3: Fix `factories.md` — `### skip_creator_parsing` list**

  ```
  Disables automatic dependency resolution. When `True`:

  - No automatic dependency resolution occurs
  ```

- [ ] **Step 4: Fix `factories.md` — signature matrix escaped pipes**

  Replace `\|` with `&#124;` inside the two code spans (browser decodes the
  entity to `|` inside `<code>`; a backslash there is literal). Change:

  ```
  | `param: X \| None` / `Optional[X]` |
  ```
  to
  ```
  | `param: X &#124; None` / `Optional[X]` |
  ```
  and
  ```
  | `param: A \| B` — union without `None` |
  ```
  to
  ```
  | `param: A &#124; B` — union without `None` |
  ```

- [ ] **Step 5: Fix the remaining collapsed lists**

  Insert a blank line before the first list item in each:

  - `integrations/fastapi.md` after `But when websockets are used, `SESSION` scope is used as well:`
  - `integrations/fastapi.md` after `The following context providers are available for import:`
  - `integrations/litestar.md` after `But when websockets are used, `SESSION` scope is used as well:`
  - `integrations/litestar.md` after `The following context providers are available for import:`
  - `migration/to-1.x.md` after `The migration to modern-di 1.x involves several key changes in the API, including:`
  - `migration/to-1.x.md` after `The key changes are:`
  - `migration/to-2.x.md` after `The migration to modern-di 2.x involves several key changes in the API, including:`

- [ ] **Step 6: Verify the audit is now clean and the site builds**

  ```bash
  cd docs && for f in $(find . -name '*.md'); do \
    awk 'prev ~ /:[[:space:]]*$/ && $0 ~ /^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]/ {print FILENAME":"NR} {prev=$0}' "$f"; \
  done
  # Expected: no output
  cd .. && grep -rn '\\|' docs
  # Expected: no output
  just docs-build
  # Expected: build succeeds, no warnings
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add docs/providers/factories.md docs/integrations/fastapi.md \
    docs/integrations/litestar.md docs/migration/to-1.x.md docs/migration/to-2.x.md
  git commit -m "docs: fix collapsed lists and escaped pipes in tables"
  ```

---

### Task 2: Factual corrections

**Files:**
- Modify: `docs/introduction/comparison.md`
- Modify: `docs/introduction/that-depends-or-modern-di.md`
- Modify: `docs/introduction/design-decisions.md`
- Modify: `docs/recipes/async-lifespan.md`

Correct custom-scopes and Dishka-autowiring claims, clarify "sync only" vs async
finalizers, tighten the concurrency prose, and explain why asyncpg needs the
lifespan.

- [ ] **Step 1: `comparison.md` — custom scopes in the landscape table**

  Change the `Scopes` row modern-di cell from
  `APP→…→STEP (fixed chain)` to `APP→…→STEP + any IntEnum`. Leave the Dishka
  cell (`RUNTIME→…→STEP (+ custom)`) unchanged.

- [ ] **Step 2: `comparison.md` — Dishka autowiring in the landscape table**

  Change the `Style` row so autowiring is not framed as exclusive. Set the Dishka
  cell to `type-based autowiring (provider classes)` (was `type-based, provider
  classes`). Leave the modern-di cell (`type-based autowiring`) unchanged.

- [ ] **Step 3: `comparison.md` — "vs Dishka" prose**

  In the paragraph beginning "If you need **arbitrary custom scopes**…", change
  `arbitrary custom scopes` to `arbitrary *named* scopes` (modern-di already
  supports any `IntEnum` scope). In the bullet
  "**Sync-only resolution and a small, fixed scope chain**…", replace it with:

  ```
  - **Sync-only *resolution* (async finalizers still supported) and a small,
    built-in scope chain you can still extend with any `IntEnum`** — a simpler
    model. Dishka's own docs note that custom scopes are "hardly ever needed,"
    which is the honest case for modern-di's simpler design. See
    [Custom scopes](../providers/scopes.md#custom-scopes).
  ```

- [ ] **Step 4: `comparison.md` — Resolution row footnote for async finalizers**

  In the `Resolution` row, change the modern-di cell from `sync (by design)` to
  `sync (async finalizers supported)`.

- [ ] **Step 5: `that-depends-or-modern-di.md` — clarify sync-only**

  In the `Resolution` table row, change the modern-di cell from
  `sync only (by design)` to `sync resolution (async finalizers supported)`.
  Then, immediately after the "How they differ" table, add a note:

  ```
  !!! note "\"Sync only\" means resolution, not teardown"
      modern-di resolves synchronously, but finalizers may be sync **or** async
      (`close_sync` / `close_async`), so async resource cleanup is fully
      supported. See [Lifecycle](../providers/lifecycle.md).
  ```

- [ ] **Step 6: `design-decisions.md` — clarify §1 sync-only**

  At the end of the first paragraph of "## 1. Resolution is sync only" (after the
  "(see [Async resources via lifespan]…)" sentence), append:

  ```
  Resolution being sync does not mean teardown is: finalizers may be sync or
  async (`close_sync` / `close_async`), so async cleanup is fully supported.
  ```

- [ ] **Step 7: `design-decisions.md` — tighten the concurrency bullets**

  Replace the two bullets currently reading "**Intended usage still holds.**…"
  and "**`set_context` and overrides are last-write-wins.**…" with:

  ```
  - **Registration is a setup phase, not a coordination tool.** The registry is
    lock-guarded against corruption, but the supported model is register every
    provider *before* serving. Registering a provider while other threads are
    already resolving is timing-dependent by nature — nothing breaks, but whether
    a given resolve sees the new provider is undefined.
  - **`set_context` and overrides are last-write-wins.** Both write into a
    per-container dict with no ordering, queueing, or merge; concurrent writes to
    the same key keep whichever landed last. Do them during setup, or per-request
    on a request-local child container — never from competing threads.
  ```

- [ ] **Step 8: `async-lifespan.md` — explain why asyncpg needs the lifespan**

  After the sentence "The same pattern works for `asyncpg.create_pool(...)`
  (truly async), …anything else that needs `await` to be ready." append:

  ```
  `asyncpg.create_pool(...)` returns an awaitable `Pool` that only opens its
  connections when `await`ed (or entered with `async with`); modern-di has async
  *finalizers* but no async *initializer*, so the `await` has to happen in the
  lifespan.
  ```

- [ ] **Step 9: Verify and commit**

  ```bash
  just docs-build   # Expected: build succeeds
  git add docs/introduction/comparison.md docs/introduction/that-depends-or-modern-di.md \
    docs/introduction/design-decisions.md docs/recipes/async-lifespan.md
  git commit -m "docs: correct custom-scopes/autowiring claims and sync-only framing"
  ```

---

### Task 3: Framework-list de-drift

**Files:**
- Modify: `docs/introduction/about-di.md`
- Modify: `docs/providers/scopes.md`

Point generic "we support frameworks" prose at the canonical list instead of
re-enumerating, and drop the under-inclusive integration subset in `scopes.md`.

- [ ] **Step 1: `about-di.md` — replace the clipped list with a link**

  In "### 5. Framework Integrations", replace:

  ```
  Works with FastAPI, Litestar, FastStream:
  ```
  with:
  ```
  Works with [every official framework integration](comparison.md#the-landscape).
  For example, with FastAPI:
  ```
  (Leave the FastAPI code block below it unchanged — it is an illustrative
  example, not a claim about coverage.)

- [ ] **Step 2: `scopes.md` — de-enumerate the framework-managed note**

  Replace the "**Framework-managed.**" sentence:

  ```
  **Framework-managed.** Integration packages (`modern-di-fastapi`, `modern-di-litestar`, `modern-di-faststream`) build the REQUEST child container for each request and tear it down at the end. You only declare `scope=Scope.REQUEST` on the providers that need it.
  ```
  with:
  ```
  **Framework-managed.** The [framework integrations](../integrations/fastapi.md) build the per-request child container for each request (or per-message for brokers) and tear it down at the end. You only declare `scope=Scope.REQUEST` on the providers that need it.
  ```

- [ ] **Step 3: Verify and commit**

  ```bash
  just docs-build   # Expected: build succeeds, links resolve
  git add docs/introduction/about-di.md docs/providers/scopes.md
  git commit -m "docs: link to canonical framework list instead of re-enumerating"
  ```

---

### Task 4: Restructure `advanced-api.md`

**Files:**
- Modify: `docs/providers/advanced-api.md`

Split the page into supported extension points vs. no-guarantee Container
internals. No symbol renames.

- [ ] **Step 1: Rewrite the page structure**

  Keep all existing content, but reorganize under two top-level parts. Replace
  the current `## `Container` attributes and methods` heading and its bullet
  list with an internals subsection carrying an explicit stability caveat. Final
  structure:

  ```
  # Advanced / low-level API

  Lower-level public surface for library authors and advanced use-cases.

  ## Supported extension points

  ### `Group.get_providers()`
  <existing Group.get_providers paragraph, unchanged>

  ### Subclassing `AbstractProvider`
  <existing subclassing section, unchanged>

  ### `CacheSettings.is_async_finalizer`
  <existing is_async_finalizer paragraph, unchanged>

  ### Deprecated: `cache_settings=`
  <existing deprecated section, unchanged>

  ## Container internals — no stability guarantee

  !!! warning "Internal surface"
      These attributes back the container's own machinery. They are documented
      for debugging and deep integration work only, and may change without a
      deprecation cycle. Do not build on them.

  - **`find_container(scope)`** — <existing text, unchanged>
  - **`parent_container`** — <existing text, unchanged>
  - **`scope_map`** — <existing text, unchanged>
  - **`lock`** — <existing text, unchanged>
  ```

- [ ] **Step 2: Verify and commit**

  ```bash
  just docs-build   # Expected: build succeeds
  git add docs/providers/advanced-api.md
  git commit -m "docs: split advanced-api into extension points vs internals"
  ```

---

### Task 5: aiohttp integration parity

**Files:**
- Modify: `docs/integrations/aiohttp.md`

Add the explicit-wiring explanation to the WebSocket section and an `## API`
table. Symbols from `modern_di_aiohttp/__init__.py`.

- [ ] **Step 1: Expand the WebSocket section with the "why explicit" explanation**

  In "### 4. WebSockets and per-message scope", after the sentence "Read the
  connection with `FromDI(aiohttp_websocket_provider)`." insert:

  ```
  Unlike FastAPI and Litestar, aiohttp has no separate WebSocket object — a
  WebSocket is an upgraded `web.Request`. So `aiohttp_websocket_provider` binds
  `web.Request` too, and is declared `bound_type=None` (not resolvable by type,
  because `aiohttp_request_provider` already owns `web.Request`). That is why you
  wire it **explicitly** with `FromDI(aiohttp_websocket_provider)` rather than by
  type annotation.
  ```

- [ ] **Step 2: Add the `## API` table at the end of the page**

  ```
  ## API

  | Symbol | Description |
  |---|---|
  | `setup_di(app, container)` | Opens the root container on startup, closes it on cleanup, and installs the middleware that builds a per-connection child container; returns the container. |
  | `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-connection child container. |
  | `inject` | Decorator for an `async def handler(request: web.Request, ...)`; resolves its `FromDI`-annotated parameters. |
  | `fetch_di_container(app)` | Returns the root `Container` stored on the app. |
  | `fetch_request_container(request)` | Returns the per-connection child container the middleware built (REQUEST for HTTP, SESSION for a WebSocket). |
  | `aiohttp_request_provider` | `ContextProvider` for `web.Request` (REQUEST scope), auto-registered by type. |
  | `aiohttp_websocket_provider` | `ContextProvider` for the WebSocket connection's `web.Request` (SESSION scope), `bound_type=None` — resolve via `FromDI(aiohttp_websocket_provider)`. |
  ```

- [ ] **Step 3: Verify and commit**

  ```bash
  just docs-build   # Expected: build succeeds
  git add docs/integrations/aiohttp.md
  git commit -m "docs: aiohttp — explain explicit ws wiring, add API table"
  ```

---

### Task 6: Litestar integration parity

**Files:**
- Modify: `docs/integrations/litestar.md`

Add the missing `## API` table (the page already has Websockets and
Framework-Context-Objects sections). Symbols from
`modern_di_litestar/__init__.py` and `main.py`.

- [ ] **Step 1: Add the `## API` table at the end of the page**

  ```
  ## API

  | Symbol | Description |
  |---|---|
  | `ModernDIPlugin(container, autowired_groups=None)` | Litestar `InitPlugin` that registers the container, composes the lifespan, and (if `autowired_groups` is given) exposes each provider in those groups as a Litestar dependency keyed by attribute name. |
  | `FromDI(dependency)` | Returns a Litestar `Provide` that resolves a provider or type from the per-request child container. |
  | `fetch_di_container(app)` | Returns the root `Container` stored on the Litestar app. |
  | `litestar_request_provider` | `ContextProvider` for `litestar.Request` (REQUEST scope), auto-registered. |
  | `litestar_websocket_provider` | `ContextProvider` for `litestar.WebSocket` (SESSION scope), auto-registered. |
  ```

- [ ] **Step 2: Verify and commit**

  ```bash
  just docs-build   # Expected: build succeeds
  git add docs/integrations/litestar.md
  git commit -m "docs: litestar — add API table"
  ```

---

### Task 7: Starlette integration parity

**Files:**
- Modify: `docs/integrations/starlette.md`

Bring Starlette to FastAPI parity: Scopes note, Websockets section (with a
verified container-access pattern), Framework Context Objects, and an `## API`
table. Symbols from `modern_di_starlette/main.py`.

- [ ] **Step 1: Verify the websocket container-access pattern before writing it**

  Starlette exposes **no** public `fetch_request_container`. Confirm how to reach
  the SESSION container inside a Starlette websocket handler for a nested
  per-message REQUEST scope. Write and run a throwaway check (scratchpad, do not
  commit) that starts a Starlette app via `setup_di`, opens a websocket, and
  resolves the container via `@inject` + type-based `Container` injection (the
  auto-registered `container_provider` resolves to the active container):

  ```python
  # scratchpad probe — confirm Container is injectable inside a ws handler
  import typing, modern_di
  from modern_di_starlette import FromDI, inject
  # @inject async def ws(websocket, container: typing.Annotated[modern_di.Container, FromDI(modern_di.providers.container_provider)]): ...
  ```

  If type/`container_provider` injection yields the SESSION child container,
  document that in Step 3. If it does not work cleanly, document the limitation
  explicitly instead (state that per-message REQUEST scope inside a Starlette ws
  handler has no first-class accessor yet) — **do not invent an API.**

- [ ] **Step 2: Add a `### 4. Scopes` note (after the existing "### 3. Scopes")**

  Note the page's existing "### 3. Scopes" already covers HTTP→REQUEST /
  WebSocket→SESSION. Rename nothing; instead expand it if needed so it states the
  SESSION scope is entered automatically for websockets (mirroring aiohttp's
  wording). If it already says this, skip.

- [ ] **Step 3: Add the Websockets section**

  Append after the Scopes section. Use the pattern confirmed in Step 1. Skeleton
  (fill the handler body with the verified accessor):

  ```
  ## Websockets

  A WebSocket connection opens a `Scope.SESSION` child container automatically and
  keeps it for the whole connection. For per-message work, open a nested
  `Scope.REQUEST` child of that session container:

  ```python
  import typing

  import modern_di
  from modern_di import Scope, providers
  from modern_di_starlette import FromDI, inject
  from starlette.websockets import WebSocket


  @inject
  async def ws_handler(
      websocket: WebSocket,
      container: typing.Annotated[modern_di.Container, FromDI(providers.container_provider)],
  ) -> None:
      await websocket.accept()
      async for message in websocket.iter_text():
          async with container.build_child_container(scope=Scope.REQUEST) as request_container:
              ...  # resolve REQUEST-scoped providers for this message
  ```
  ```

  (If Step 1 showed `container_provider` injection does not return the SESSION
  child, replace this block with the documented-limitation note from Step 1.)

- [ ] **Step 4: Add the Framework Context Objects section**

  Mirror FastAPI/Litestar. Append:

  ```
  ## Framework Context Objects

  Framework-specific context objects like `starlette.requests.Request` and
  `starlette.websockets.WebSocket` are automatically made available by the
  integration. You can reference these context providers implicitly through type
  annotations or explicitly by importing them.

  The following context providers are available for import:

  - `starlette_request_provider` — the current `starlette.requests.Request` (REQUEST scope)
  - `starlette_websocket_provider` — the current `starlette.websockets.WebSocket` (SESSION scope)

  ### Implicit Usage (Type-based Resolution)

  ```python
  from starlette.requests import Request
  from modern_di import Group, Scope, providers


  def create_request_info(request: Request) -> dict[str, str]:
      return {"method": request.method, "url": str(request.url)}


  class AppGroup(Group):
      request_info = providers.Factory(scope=Scope.REQUEST, creator=create_request_info)
  ```

  ### Explicit Usage (Provider-based Resolution)

  ```python
  import modern_di_starlette
  from starlette.requests import Request
  from modern_di import Group, Scope, providers


  def create_request_info(request: Request) -> dict[str, str]:
      return {"method": request.method, "url": str(request.url)}


  class AppGroup(Group):
      request_info = providers.Factory(
          scope=Scope.REQUEST,
          creator=create_request_info,
          kwargs={"request": modern_di_starlette.starlette_request_provider},
      )
  ```
  ```

- [ ] **Step 5: Add the `## API` table**

  ```
  ## API

  | Symbol | Description |
  |---|---|
  | `setup_di(app, container)` | Registers the container on `app.state`, composes the lifespan (opens/closes the container), and installs the middleware that builds a per-connection child container; returns the container. |
  | `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-connection child container. |
  | `inject` | Decorator for an `async def handler(connection: Request \| WebSocket, ...)`; resolves its `FromDI`-annotated parameters. |
  | `fetch_di_container(app)` | Returns the root `Container` stored on `app.state`. |
  | `starlette_request_provider` | `ContextProvider` for `starlette.requests.Request` (REQUEST scope), auto-registered. |
  | `starlette_websocket_provider` | `ContextProvider` for `starlette.websockets.WebSocket` (SESSION scope), auto-registered. |
  ```

  Note: the `Request \| WebSocket` cell uses a real escaped pipe *outside* a code
  span, which renders as `|`. (Do not use `&#124;` here — that trick is only for
  pipes inside `` `code spans` ``.)

- [ ] **Step 6: Verify and commit**

  ```bash
  just docs-build   # Expected: build succeeds, all anchors/links resolve
  git add docs/integrations/starlette.md
  git commit -m "docs: starlette — add websockets, context objects, and API table"
  ```

---

### Task 8: Final validation

**Files:** none (validation only).

- [ ] **Step 1: Full docs build + planning check**

  ```bash
  just docs-build      # Expected: success
  just check-planning  # Expected: planning: OK
  ```

- [ ] **Step 2: Finalize the bundle summary**

  Confirm `design.md`'s `summary:` still describes the shipped result; adjust if
  any task changed scope (e.g. the Starlette ws limitation path). Commit any edit:

  ```bash
  git add planning/changes/2026-07-04.02-docs-accuracy-parity/design.md
  git commit -m "docs: finalize docs-accuracy-parity bundle summary" || true
  ```

- [ ] **Step 3: Push and open the PR**

  ```bash
  git push -u origin docs/accuracy-parity
  gh pr create --fill --title "docs: accuracy + integration-parity pass"
  ```
  Then watch CI (the `docs-build` and lint jobs) until green.
