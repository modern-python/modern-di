---
summary: Docs accuracy + integration-parity pass — rendering fixes, factual corrections, framework-list de-drift, and full API/websocket parity for aiohttp/Litestar/Starlette.
---

# Design: Docs accuracy and integration-parity pass

**Date:** 2026-07-04
**Goal:** Close a batch of documentation defects found in a read-through of the
published site: broken Markdown rendering, factually wrong claims, framework
lists that drift as integrations are added, and integration pages that lack the
sections FastAPI's page has. Documentation-only; no library or integration code
changes.

## Summary

One PR that (1) fixes Markdown rendering bugs (inline-collapsed lists, escaped
pipes inside table code spans), (2) corrects factual errors (custom scopes,
Dishka autowiring, the "sync only" framing), (3) reduces framework-list drift by
collapsing generic enumerations to a single canonical list plus links and fixing
the wrong subsets, and (4) brings the aiohttp, Litestar, and Starlette
integration pages to parity with FastAPI (API tables; websocket + framework
context sections where missing; the aiohttp websocket-wiring explanation).

## Motivation

A page-by-page review of <https://modern-di.modern-python.org> surfaced:

- **Rendering.** `providers/factories.md#creator` renders its `1./2.` list
  inline because there is no blank line before the list; the
  `Creator-signature support matrix` shows literal backslashes
  (`param: X \| None`) because `\|` inside a `` `code span` `` is literal, not an
  escaped pipe.
- **Wrong facts.** `introduction/comparison.md` implies modern-di has no custom
  scopes (it does — any `IntEnum`, see `providers/scopes.md#custom-scopes`) and
  frames autowiring as a modern-di differentiator over Dishka (Dishka autowires
  by type too). `introduction/that-depends-or-modern-di.md` (and echoes in
  `comparison.md`/`design-decisions.md`) reads "sync only" in a way that scares
  readers off, without noting that finalizers may be sync **or** async.
- **Framework-list drift.** The set of supported frameworks is enumerated in ~7
  places. Two are correct full lists, several are precise subset-claims that are
  fine, but `introduction/about-di.md:205` is a clipped/incorrect list
  ("FastAPI, Litestar, FastStream") and `providers/scopes.md:75` names only
  fastapi/litestar/faststream as building the per-request child container when
  aiohttp and starlette do so as well. Every new integration multiplies the
  update sites.
- **Integration parity.** FastAPI's page has an `## API` table, a `## Websockets`
  section, and `## Framework Context Objects`. aiohttp and Litestar lack the API
  table; Starlette lacks all three beyond the basic example; the aiohttp
  websocket section does not explain *why* wiring is explicit there.

## Non-goals

- Renaming `Container` internals (`find_container`, `parent_container`,
  `scope_map`, `lock`) to underscore-private. It is a breaking public-API change
  needing a deprecation path; tracked as a follow-up (see Out of scope).
- Adding `mkdocstrings` or any auto-generated API reference. Docs tooling stays
  plain `mkdocs` + `mkdocs-material`.
- Any change to library or integration source. This bundle is docs-only.
- Rewriting the concurrency semantics themselves — only the prose that describes
  them (`design-decisions.md`) is tightened.

## Design

### 1. Rendering fixes (`providers/factories.md` + full-doc audit)

- **Collapsed lists.** Markdown needs a blank line between a paragraph and the
  list that follows it. Add it wherever missing. Confirmed offenders:
  `factories.md` `### creator` (the `1./2.` list after "…signature to:") and
  `### skip_creator_parsing` (the `-` list after "When `True`:"). Audit every
  `docs/**/*.md` for the same pattern (a non-blank line immediately followed by
  an `1.`/`-`/`*` list item) and fix each.
- **Escaped pipes in table code spans.** In the
  `### Creator-signature support matrix` table, replace `\|` inside inline code
  with the HTML entity `&#124;` — e.g. `` `param: X &#124; None` ``. Inside a
  `` `code span` `` a backslash is literal (renders `\|`), whereas the entity is
  emitted into the `<code>` and the browser decodes it to `|`. pymdownx's table
  extension passes the entity through correctly. Affected rows: the `X | None`,
  `A | B`, and any other `|`-containing code spans in that table.

### 2. Factual corrections

- **Custom scopes (`comparison.md`).** Adjust the landscape table row and the
  "vs Dishka" prose so they no longer say modern-di lacks custom scopes. Accurate
  framing: modern-di accepts *any `IntEnum`* as a scope (strictly-greater int
  than its parent), but does not offer an arbitrary *named* scope system the way
  Dishka does — link to `providers/scopes.md#custom-scopes`.
- **Dishka autowiring (`comparison.md`).** Reword row/prose so autowiring is not
  framed as exclusive to modern-di; Dishka resolves by type as well. Keep the
  genuine differentiators (first-party pytest plugin, small fixed core,
  all-official uniformly-maintained integrations).
- **"Sync only" framing.** Everywhere the phrase appears
  (`that-depends-or-modern-di.md`, `comparison.md`, `design-decisions.md`), add a
  short clause: resolution is synchronous, but finalizers may be sync **or**
  async (`close_sync`/`close_async`), so async teardown is fully supported. Goal:
  stop "sync only" from reading as "no async at all."
- **Concurrency prose (`design-decisions.md`, bullets on register-then-serve and
  last-write-wins).** Tighten to land the meaning faster. The meaning to
  preserve: the registries are thread-safe against *corruption*, but concurrent
  mutation is not a coordination mechanism — register providers in a setup phase
  before serving, and do `set_context`/overrides during setup or on a
  request-local child container, never from competing threads at serve time.
- **asyncpg (`recipes/async-lifespan.md`).** Keep the claim; add a half-sentence
  explaining *why* `asyncpg.create_pool(...)` belongs in the lifespan while the
  cases in "When a sync creator works instead" do not: the pool must be
  `await`ed (or `async with`) to open its connections, and modern-di has async
  *finalizers* but no async *initializer*, so the only place to `await`
  construction is the lifespan. (Verified against asyncpg docs: `create_pool`
  returns an awaitable `Pool`; idiomatic use is `await`/`async with`.)

### 3. Framework-list de-drift

Establish two canonical enumeration sites and make everything else link rather
than re-list:

- **Canonical full list:** `index.md` (the Quick-Start bullet, already correct
  and complete: aiohttp, FastAPI, FastStream, Litestar, Starlette, Typer, pytest)
  and the `comparison.md` "Official integrations" table row (also correct).
- **Convert generic enumerations to links.** Where prose only means "we support
  many frameworks," replace the hardcoded name list with a link to the
  Integrations section / comparison row. Primary target: `about-di.md:205`
  ("Works with FastAPI, Litestar, FastStream:") becomes a correct/linked
  statement.
- **Fix wrong subsets.** `providers/scopes.md:75` ("Framework-managed…") should
  not imply only fastapi/litestar/faststream build the per-request child — say
  "the framework integrations" and link, since aiohttp and starlette do too.
- **Leave precise subset-claims alone.** `writing-integrations.md`
  ("Dependency generator (FastAPI, Litestar)"), `context-not-set.md`,
  `request-scoped-engine.md`, etc. make accurate statements about specific
  frameworks' mechanics — those are not drift and stay.

### 4. Integration parity — aiohttp, Litestar, Starlette

All symbols below are taken from each package's `__all__` / `main.py` as read
during design; the plan must re-verify against source at implementation time.

#### 4a. aiohttp (`integrations/aiohttp.md`)

- **Add `## API` table** with: `setup_di(app, container)`, `FromDI(dependency)`,
  `inject`, `fetch_di_container(app)`, `fetch_request_container(request)`,
  `aiohttp_request_provider` (Request, REQUEST, auto-registered by type),
  `aiohttp_websocket_provider` (Request, SESSION, `bound_type=None` —
  reference-only, resolve via `FromDI`).
- **Websocket section — add the missing explanation.** aiohttp has *no separate
  WebSocket object*: a websocket is an upgraded `web.Request`, so
  `aiohttp_websocket_provider` binds `web.Request` too and is declared
  `bound_type=None` (not type-resolvable). That is exactly why it must be wired
  **explicitly** via `FromDI(aiohttp_websocket_provider)` rather than by type —
  unlike FastAPI/Litestar, which have distinct `WebSocket` objects. The existing
  example already uses the right symbols (`fetch_request_container`); add the
  prose that explains the explicit-wiring requirement.

#### 4b. Litestar (`integrations/litestar.md`)

- **Add `## API` table** with: `ModernDIPlugin(container, *, autowired_groups=...)`,
  `FromDI(dependency)`, `fetch_di_container(app)`,
  `litestar_request_provider`, `litestar_websocket_provider`. The page already
  has Websockets and Framework-Context-Objects sections — only the API table is
  missing.

#### 4c. Starlette (`integrations/starlette.md`)

Bring to full FastAPI parity. Behavior confirmed in `main.py`: the middleware
opens a REQUEST child for HTTP and a SESSION child for websockets automatically;
`starlette_request_provider` (REQUEST) and `starlette_websocket_provider`
(SESSION) are auto-registered.

- **Add `## Scopes`** note (HTTP → REQUEST, WebSocket → SESSION, auto-entered).
- **Add `## Websockets`** section. One asymmetry to resolve at implementation
  time: Starlette exposes **no public `fetch_request_container`** (aiohttp does).
  For a per-message nested REQUEST scope inside a Starlette websocket handler,
  verify the clean way to obtain the SESSION container — likely `@inject` +
  `FromDI(container_provider)` or type-based `Container` injection (the
  auto-registered `container_provider`). Document whatever is verified to work;
  if none is clean, document the limitation explicitly rather than inventing an
  API.
- **Add `## Framework Context Objects`** section mirroring FastAPI/Litestar
  (implicit type-based + explicit provider-based usage of
  `starlette_request_provider` / `starlette_websocket_provider`).
- **Add `## API` table** with: `setup_di(app, container)`, `FromDI(dependency)`,
  `inject`, `fetch_di_container(app)`, `starlette_request_provider`,
  `starlette_websocket_provider`.

### 5. advanced-api.md restructure (docs-only)

Split `providers/advanced-api.md` into two clearly-labelled parts: **supported
extension points** (`AbstractProvider` subclassing, `Group.get_providers()`,
`CacheSettings.is_async_finalizer`, the deprecated `cache_settings=` note) vs. a
**Container internals — no stability guarantee** subsection (`find_container`,
`parent_container`, `scope_map`, `lock`) that states these are advanced/internal
and may change without notice. No symbol renames (that is the follow-up below).

## Out of scope

- **Underscore-privatizing `Container` internals.** Research during design
  confirmed `find_container`/`parent_container`/`scope_map`/`lock` are referenced
  only inside `modern_di` core — none of the six integration packages use them —
  so a rename would not break the official integrations. But `find_container` is
  documented public advanced API, so the rename is still a breaking change for
  advanced/library-author users and needs its own bundle with a deprecation
  decision. `advanced-api.md` is still restructured in this PR (Design §5) but
  nothing is renamed.
- Adding `mkdocstrings`.

## Testing

- `mkdocs build --strict` locally — catches broken links and (with the fixes)
  confirms the pages build. Manually eyeball the rendered `factories.md` list and
  signature matrix, and the three integration pages.
- `just lint-ci` — no-autofix lint plus planning-bundle validation
  (`just check-planning` must pass for this bundle).
- No pytest impact (docs-only); `just test-ci` coverage gate is unaffected.

## Risk

- **Low overall — documentation only, no runtime code touched.**
- **`&#124;` entity not rendering as `|`** in some viewer: low; it is the
  standard pymdownx-tables workaround. Verified by `mkdocs build` + visual check.
- **Starlette websocket container-access pattern** turning out to have no clean
  public path: medium-likelihood, low-impact — mitigated by the design's
  instruction to document the verified pattern or the limitation, never an
  invented API.
- **Framework-list link strategy** could under-link and leave a stale subset
  somewhere: low; the audit enumerates every current site.
