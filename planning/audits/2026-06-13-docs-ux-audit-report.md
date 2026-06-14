# Docs UX & Consistency Audit Report — 2026-06-13

This audit assessed the modern-di documentation surface — the docs site, README, `architecture/` truth-home, and public-API docstrings — through a reader-experience lens, weighted toward the new-user onboarding path (PyPI/GitHub landing → README → Quickstart → Introduction → Providers). It complements the 2026-06-12 correctness audit by focusing on whether a reader can get to first success, navigate between related concepts, and form a correct mental model — not whether the code is correct. No fixes were applied. Every High/Medium finding was adversarially verified against the source before inclusion; severities below are the post-verification adjusted values.

## Summary

The dominant theme is the onboarding journey: the README has no install command or code example, the Quickstart's first runnable example is async-only with no `asyncio.run()` (so a copy-paste silently does nothing), and several concept/integration examples are non-runnable as written (missing imports, undefined names, ellipsis placeholders, or under-wired creators). The second theme is cross-surface drift: the same concept is named inconsistently (`lifecycle` vs `lifetime`, `creator` vs `factory function`, `AppModule` vs `Dependencies`), one troubleshooting page misnames its exception (`RuntimeError` vs `DuplicateProviderTypeError`), and the missing-context behavior is documented three different ways across code, architecture, and user docs. Findability gaps are pervasive but individually minor: reference and troubleshooting pages frequently fail to cross-link to the concept pages that explain the errors they describe. After verification, no finding rose to High; the most material issues are a cluster of Mediums on the onboarding path and a handful of accuracy/consistency Mediums.

| Lens | High | Medium | Low | Total |
|---|---|---|---|---|
| Onboarding | 0 | 6 | 11 | 17 |
| Understanding | 0 | 2 | 9 | 11 |
| Findability | 0 | 1 | 12 | 13 |
| Consistency | 0 | 2 | 11 | 13 |
| Bug | 0 | 3 | 2 | 5 |
| Readability | 0 | 1 | 5 | 6 |
| Convenience | 0 | 1 | 4 | 5 |
| **Total** | **0** | **16** | **54** | **70** |

## Top findings by impact

1. **Medium** — README (whole file): no `pip install` line and no code example, so a GitHub/PyPI visitor sees zero "what does this look like" before clicking out to the docs site.
2. **Medium** — `docs/index.md` 4.2 (lines 103-120): the first complete Quickstart example is async-only and never calls `asyncio.run(main())`, so a newcomer who copies and runs it gets no output and no error — a silent failure on the highest-weight onboarding step.
3. **Medium** — `docs/migration/to-2.x.md` §3 (lines 126-159): the canonical Dict/List replacement example is non-functional — bare `Factory(creator=...)` with unresolvable `str`/`int` fields raises `ArgumentResolutionError` at resolution.
4. **Medium** — `docs/troubleshooting/duplicate-type-error.md` (lines 9-11): the error banner says `RuntimeError` but the framework raises `DuplicateProviderTypeError`; a user grepping the class name they actually saw never lands on the page that explains it.
5. **Medium** — `docs/providers/container.md` "Explicit Injection" (lines 33-46): the example's comment says "use the container to manually resolve dependencies" but the body never touches `di_container` and shows no advantage over the automatic form just above.
6. **Medium** — `docs/providers/context.md` Basic Usage (lines 13-46): the core ContextProvider page leads with a FastAPI-only example that requires an external package and never declares a `ContextProvider`.
7. **Medium** — Missing-context behavior (cross-surface): code returns `None`, architecture documents the `Factory` raise-caveat, but `docs/providers/context.md` is silent — a user ships non-nullable params and hits an unexpected `ArgumentResolutionError`.
8. **Medium** — `docs/integrations/pytest.md` install block (lines 12-28): flush-left continuation content breaks MkDocs list rendering so all four onboarding steps render as "1." (verified in built HTML; replicated across 6 files).

## Findings

### Onboarding path

#### O-1 — README has no install command or code example (medium)
- Location: `README.md` (whole file)
- Lens: onboarding
- Issue: README is badges + a feature bullet list + links to the external docs site. No `pip install modern-di` / `uv add modern-di` and no inline Group/Factory/Container/resolve snippet.
- Reader harm: A visitor evaluating the library on GitHub/PyPI (the most common first touchpoint) cannot judge it or reach first success without a click-out to a separate docs site; comparison-shoppers bounce.
- Suggested fix: Add an Install line and a ~15-line copy-pasteable minimal Quick Start (one Factory, a Container, a `resolve()` call), mirroring `docs/index.md` lines 25-43 and 51-120; keep the deep dive on the docs site. Keep it short and link out to avoid drift.

#### O-2 — Quickstart's first runnable example is async-only and never runs (medium)
- Location: `docs/index.md` step 4.2 (lines 101-120)
- Lens: onboarding
- Issue: The first complete end-to-end example wraps everything in `async def main()` / `async with Container(...)` but never calls `asyncio.run(main())` and never imports `asyncio`. Nothing in the example does async work (resolution is sync-only; `find()` is sync).
- Reader harm: A first-timer copies the canonical Quickstart, runs the file, gets no output and no error, and concludes the framework is broken or that they erred — a silent no-op on the highest-weight step.
- Suggested fix: Lead with a synchronous example (`with Container(groups=[Dependencies], validate=True) as container:` and sync child container), since `resolve()` is sync and `Container` supports `with`/`close_sync()`. Demote the async variant to a clearly-labelled follow-on for async finalizers (or, minimally, add `import asyncio` + `asyncio.run(main())`).

#### O-3 — `to-2.x.md` Dict/List replacement example raises at resolution (medium)
- Location: `docs/migration/to-2.x.md` §3 "After (2.x)" (lines 126-159)
- Lens: bug
- Issue: `UserService(name: str, age: int)` / `AuthService(token: str, expiry: int)` are wired with bare `providers.Factory(creator=...)` and no `kwargs`, so the primitive fields have no matching provider. Resolving `my_dict` raises `ArgumentResolutionError`. Reproduced end-to-end.
- Reader harm: A 1.x user migrating off Dict/List copies the canonical example, runs it, and gets a runtime error on the exact pattern the guide teaches; the migration stalls.
- Suggested fix: Supply static values via `kwargs`, e.g. `providers.Factory(creator=UserService, kwargs={"name": "admin", "age": 30})`, or use dependency-shaped fields that have their own providers.

#### O-4 — ContextProvider page leads with a FastAPI-only example (medium)
- Location: `docs/providers/context.md` "Basic Usage with FastAPI" (lines 13-46)
- Lens: onboarding
- Issue: The first "Basic Usage" section for the core ContextProvider concept requires the external `modern_di_fastapi` package and declares no `ContextProvider` at all; the wiring is described only in prose. The correct framework-agnostic example is present but second (lines 48-91).
- Reader harm: A newcomer learning what ContextProvider is, core-framework-only, is shown an example that needs a separate install and never contains the provider type the page is about; concept-to-example mismatch.
- Suggested fix: Promote the existing manual example to "Basic Usage" (explicit `ContextProvider` + `build_child_container(context={...})`); demote FastAPI to a "With integrations" subsection linking `integrations/fastapi.md`.

#### O-5 — `litestar.md` websocket snippet uses undefined names and unexplained injection (medium)
- Location: `docs/integrations/litestar.md` Websockets section (lines 111-131)
- Lens: onboarding
- Issue: References `MyService` (defined nowhere on the page) and injects via a bare `di_container: Container` parameter. Note: the websocket plugin passes no `autowired_groups`, so a bare `Container` param likely does *not* auto-resolve without `FromDI` — the rest of the docs use `FromDI`/`autowired_groups` (e.g. `typer.md` line 105).
- Reader harm: A reader copy-pasting hits `NameError` on `MyService` and cannot tell whether `di_container: Container` auto-resolves or needs a marker.
- Suggested fix: Make the snippet self-contained (define/reuse `MyService` and `ALL_GROUPS`). Do **not** assert bare-type auto-resolution as the original finding suggested — verify the actual Litestar integration behavior and align the snippet with `FromDI`/`autowired_groups`.

#### O-6 — `from-that-depends.md` async-creator §6 vs framework-integration §8 are never reconciled (medium)
- Location: `docs/migration/from-that-depends.md` §6 (lines 324-332) vs §8 (lines 393-407)
- Lens: understandability
- Issue: §6 wires FastAPI with a hand-written `lifespan=lifespan` (`async with container`, which runs `close_async`), while §8 wires it with `modern_di_fastapi.setup_di(app, container)` (no custom lifespan, also calls `close_async`). The page never explains how these combine, whether `setup_di` replaces/wraps a custom lifespan, or whether `close_async` runs twice.
- Reader harm: A user needing both an async resource and the integration guesses at order, may double-close the container or lose their lifespan, and can't tell which pattern is canonical for production.
- Suggested fix: Add a reconciling sentence and link `integrations/fastapi.md` as the authoritative wiring. Caveat: verify against the separate `modern-di-fastapi` repo whether `setup_di` composes a custom lifespan before writing the exact code mechanic.

#### O-7 — `architecture/scopes.md` worked example missing `Group`/`CacheSettings` imports (medium)
- Location: `architecture/scopes.md` "Worked example" (lines 64-94)
- Lens: onboarding
- Issue: Imports only `Container`, `Scope`, `providers`, but uses `class AppGroup(Group)` and bare `CacheSettings()` — both raise `NameError`. (`DatabasePool`/`UserFromRequest` are intentional undefined stand-ins.) Inconsistent with `containers.md`, which imports `Group` before use.
- Reader harm: A reader copy-pasting the canonical scope example hits `NameError` on the first class line.
- Suggested fix: Add `Group` to the `modern_di` import and use `providers.CacheSettings()` (matching the existing `providers.Factory` style); keep a comment noting the creator classes are user-defined.

#### O-8 — `docs/index.md` Quickstart step numbering jumps 1/2/3 → 4.1/4.2 (low)
- Location: `docs/index.md` headings `## 4.1.` / `## 4.2.`
- Lens: readability
- Issue: A clean `## 1.`/`## 2.`/`## 3.` walkthrough switches to top-level decimal sub-numbering with no `## 4.` parent; reads as a typo on first scan.
- Reader harm: A reader scanning the linear quickstart wonders if they missed a step 4 and re-scans to confirm 4.1/4.2 are alternatives, not sequence.
- Suggested fix: Introduce a `## 4. Wire it up` parent with `### Option A` / `### Option B` (framework integration vs. modern-di directly), or add a one-line "these are two mutually-exclusive choices" lead-in.

#### O-9 — `docs/index.md` introduces "finalizers" undefined with no visible behavior (low)
- Location: `docs/index.md` step 4.2 comments (lines 118-119)
- Lens: understanding
- Issue: "Finalizers" appears for the first time on the landing page with no gloss, and the example registers no finalizer, so the comments describe cleanup the reader can't see.
- Reader harm: A zero-context reader meets an undefined term tied to invisible behavior.
- Suggested fix: Add a half-sentence gloss (e.g. "finalizers — teardown hooks like closing a DB connection") and/or link `providers/lifecycle.md` on first use.

#### O-10 — `about-di.md` lifetime-management snippet missing `import uuid` (low)
- Location: `docs/introduction/about-di.md` "Lifetime Management in DI" (lines 70-94)
- Lens: onboarding
- Issue: The block calls `uuid.uuid4()` (line 92) but its only import is `from modern_di import ...`. The concepts themselves are glossed inline and re-taught runnably below, so the only load-bearing defect is the missing import.
- Reader harm: A reader treating the (illustrative) block as runnable hits a `NameError`.
- Suggested fix: Add `import uuid`.

#### O-11 — `resolving.md` example has an unused `Scope` import (low)
- Location: `docs/introduction/resolving.md` sub-dependency example (lines 31-39)
- Lens: understanding
- Issue: `Scope` is imported (line 16) but never used; both `Factory` calls silently default `scope=Scope.APP`. `validate=True` is explained later (line 51).
- Reader harm: A reader copying the example into a project gets a ruff F401 and a "why is this here?" question.
- Suggested fix: Either pass `scope=Scope.APP` explicitly so the import is used, or drop the import and add a one-line note that scope defaults to APP (link Scopes).

#### O-12 — `scopes.md` examples use undefined `Dependencies` with no cross-link (low)
- Location: `docs/providers/scopes.md` examples (lines 27-35, reused 61-69, 77-81)
- Lens: onboarding
- Issue: Examples use `Container(groups=[Dependencies])` where `Dependencies` is never defined on the page. (It *is* defined three pages earlier in the Quickstart and `resolving.md`, so nav-order readers have seen it; the gap is for deep-link arrivals.)
- Reader harm: A reader deep-linking directly to scopes.md lands without local context or a pointer.
- Suggested fix: Add an inline note + link to where `Dependencies(Group)` is defined (Quick-Start or `introduction/resolving.md`, which precede this page — not `factories.md`, which follows it).

#### O-13 — `scopes.md` "Custom scopes" snippet is internally inconsistent (low)
- Location: `docs/providers/scopes.md` "Custom scopes" (lines 99-104)
- Lens: onboarding
- Issue: `tenant_provider` is declared as a bare variable and never attached to a Group, while `Container(groups=[MyGroup])` references a `MyGroup` that is never defined. The provider→Group→Container wiring (the point of the example) is never shown.
- Reader harm: A reader cannot tell how a custom-scope provider actually reaches the container.
- Suggested fix: Define `class MyGroup(Group)` with `tenant_provider` as a class attribute and a concrete `creator`, matching the dominant Group pattern used elsewhere.

#### O-14 — `litestar.md` first example has unused `import typing` (low)
- Location: `docs/integrations/litestar.md` first example (line 30)
- Lens: readability
- Issue: `import typing` is included but never used in the snippet.
- Reader harm: A reader copies a dead import (ruff F401) and may wonder how `typing` relates to DI.
- Suggested fix: Remove the unused `import typing`.

#### O-15 — `typer.md` first example has unused `import modern_di` (low)
- Location: `docs/integrations/typer.md` first example (line 31)
- Lens: readability
- Issue: `import modern_di` is present but the first example uses only `modern_di_typer` and the `from modern_di import ...` names; the dotted module is needed only in the later Action-scope example.
- Reader harm: A reader carries an unused import (ruff F401) and is unsure whether both import styles are needed for the happy path.
- Suggested fix: Drop `import modern_di` from the first example (it has its own import in the Action-scope example).

#### O-16 — `typer.md` Action-scope snippet uses undefined `app` and `creator=...` (low)
- Location: `docs/integrations/typer.md` Action scope section (lines 91-110)
- Lens: onboarding
- Issue: Uses `@app.command()`/`app` without defining `app` and uses `creator=...` (an ellipsis placeholder), with no cue it continues the first example. The teaching mechanism is correctly explained in prose, and fragment-continuation is the site's house style.
- Reader harm: A reader treating it as standalone gets a `NameError` and a non-functional `creator=...`.
- Suggested fix: Add a one-line lead-in that it builds on the first example's `app`/`container`, and replace `creator=...` with a small `Job` class exposing `run()`.

#### O-17 — `pytest.md` step 4 references an `expose`-derived fixture never shown on a group (low)
- Location: `docs/integrations/pytest.md` step 4 (lines 62-80)
- Lens: onboarding
- Issue: `expose(Dependencies, Auth, Billing)` then a test consumes `user_service`, but no `user_service` attribute is shown on any group (unlike `email_client`, which is named explicitly). The derivation rule is stated in prose, but no worked attribute→fixture instance is shown.
- Reader harm: A reader can't concretely verify how `expose` derives fixture names from their own providers.
- Suggested fix: Add a one-line comment (`# user_service is the attribute on Dependencies`) or a 2-3 line Group definition.

### docs/ site

#### D-1 — `container.md` "Explicit Injection" example never uses the container (medium)
- Location: `docs/providers/container.md` (lines 33-46)
- Lens: understanding
- Issue: The comment says "use the container to manually resolve dependencies" but the body is `return "some value"` and never touches `di_container`. Both the Automatic and Explicit examples use a `di_container: Container` param, so the explicit `kwargs={"di_container": providers.container_provider}` form shows no advantage over the automatic form above it (which *does* use the container).
- Reader harm: A reader can't learn when/why to prefer explicit injection and has nothing meaningful to copy.
- Suggested fix: Make the body actually use the container (e.g. `di_container.scope.name`) and add one sentence on when explicit is needed (parameter not annotated as `Container`, or you want an explicit binding).

#### D-2 — `scopes.md` "Resolving across scopes" doesn't name the error or route to a fix (low)
- Location: `docs/providers/scopes.md` (line 83)
- Lens: findability
- Issue: States resolving a REQUEST-scoped provider from an APP container "raises a clear error" without naming it (`ScopeNotInitializedError`) or linking the reference. Note: do **not** link `troubleshooting/scope-chain.md` — that page covers a *different* error (`InvalidScopeDependencyError`/validation-time, fixed by changing provider scope), not the resolution-time `ScopeNotInitializedError` (fixed by building the child container first).
- Reader harm: A reader who hits the error has no breadcrumb to the explanation.
- Suggested fix: Name `ScopeNotInitializedError` and/or link `providers/errors-and-exceptions.md` (which documents it), not `scope-chain.md`.

#### D-3 — `scopes.md` async vs sync `build_child_container` unexplained (low)
- Location: `docs/providers/scopes.md` "Building child containers" (lines 59-69)
- Lens: understanding
- Issue: A `with` and an `async with` block appear with no prose on when to pick which (only "finalizers ran here" vs "async finalizers ran here" comments). The rule lives in the sibling `lifecycle.md` (line 97), linked in "See also".
- Reader harm: A reader is left guessing whether they need `async with` or `with`.
- Suggested fix: Add one sentence: "Use `async with` only when the scope holds providers with async finalizers; otherwise plain `with` is enough. Resolution itself is always synchronous."

#### D-4 — `lifecycle.md` has no imports in any code block (low)
- Location: `docs/providers/lifecycle.md` (top of file / all code blocks)
- Lens: onboarding
- Issue: Zero import statements across 8 code blocks, while every sibling provider page opens with `from modern_di import ...`. Names `Container`, `providers`, `Scope`, `exceptions` are used undeclared. (Some names — `Dependencies`, `AsyncEngine`, etc. — are intentional placeholders.)
- Reader harm: A reader copy-pasting can't tell what to import; lifecycle.md is the outlier among siblings.
- Suggested fix: Add a one-line `from modern_di import Container, Scope, providers, exceptions` near the top and note `Dependencies` is a user-defined `Group`.

#### D-5 — `lifecycle.md` finalizer ordering described with two different terms (low)
- Location: `docs/providers/lifecycle.md` (lines 64, 103, 148)
- Lens: consistency
- Issue: "Reverse-resolve order" (line 64) vs "reverse-creation order, as above" (line 103) for the same behavior; the "as above" asserts equivalence without stating why. (They are in fact identical because creation is lazy-on-first-resolve; code iterates `reversed(_creation_order)`.)
- Reader harm: A reader reasoning about cleanup order (session before engine) sees two nouns and can't be sure they're guaranteed identical.
- Suggested fix: Standardize on "reverse-creation order" (matches the code/docstring), or add a half-sentence noting creation order equals first-resolve order.

#### D-6 — `factories.md` leads with dense reference before any basic example (low)
- Location: `docs/providers/factories.md` (lines 1-83; whole-page ordering)
- Lens: onboarding
- Issue: Opens with a one-line intro then a dense `## Parameters` reference (union/optional semantics, support matrix, X-3 wiring, creator-failure semantics) before the first basic "Regular Factories" example at line ~184. (Mitigated: Factory is already demonstrated in the Quickstart, so this is a reference page, not the onboarding entry point.)
- Reader harm: Even as a reference, advanced edge cases precede the fundamentals; the regular-vs-cached distinction is buried ~180 lines down.
- Suggested fix: Move "Types of factories"/"Regular Factories" up near the top; push the support matrix, X-3 wiring, and creator-failure semantics into a later "Advanced"/"Edge cases" section.

#### D-7 — `factories.md` heading contains internal identifier "(X-3)" (low)
- Location: `docs/providers/factories.md` (line 101)
- Lens: understanding
- Issue: The heading reads "Provider passed as a kwargs value (X-3)"; "X-3" is an internal change-bundle/audit identifier that appears nowhere else and is never defined.
- Reader harm: A reader assumes "X-3" is a concept/version they should know and searches fruitlessly.
- Suggested fix: Drop "(X-3)" → "### Provider passed as a kwargs value". No anchor targets the parenthetical.

#### D-8 — `factories.md` "Escaping problem shapes" uses type-inconsistent `list[X] = None` (low)
- Location: `docs/providers/factories.md` (line 97)
- Lens: bug
- Issue: The blessed escape example is `def f(items: list[X] = None)` — annotation `list[X]` with default `None`, which the project's own ruff (`select=["ALL"]`, RUF013) / ty would reject.
- Reader harm: A reader copies the idiom and gets a signature their own type checker flags, contradicting the example's "avoid errors" purpose.
- Suggested fix: Use `def f(items: list[X] | None = None)` (verified to still escape the declaration error and preserve end behavior); avoid `list[X] = []` (mutable-default B006).

#### D-9 — `factories.md` "Parameters" intermixes constructor args with behavior sections (low)
- Location: `docs/providers/factories.md` "## Parameters" (lines 5-7 onward)
- Lens: readability
- Issue: At the same `###` level, pure constructor params (scope, creator, bound_type, kwargs, cache_settings, skip_creator_parsing) are interleaved with behavioral sub-sections (Union/Optional params, support matrix, X-3, creator-failure semantics) — splitting the param list mid-stream.
- Reader harm: A reader scanning for "what args can I pass to `Factory()`" must filter behavioral prose out of the list.
- Suggested fix: Split into a tight "## Parameters" (constructor args only) and a separate "## Resolution behavior"/"## Signature handling" section. Preserve the `#optional-parameters` anchor (the matrix links to it) by keeping the heading text.

#### D-10 — `container.md` Advanced section buries library-author API (low)
- Location: `docs/providers/container.md` "Advanced" (lines 96-137)
- Lens: findability
- Issue: A grab-bag of low-level surface (`Group.get_providers()`, subclassing `AbstractProvider`, `CacheSettings.is_async_finalizer`, `find_container`, `scope_map`) lives under "Container Provider" with no nav entry that suggests it. (Correction to the original finding: the `effective_scope` bullet is custom-provider *authoring* guidance citing Alias as an exemplar, **not** misfiled Alias usage docs — do not relocate it to `alias.md`.)
- Reader harm: A library author wanting custom-provider/low-level-API docs won't think to open "Container Provider"; the content is effectively hidden.
- Suggested fix: Move custom-provider/`AbstractProvider`/`get_providers` material to a dedicated Advanced/API nav page, or at least cross-link from where readers would look. The section is honestly labelled, so beginners aren't misled.

#### D-11 — `context.md` has no cross-links to related core pages (medium)
- Location: `docs/providers/context.md` (whole page)
- Lens: findability
- Issue: Uses `Factory`, `Scope.REQUEST`, `build_child_container` heavily but links to nothing — zero outbound links — while sibling pages cross-link and other pages (recipes, troubleshooting) link *into* context.md. A conspicuous dead-end on a dense onboarding page.
- Reader harm: A reader hitting an unfamiliar concept has no path forward and must hunt the nav.
- Suggested fix: Add inline links (Factory→factories.md, Scope→scopes.md, build_child_container→container.md, "the integration"→integrations/fastapi.md), ideally plus a trailing "See also" to match scopes/lifecycle/factories.

#### D-12 — `alias.md` Overrides section doesn't link to the overrides docs (low)
- Location: `docs/providers/alias.md` "## Overrides" (lines 69-96)
- Lens: findability
- Issue: Relies on `provider_id`, `container.override`, `reset_override` without linking where they're introduced. The page has no "See also" at all.
- Reader harm: A reader arriving via search has no pointer to learn the override mechanism, so the precedence note (line 82) lacks context.
- Suggested fix: Link `docs/recipes/testing-overrides.md` (the canonical home for the override primitive) on first mention of `container.override` — not `docs/testing/`, which covers the pytest fixtures.

#### D-13 — `errors-and-exceptions.md` entries don't link to matching troubleshooting pages (low)
- Location: `docs/providers/errors-and-exceptions.md` (most exception entries)
- Lens: findability
- Issue: The Troubleshooting section has pages mapping 1:1 onto exceptions documented here (Circular, Missing Provider, Duplicate Type, Scope errors, ContextProvider/ArgumentResolutionError), but only the two `FinalizerError` entries cross-link (to Lifecycle).
- Reader harm: A reader landing here after an error gets a one-liner and a dead end instead of the troubleshooting page that explains the fix.
- Suggested fix: Add inline "See [Troubleshooting]..." links to each entry with a matching page, mirroring the existing `FinalizerError`→Lifecycle pattern. (Mitigated: the Troubleshooting nav is always visible in the sidebar.)

#### D-14 — `fastapi.md` lacks the API reference table that `faststream.md` has (low)
- Location: `docs/integrations/fastapi.md` (overall) vs `docs/integrations/faststream.md` (lines 135-143)
- Lens: consistency
- Issue: FastStream ends with a clean `## API` table; FastAPI has none — its symbols (`setup_di`, `FromDI`, `build_di_container`, `fastapi_request_provider`, `fastapi_websocket_provider`) are scattered through prose/code.
- Reader harm: A reader cross-referencing the two integrations gets uneven treatment and must reverse-engineer the FastAPI API surface.
- Suggested fix: Add a mirrored `## API` table — but write accurate descriptions (e.g. `build_di_container` is a `Depends` callable, not FastStream's `fetch_di_container` getter), not a verbatim copy.

#### D-15 — `fastapi.md` `build_di_container` introduced without description (low)
- Location: `docs/integrations/fastapi.md` Websockets section (line 98)
- Lens: understanding
- Issue: `build_di_container` appears only as a `fastapi.Depends` target and is never described anywhere on the page; sibling pages (faststream, typer) document their container-fetch helper in an `## API` section.
- Reader harm: A reader can't learn what it returns (the SESSION-scoped container) or how to obtain the container outside websockets.
- Suggested fix: Add a one-line description (what it returns and its scope) inline or in the new API table.

#### D-16 — `fastapi.md` getting-started omits `validate=True` (low)
- Location: `docs/integrations/fastapi.md` (line 57) vs `docs/integrations/faststream.md` (line 65)
- Lens: consistency
- Issue: FastStream uses `Container(..., validate=True)` (so does typer.md:63), FastAPI uses `Container(groups=ALL_GROUPS)` with no `validate`. The project's own docs (scopes.md, scope-chain.md, index.md) repeatedly recommend `validate=True`.
- Reader harm: A reader following both pages gets contradictory signals about whether `validate=True` is the recommended default.
- Suggested fix: Add `validate=True` to the FastAPI example (the single factory validates cleanly); ideally apply to litestar/pytest pages too for full consistency.

#### D-17 — `fixtures.md` cross-reference promises a worked example that isn't on the target page (low)
- Location: `docs/testing/fixtures.md` (line 7) → `docs/integrations/pytest.md`
- Lens: findability
- Issue: fixtures.md promises pytest.md has a plain-`modern-di` `container.resolve(...)` worked example, but pytest.md has zero `resolve(...)` calls — the resolve-based example lives in `recipes/testing-overrides.md`. (Most of the described setup *is* present on pytest.md; only the "resolve inside tests" payoff is missing, and fixtures.md line 9 already links the recipe.)
- Reader harm: A reader wanting the no-helper path follows the link, scans pytest.md, finds nothing matching, and bounces.
- Suggested fix: Repoint fixtures.md line 7 to `recipes/testing-overrides.md` (cleaner), or add a resolve-based plain example to pytest.md.

#### D-18 — `pytest.md` Overrides section doesn't link the deeper recipe (low)
- Location: `docs/integrations/pytest.md` "Overrides" (lines 113-156)
- Lens: findability
- Issue: Explains overrides inline but never links `recipes/testing-overrides.md` (transactional-session pattern, reset-all), even though the recipe links back to pytest.md and every neighboring page reaches the recipe.
- Reader harm: A reader needing the real-DB override pattern stops at the two simple snippets and never finds the recipe.
- Suggested fix: Add a one-line pointer at the end of the section: "For deeper patterns (transactional DB sessions, resetting all overrides) see the [testing-with-overrides recipe](../recipes/testing-overrides.md)."

#### D-19 — `pytest.md` install block breaks numbered-list rendering (medium)
- Location: `docs/integrations/pytest.md` install block (lines 12-28)
- Lens: readability
- Issue: Verified in built HTML — the four onboarding steps render as four separate single-item `<ol>` blocks all showing "1." because the tab/code continuation content is flush-left (col 0) instead of indented to the list's content column, terminating the list. (The original finding inverted the cause; the fix direction is still correct.) Replicated across `index.md` and the four other integration pages.
- Reader harm: The numbered happy-path loses its step structure; every step shows "1."
- Suggested fix: Indent all continuation content (tabs + code) to nest under each numbered item, or restructure steps as headings. Apply consistently across the 6 affected files.

#### D-20 — `recipes/testing-overrides.md` uses bare `AsyncSession` in a `resolve()` call (low)
- Location: `docs/recipes/testing-overrides.md` Pattern 2 prose (line 66)
- Lens: consistency
- Issue: `container.resolve(AsyncSession)` uses a bare name, but the file imports `import sqlalchemy.ext.asyncio as sa_async` and uses the `sa_async.` prefix everywhere else (and the sibling sqlalchemy.md recipe does too).
- Reader harm: A reader sees two spellings of the same type and is unsure whether a bare import is expected; copied verbatim it's a `NameError`.
- Suggested fix: Use `container.resolve(sa_async.AsyncSession)`. (The "Pattern 1" mention in the original finding is spurious; Pattern 1 is unaffected.)

#### D-21 — `to-2.x.md` `.cast` removal has no migration recipe (medium)
- Location: `docs/migration/to-2.x.md` §6 and Breaking Changes item 6 (lines 222-242, 265)
- Lens: consistency
- Issue: Breaking-change item 6 says `.cast` is removed, but the guide never shows the before/after. The 1.x guide leans heavily on `.cast` (e.g. `db_engine=database_engine.cast`); `.cast` was the per-dependency wiring mechanism and is the single most pervasive edit in a real 1.x→2.x migration.
- Reader harm: A reader with a `.cast`-heavy 1.x codebase is told it's gone but given no recipe, so they reverse-engineer the new model from unrelated sections.
- Suggested fix: Add a short subsection mapping 1.x `.cast` to 2.x: provider deps → implicit type-based wiring (drop the arg); static values → `kwargs={...}`; context → ContextProvider-registered type. At minimum cover the common provider-dep case.

#### D-22 — `to-2.x.md` empty `with`/`async with` blocks are syntax errors (low)
- Location: `docs/migration/to-2.x.md` §5 first "After (2.x)" snippet (lines 209-214)
- Lens: readability
- Issue: Both blocks have only a comment (`# Use request_container`) as their body; a `with` block with no statement raises `SyntaxError` (confirmed via `ast.parse`).
- Reader harm: A reader copy-pasting gets an immediate `IndentationError`/`SyntaxError`.
- Suggested fix: Put a runnable placeholder statement in the block (e.g. `svc = request_container.resolve(MyService)` or `pass`).

#### D-23 — `contributing.md` clone block is missing `git clone` (medium)
- Location: `docs/dev/contributing.md` "Clone project" (lines 6-10)
- Lens: bug
- Issue: The block shows a bare SSH URL `git@github.com:modern-python/modern-di.git` followed by `cd modern-di`, with no `git clone` prefix.
- Reader harm: A first-time contributor copy-pasting gets a shell error and is blocked at the very first action.
- Suggested fix: Change the first line to `git clone git@github.com:modern-python/modern-di.git`; ideally also offer the HTTPS form.

#### D-24 — `contributing.md` offers SSH-only clone, no fork workflow (low)
- Location: `docs/dev/contributing.md` (line 8)
- Lens: onboarding
- Issue: Only an SSH clone URL is given; no HTTPS, and the typical open-source fork-then-PR workflow isn't mentioned.
- Reader harm: Contributors without SSH keys hit an auth failure; would-be PR authors don't know whether to fork or clone upstream.
- Suggested fix: Add the HTTPS URL alongside SSH and a one-line fork/PR pointer.

#### D-25 — `contributing.md` never explains how to submit work (medium)
- Location: `docs/dev/contributing.md` (whole page)
- Lens: convenience
- Issue: The page stops after "run the tests" — no branching, commit/PR conventions, the planning convention, or the 100% line-coverage gate (justfile enforces `--cov-fail-under=100`).
- Reader harm: A contributor finishes setup, opens a PR that fails CI on coverage/lint or ignores the planning convention, leading to rejected work.
- Suggested fix: Add a "Submitting changes" section (branch from main; run `just lint`/`just test`; note the 100% coverage gate; link `planning/README.md`; open a PR upstream). Link the planning convention rather than mandating its heavy Full lane for external contributors.

#### D-26 — `contributing.md` omits CI-equivalent commands (low)
- Location: `docs/dev/contributing.md` "Running tests" (lines 18-19)
- Lens: convenience
- Issue: Only `just test` is shown. CI runs the non-fixing/coverage variants (`just lint-ci`, `just test-ci`); local `just test` has no coverage check, so a green local run can still fail CI on the 100% gate.
- Reader harm: A contributor passes locally, pushes, and CI fails on coverage — a confusing round-trip.
- Suggested fix: Mention `just lint-ci`/`just test-ci` (note `test-ci` is the coverage-enforcing recipe), that CI runs the non-fixing variants, and the `just test PATH -k NAME` subset tip.

### README

#### R-1 — README has no install/usage (medium)
- Location: `README.md` (whole file)
- Lens: onboarding
- Issue: See **O-1** — merged. (Two agents flagged the identical defect: no install command, no code example.)
- Reader harm: First-time GitHub/PyPI visitor cannot reach first success on the page where most people start.
- Suggested fix: Add an Install line and a short copy-pasteable Quick Start mirroring `docs/index.md`; link out for the deep dive.

#### R-2 — README "Documentation" link has no Quick Start signpost (low)
- Location: `README.md` (line 33)
- Lens: convenience
- Issue: Getting-started/install/first example all sit behind a single bare "Documentation" link; no direct deep link to a Quick Start page.
- Reader harm: A reader wanting the fastest path lands on the docs home and must hunt the nav. (Mitigated by two working usage-template repo links already present.)
- Suggested fix: Inline a Quick Start (preferred, avoids dead-link risk) or add a direct "New here? Start with the Quick Start" deep link.

### architecture/

#### A-1 — `containers.md` "Lifecycle: close and reopen" leads with internals (low)
- Location: `architecture/containers.md` (lines 76-117)
- Lens: readability
- Issue: Dives straight into `close_sync`/`close_async`, LIFO `_creation_order`, `AsyncFinalizerInSyncCloseError`, and reopen semantics; the idiomatic `with Container(...) as c:` happy path appears only at the bottom, framed as reopen. (Mitigated: this is the deep-dive reference surface, not a tutorial.)
- Reader harm: A reader wanting "how do I clean up my container" wades through finalizer-ordering internals before the one-line answer.
- Suggested fix: Lead with a 2-3 line happy-path summary and a `with Container(...) as container:` snippet, then keep the LIFO/finalizer/reopen detail as the deep dive.

#### A-2 — `containers.md` imports `Group` via deep path (low)
- Location: `architecture/containers.md` (line 10) vs `architecture/providers.md` (line 15)
- Lens: consistency
- Issue: containers.md imports `Container`, `Scope` from the top level but `Group` via `from modern_di.group import Group`, while providers.md uses the idiomatic top-level `from modern_di import ... Group`. `Group` is a real top-level export.
- Reader harm: A reader cross-referencing sees two import paths for the same symbol and may doubt the top-level export.
- Suggested fix: Use `from modern_di import Container, Scope, Group` in containers.md. (`testing-and-overrides.md` line 65 has the same deep path; a full cleanup would touch it too.)

#### A-3 — `providers.md` omits `UnsupportedCreatorParameterError` (medium)
- Location: `architecture/providers.md` "Declaration-time signature parsing" / "Static kwargs"
- Lens: bug
- Issue: The "authoritative reference" enumerates declaration-time failures (`UnknownFactoryKwargError`, the `skip_creator_parsing` UserWarning) but omits `UnsupportedCreatorParameterError`, raised at declaration time for a parameterized-generic param (e.g. `list[int]`) with no default and not in `kwargs` (also fires for positional-only params without defaults).
- Reader harm: A newcomer with a `list[Foo]` constructor param gets a hard exception with an error class the docs never mention and can't map it to documented behavior.
- Suggested fix: Add a paragraph/table row documenting `UnsupportedCreatorParameterError` and its three escape hatches (pass via kwargs, add a default, `skip_creator_parsing=True`); mention both triggers (parameterized generics and positional-only).

#### A-4 — `providers.md` "Static kwargs — `kwargs={}`" heading shows the inert value (low)
- Location: `architecture/providers.md` (line 62)
- Lens: understanding
- Issue: The heading example `kwargs={}` is an empty (falsy) dict, which triggers none of the described behavior (validation runs only `if kwargs:`, merge only `if self._kwargs:`); the section is about *populated* kwargs and shows no populated example.
- Reader harm: A heading-skimmer copies an empty dict that does nothing, then is confused when no static value is injected.
- Suggested fix: Retitle to "Static kwargs" and show a populated example, e.g. `kwargs={"timeout": 30}` (using a real creator param name to avoid `UnknownFactoryKwargError`).

#### A-5 — `providers.md` omits `bound_type` for Alias/ContextProvider (low)
- Location: `architecture/providers.md` Alias and ContextProvider sections
- Lens: consistency
- Issue: Factory's section documents the optional `bound_type` param, but the Alias and ContextProvider sections don't note that both also accept it (alias.py:22, context_provider.py:21). The ContextProvider section never mentions it at all.
- Reader harm: A reader wanting to bind an Alias/ContextProvider to a Protocol/base type assumes it's Factory-only.
- Suggested fix: Note in both sections that `bound_type` overrides the inferred bound type, matching the Factory section.

#### A-6 — `testing-and-overrides.md` scope-chain example references an undeclared attribute (low)
- Location: `architecture/testing-and-overrides.md` "Testing scope chains" code block
- Lens: convenience
- Issue: Resolves `MyGroup.request_scoped_service`, but the earlier `MyGroup` declares only `service` and `repo` (both `Scope.APP`); no REQUEST-scoped provider was declared, so the reused snippet raises `AttributeError`.
- Reader harm: A reader copying it expecting the same `MyGroup` hits `AttributeError`.
- Suggested fix: Add `request_scoped_service = providers.Factory(scope=Scope.REQUEST, creator=...)` to the `MyGroup` block, or annotate that this snippet needs an added REQUEST-scoped provider.

### docstrings

#### DS-1 — `Container` class and `__init__` have no docstrings (low)
- Location: `modern_di/container.py` class `Container` (line 20), `__init__` (lines 33-74)
- Lens: onboarding
- Issue: The framework's central entry point has no class docstring and no `__init__` docstring. (Mitigated: the signature is heavily typed — `groups: list[type[Group]] | None`, `scope = Scope.APP` — so types convey much; runtime semantics like what `validate=True` does, `context`, root-vs-child registry sharing, and `use_lock` are not. Selective docstrings are the house style here.)
- Reader harm: A reader via IDE hover/`help()`/source gets no guidance on runtime semantics of the constructor they must call first.
- Suggested fix: Add a concise class docstring (role, root-vs-child, registries) and a short `__init__` docstring covering `validate`, `context`, and root-vs-child behavior.

#### DS-2 — `resolve` vs `resolve_provider` undocumented (low)
- Location: `modern_di/container.py` `resolve` (line 107), `resolve_provider` (line 117)
- Lens: understanding
- Issue: Two near-identically named public methods have no docstrings to disambiguate by-type vs by-reference resolution. (Mitigated by distinct typed signatures and ty/IDE feedback on misuse.)
- Reader harm: A reader sees both in autocomplete and may guess wrong (e.g. pass a type to `resolve_provider`).
- Suggested fix: Add one-liners: `resolve` — "Resolve a dependency by its type."; `resolve_provider` — "Resolve a specific provider by reference (also enforces closed-state and applies overrides)."

#### DS-3 — `Scope` IntEnum has no docstring (low)
- Location: `modern_di/scope.py` class `Scope` (lines 4-9)
- Lens: understanding
- Issue: Five bare integer assignments with no docstring; the load-bearing rule (higher int = deeper scope; a provider resolves only from a container at the same-or-deeper scope) lives only in external docs and error messages.
- Reader harm: A developer opening scope.py can't tell why the ordering matters or which way "deeper" goes.
- Suggested fix: Add a class docstring stating the integer-ordering and resolution constraint (mention APP/SESSION/... as default examples; the rule is about IntEnum ordering, since custom IntEnum scopes are allowed).

#### DS-4 — `ContextProvider` undocumented + silent-None behavior (low)
- Location: `modern_di/providers/context_provider.py` class `ContextProvider` (line 13)
- Lens: understanding
- Issue: No class docstring; `resolve()` returns `None` when no context value is set, with no in-source note of the silent-None behavior or how values are supplied (`build_child_container(context={...})`). (Partly mitigated by the `T_co | None` return annotation; no-class-docstring is house style.)
- Reader harm: A reader is surprised by `None` and has no in-source pointer to where the value is injected.
- Suggested fix: Add a class docstring: holds a runtime-injected value supplied at build time via `context={...}`, looked up at its bound scope, resolves to `None` when unset (and note the Factory-injection raise path — see X-9).

### Cross-cutting

#### X-1 — Missing-context behavior documented inconsistently across surfaces (medium)
- Location: `modern_di/providers/context_provider.py` `resolve()`, `architecture/providers.md` (lines 110-113), `docs/providers/context.md` (whole page)
- Lens: consistency
- Issue: `resolve()` returns `None` unconditionally on unset; architecture documents both that and the Factory caveat (injection into a non-nullable param raises `ArgumentResolutionError`); user-facing context.md is silent on the missing-value case entirely. Behavior differs by call path (direct resolve → None; non-nullable Factory injection → raises).
- Reader harm: A reader of only context.md expects `None`, ships code without nullable annotations/defaults, then hits an unexpected `ArgumentResolutionError` at request time.
- Suggested fix: Add a "Missing context value" subsection to context.md stating the two-path behavior, mirror the architecture wording, and cross-link `troubleshooting/context-not-set.md`.

#### X-2 — `duplicate-type-error.md` misnames the exception as `RuntimeError` (medium)
- Location: `docs/troubleshooting/duplicate-type-error.md` (lines 9-11)
- Lens: bug / consistency
- Issue: The error banner shows `RuntimeError: Provider is duplicated by type ...`, but the framework raises `DuplicateProviderTypeError` (a `RegistrationError` → `ModernDIError` → `RuntimeError`); a traceback prints the concrete class name. `errors-and-exceptions.md` and `recipes/multi-group.md` both name it correctly, so this page is the outlier. (Merges three findings flagging the same defect.)
- Reader harm: A user grepping the class name they saw never lands on the page that explains it; the page that exists to explain the error misnames it.
- Suggested fix: Change the banner to `DuplicateProviderTypeError: Provider is duplicated by type ...`, note it descends from `RegistrationError`/`ModernDIError` (so `except RuntimeError`/`except RegistrationError` both catch it), and cross-link `errors-and-exceptions.md`.

#### X-3 — `container.md` page conflates Container-provider, context-propagation, and library-author API (medium)
- Location: `docs/providers/container.md` "Advanced" (lines 96-137) and "Context Propagation" (lines 67-94)
- Lens: findability
- Issue: The "Container Provider" page also carries a low-level public-API reference and a context-propagation warning that duplicates `troubleshooting/context-not-set.md` cause #1 — neither discoverable from the page title, and the natural owner (`providers/context.md`) has no such discussion. (Supersedes D-10's narrower framing.)
- Reader harm: A library author looking for the low-level API or custom-provider docs won't open "Container Provider"; the context warning is duplicated with no page owning it.
- Suggested fix: Split the Advanced/API material into its own nav page; move/merge the context-propagation warning into `providers/context.md`.

#### X-4 — `to-2.x.md` `.cast` removal lacks a migration recipe (medium)
- Location: `docs/migration/to-2.x.md` §6 / Breaking Changes item 6
- Lens: consistency
- Issue: See **D-21** — the most pervasive 1.x→2.x edit has no worked before/after.
- Reader harm: A reader with `.cast`-heavy code is told it's gone with no recipe.
- Suggested fix: Add a `.cast`→type-based-wiring/`kwargs`/ContextProvider mapping subsection.

#### X-5 — "lifecycle" vs "lifetime" overloaded in `factories.md` (low)
- Location: `docs/providers/factories.md` (line 11) vs `docs/providers/scopes.md` (line 3), `docs/providers/lifecycle.md`
- Lens: consistency
- Issue: factories.md:11 says scope "Defines the lifecycle of the dependency," but scopes.md calls scope the "lifetime band" and there's a whole separate "Lifecycle" page about creation/caching/finalizers. The rest of the docs reserve "lifetime" for scope and "lifecycle" for create/cache/cleanup, so factories.md:11 is a lone outlier. (about-di.md:66 uses "Lifetime Management" — consistent, not an offender.)
- Reader harm: The overloaded word blurs the two mental models a newcomer must keep separate.
- Suggested fix: Change factories.md:11 to "Defines the lifetime (scope) of the dependency." Reserve "lifecycle" for the create/cache/cleanup page.

#### X-6 — `about-di.md` names the Group `AppModule` (low)
- Location: `docs/introduction/about-di.md` (lines 74, 133, 185)
- Lens: consistency
- Issue: Names its Group `AppModule`, while the rest of the site uses `Dependencies`/`AppGroup`/`MyGroup`. "Module" is a loaded DI term in other frameworks (injector/NestJS) that modern-di does not have.
- Reader harm: On the first conceptual page, a reader from another framework may hunt for a "Module" API that doesn't exist.
- Suggested fix: Rename to `AppGroup` or `Dependencies` (self-contained identifiers, safe rename).

#### X-7 — `about-di.md` uses singleton/scoped/transient vocabulary the site abandons (low)
- Location: `docs/introduction/about-di.md` "Lifetime Management in DI" (line 68, comments 75/82/89)
- Lens: understanding
- Issue: Introduces "singleton, scoped, transient," but modern-di's real model is scope (APP/SESSION/...) plus cache_settings present/absent. "Transient"/"scoped" appear nowhere else as categories; two REQUEST factories differ only by `cache_settings`, yet that distinguishing axis is never named.
- Reader harm: A reader learns three terms then never sees them again, may search for a non-existent "transient"/"scoped" provider option.
- Suggested fix: Map the three generic terms to modern-di's model in one sentence (scope = how long; `cache_settings` present = one shared instance, absent = fresh each resolve), then use only modern-di's terms.

#### X-8 — `about-di.md` uses `CacheSettings()` before it's introduced (low)
- Location: `docs/introduction/about-di.md` "Lifetime Management" (lines 70-94 and throughout)
- Lens: onboarding
- Issue: As the first Introduction page, uses `providers.CacheSettings()` (the singleton mechanism, explained pages deeper) before introducing it. (The undefined illustrative class names — `EmailService`, `DatabasePool`, etc. — are accepted concept-page convention and not a defect; the missing `uuid` import is O-10.)
- Reader harm: A zero-context reader meets `CacheSettings()` with no idea what it does, despite inline comments conveying the effect.
- Suggested fix: Add a one-line gloss the first time it appears: "`CacheSettings()` makes the provider a cached singleton — see Factories."

#### X-9 — `context-not-set.md` "depending on configuration" is vague and partly wrong (low)
- Location: `docs/troubleshooting/context-not-set.md` (line 3)
- Lens: understanding
- Issue: "the resolution fails (or returns `None`, depending on configuration)" — there is no "configuration" setting; the outcome depends on how the ContextProvider is consumed and on param nullability/default.
- Reader harm: A user debugging a context-not-set crash leaves with no actionable rule.
- Suggested fix: Replace with the actual rule, taking care with the default branch: a directly-resolved ContextProvider returns `None`; injected into a Factory param with no value it raises `ArgumentResolutionError`, **unless** the param has a default (the default is used — `None` is *not* injected) or is nullable `X | None` (then `None` is injected).

#### X-10 — `creator` vs "factory function" terminology (low)
- Location: `architecture/providers.md` (line 29), `docs/introduction/resolving.md` (line 12)
- Lens: consistency
- Issue: The API param is `creator=`. providers.md:29 says "a constructor or factory function" — "factory function" sits one clause from the `Factory` provider class name, inviting conflation. (Most other "factory function" uses are harmless generic prose; this adjacency is the real case.)
- Reader harm: A reader can't tell whether "factory function" means the `creator` callable or the `Factory` provider.
- Suggested fix: Standardize on "creator"/"creator callable" where a doc means the `creator=` argument; reserve "Factory" for the provider type. Fix providers.md:29 primarily.

#### X-11 — `resolving.md` omits the nullable-None fallback (low)
- Location: `docs/introduction/resolving.md` (line 12) vs `architecture/resolution.md` Step 4 (lines 75-79)
- Lens: understanding
- Issue: resolving.md states only the default fallback and covers unions, but never mentions the `X | None` → inject-`None` fallback (documented in factories.md and resolution.md). The full rule is default > nullable-None > raise.
- Reader harm: A reader using resolving.md as their model expects a missing optional with no default to raise, but it silently receives `None`.
- Suggested fix: Add one cross-linking sentence near the union sentence: a param typed `X | None` with no provider and no default receives `None` rather than raising — see Factories: Optional parameters.

#### X-12 — `alias.md` "removed in 3.0" contradicts code/architecture "a future release" (low)
- Location: `docs/providers/alias.md` (line 19) vs `architecture/providers.md` (lines 137-141) and `modern_di/providers/alias.py` (line 28)
- Lens: consistency
- Issue: User docs promise the deprecated Alias `scope=` is "removed in 3.0," but the authoritative architecture doc and the runtime DeprecationWarning both say only "a future release." (Practical harm is near-zero since `scope=` is an ignored no-op.)
- Reader harm: A user may schedule removal for their 3.0 bump and be surprised, or treat it as more urgent than intended.
- Suggested fix: Drop "3.0" from alias.md to match "a future release" (align docs to the runtime string unless 3.0 is genuinely planned).

#### X-13 — `design-decisions.md` "five providers" mixes categories (low)
- Location: `docs/introduction/design-decisions.md` §5 (line 32)
- Lens: consistency
- Issue: Lists "five providers (`Factory`, `Alias`, `ContextProvider`, `container_provider`, `AbstractProvider`)," but `AbstractProvider` is the non-instantiable base and `container_provider` is a pre-built instance — only three are user-instantiable provider types. Undercuts the "small core" message. (Merges two findings of the same issue; architecture/providers.md documents these under distinct headings.)
- Reader harm: A newcomer counting "five providers" may try `AbstractProvider(...)` or look for a `container_provider` constructor and fail.
- Suggested fix: Reword: "three concrete provider types (`Factory`, `Alias`, `ContextProvider`), plus the `AbstractProvider` base and the pre-built `container_provider` singleton."

#### X-14 — "Automatic dependencies graph" is ungrammatical (low)
- Location: `README.md` (line 20) and `docs/index.md` (line 7)
- Lens: consistency
- Issue: The first feature bullet reads "Automatic dependencies graph" (should be singular attributive "dependency graph") in both the README and docs landing. (The "object graph"/"provider graph" variants elsewhere are context-appropriate, not errors — reject the global-normalization suggestion.)
- Reader harm: The very first feature bullet a prospective user reads is grammatically off — a small credibility ding.
- Suggested fix: Fix both to "Automatic dependency graph." Leave "object graph"/"provider graph" as-is where used precisely.

#### X-15 — `index.md` "Where to next" skips the Introduction pages (low)
- Location: `docs/index.md` "Where to next" (lines 122-126)
- Lens: findability
- Issue: The handoff links to Scopes, Lifecycle, Recipes but skips `introduction/resolving.md` (the auto-wiring mechanism just demonstrated) and `providers/factories.md` (the provider just used), routing around the entire Introduction section.
- Reader harm: A reader following the in-page "next" links never reaches the page explaining the type-based resolution they just used. (Mitigated: the full nav sidebar lists both pages in conceptual order.)
- Suggested fix: Add "Resolving — how type-based auto-injection works" and "Factories — the provider you just used" to the list, ideally first.

#### X-16 — Two troubleshooting pages lack a "See also" section (low)
- Location: `docs/troubleshooting/circular-dependency.md` and `docs/troubleshooting/duplicate-type-error.md`
- Lens: findability
- Issue: 3 of 5 troubleshooting pages (scope-chain, missing-provider, context-not-set) end with a "See also" linking the concept/error pages; these two don't. circular-dependency.md leans on `validate()` but never links `lifecycle.md#validation` or the errors page; duplicate-type-error.md never links `factories.md#bound_type`, the errors page, or its stated inverse missing-provider.md (which links *to* it). (Merges page-level and cross-cutting findings.)
- Reader harm: A reader landing on either page via search has no one-click path to the conceptual explanation; inconsistent with siblings.
- Suggested fix: Add "See also" sections matching the others. duplicate-type-error.md → `providers/factories.md#bound_type`, `providers/errors-and-exceptions.md`, `troubleshooting/missing-provider.md`, and a note that `Alias` is preferred over duplicate factories for abstract-to-concrete binding. circular-dependency.md → `providers/errors-and-exceptions.md`, `providers/lifecycle.md#validation`.

#### X-17 — `duplicate-type-error.md` quotes a truncated error message (low)
- Location: `docs/troubleshooting/duplicate-type-error.md` "Understanding the Error"
- Lens: bug
- Issue: The real `PROVIDER_DUPLICATE_TYPE_ERROR` message is multi-line (numbered "To resolve this issue: 1...2..." plus a "See https://..." URL); the doc quotes only the first sentence. (Related to X-2, which also corrects the class name.)
- Reader harm: A reader comparing the doc's quoted error to their console finds them noticeably different and may doubt they're on the right page (mitigated — the lead sentence matches).
- Suggested fix: Quote the full message as emitted, or note that the runtime message also embeds the resolution steps and a backlink to this page.
