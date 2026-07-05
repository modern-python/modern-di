# modern-di 3.0 UX & interface research report (2026-07-05)

## 1. Summary

**Question.** With one breaking-change budget available at the 3.0 major, which interface, diagnostics,
documentation, and integration-shape changes does the comparative evidence from the wider DI field justify —
and which field practices should modern-di consciously continue to refuse?

**Method (short form).** A four-phase comparative study: (1) a ground-truth digest of modern-di v2.23 built
exclusively from this repo's `architecture/` files and source; (2) per-framework research notes on 13
comparison frameworks, built from official docs, primary sources, and issue trackers; (3) four per-surface
syntheses (core API ergonomics, errors & diagnostics, docs & onboarding, integration shape) organized by
cross-framework pattern; (4) candidate generation constrained by modern-di's four fixed design constraints,
followed by adversarial verification of every candidate against repo source and live upstream sources.

**Comparison set (13).** Python: dishka, wireup, svcs, that-depends, dependency-injector, python-injector,
FastAPI `Depends`. Beyond Python: Spring, .NET MEDI, Koin, Dagger 2 (+Hilt), Uber Fx (dig), Angular DI.

**Counts.** 31 candidates generated; 30 survived adversarial verification (19 confirmed as written, 11
amended in problem/precedent/sketch wording, with corrections folded in below); 1 refuted (appendix).
30 field practices were consciously rejected against the fixed constraints (section 4). Four shortlist
entries are cross-surface duplicates of another entry (API-1≡ERR-2, API-7≡ERR-1, API-8≡INT-3, ERR-4≈DOC-6);
they are ranked adjacently and cross-referenced, not merged, since each carries surface-specific evidence.

**Breaking-budget usage.** Only three distinct decisions consume the budget: default-on validation
(API-1/ERR-2), sync-generator creators (API-2), and raising on direct resolve of an unset ContextProvider
(API-6). Everything else is additive or docs-only.

**Rulings (2026-07-05).** All 26 distinct decisions ruled by the maintainer: **22 accepted**, **2 rejected**
(API-2 generator creators — `planning/decisions/2026-07-05-no-generator-creators.md`; API-3 `enter_scope`
alias — `planning/decisions/2026-07-05-no-enter-scope-alias.md`), **2 deferred** (ERR-8 resolution tracing,
INT-6 conformance suite — `planning/deferred.md`). Per-candidate rulings inline in section 5. With API-2
rejected, the breaking budget carries two decisions: API-1/ERR-2 and API-6.

**Top 5 by impact:**

| # | Candidate | One-line case |
|---|---|---|
| 1 | API-1 / ERR-2 — validate on by default | Best validation content in the study, shipped off; every framework that revisited this moved to default-on |
| 2 | DOC-1 — publish `to-3.x.md` before the tag | All three queued 3.0 breaks already warn on 2.x; a warnings-as-errors recipe makes a green 2.x suite a 3.0 guarantee |
| 3 | ERR-1 / API-7 — runtime cycle guard | The default cycle experience today is a raw `RecursionError` — the field's worst-cited bug class |
| 4 | API-2 — yield-based Factory teardown | Every Python peer spells teardown as code-after-yield; modern-di alone requires a second object |
| 5 | API-6 — raise on unset ContextProvider direct resolve | Kills the one silent-None path that contradicts modern-di's own error philosophy |

**Overall position.** modern-di is already on the winning side of the field's big arguments: type-hint
autowiring, schema/runtime split (Group vs Container), hierarchical scopes, context-dict scope entry,
flag-not-taxonomy caching, all-errors validation aggregation, "did you mean" suggestions, declaration-time
signature failure, tree-wide auto-clearing overrides, and a real pytest package where the field has none.
The residual gaps are ergonomic deltas against dishka and wireup (validation default, yield teardown,
registration spelling) plus diagnostics polish (cycle guard, scope-error breadcrumbs, graph export) and a
set of cheap, high-leverage docs pages.

## 2. Method

**Phases.**

1. **Ground truth.** `ground-truth.md` digest written from `architecture/*.md` and `modern_di/` source only;
   the repo governs all modern-di claims. Recent 2026-06 UX work (error-message rework, `suggester.py`,
   `Factory(cache=)`, docs audits) and the three queued 3.0 breaks were recorded as do-not-re-propose
   context.
2. **Per-framework notes.** One notes file per comparison framework (13 files, scratchpad), each covering
   registration shape, scope model, teardown, validation timing, error anatomy, docs/onboarding, testing,
   and integration surface, with URL citations to official docs, source, and issue trackers.
3. **Per-surface synthesis.** Four findings files organized by cross-framework pattern rather than by
   framework, each ending in a modern-di position statement (condensed in section 3).
4. **Candidate generation + adversarial verification.** Candidates were drafted per surface, each carrying a
   constraint check against the four fixed constraints. A separate verification pass then checked every
   candidate on four axes: (a) problem statement re-verified against repo source (file:line where possible,
   with local reproduction runs for behavioral claims); (b) precedent re-verified against live primary
   sources (official docs, raw source files on GitHub, `gh api` for issues/releases); (c) constraint
   compliance; (d) the `breaking` flag. Verdicts: **confirmed**, **amended** (defect in wording/sketch
   corrected, candidate stands), or **refuted** (dropped to appendix). Amendments are folded into the
   candidate text in section 5.

**Constraints held fixed** (candidates violating any were routed to the rejected pool, not the shortlist):

1. Zero dependencies.
2. Sync-only resolution (finalizers may be sync or async).
3. No global state.
4. Conservative feature set.

**Coverage gaps.** This is a comparative documentation/source study, not usability testing — no user
interviews or task timing; "onboarding friction" is inferred from concept counts and community evidence
(issues, HN/blog criticism). Performance benchmarking and typing-plugin/static-analysis surfaces were out of
scope. Sibling integration repos (fastapi, faststream, typer, pytest, aiohttp, starlette, litestar) were
read as source evidence for the integration surface but not themselves audited. Framework versions are as of
2026-07; fast-moving peers (dishka, wireup, FastAPI) may drift.

## 3. Comparative findings by surface

### 3.1 Core API ergonomics

Condensed from `findings-core-api.md`; pattern-organized.

- **Registration families.** Three families: class-attribute namespaces (dependency-injector, that-depends,
  modern-di's Group), decorator-on-definition (wireup `@injectable`, dishka `@provide`, Angular
  `@Service()`, Dagger `@Inject`), and imperative calls (svcs `register_factory`, MEDI `AddSingleton`, Fx
  `fx.Provide`, Koin DSL). Inside the first family, modern-di alone separates schema (Group) from runtime
  (Container); dependency-injector and that-depends make the class both, and that-depends' README now points
  new projects at modern-di (https://github.com/modern-python/that-depends). Type-hint autowiring won the
  field; explicit-wiring laggards draw the boilerplate criticism
  (https://blog.wasinski.dev/comparison-of-dependency-injection-libraries-in-python). The market pull is
  toward shorter registration: dishka `provide(Service)`, Koin `singleOf(::Ctor)`, Angular v22 `@Service()`.
  modern-di's keyword-only `creator=` is the outlier — no peer requires a keyword before the class name.
  A second repetition tax: every provider in a Group re-states its scope; dishka sets it once per
  `Provider(scope=...)` (https://dishka.readthedocs.io/en/stable/provider/index.html).
- **Scope vocabulary.** The field lingua franca is flat singleton/scoped/transient (MEDI, wireup, Koin);
  MEDI is explicit that "Scopes aren't hierarchical"
  (https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection-guidelines). Only dishka
  (`APP → REQUEST → ACTION → STEP`, same long-cannot-depend-on-short rule,
  https://dishka.readthedocs.io/en/stable/advanced/scopes.html) and modern-di ship an ordered hierarchy;
  Dagger proves the demand by making users DIY it with `@Subcomponent`, which Hilt exists to fix
  (https://dagger.dev/hilt/). Residual friction is translation (a docs problem) and the auto-increment
  landing on SESSION where web code always wants REQUEST.
- **"Create once".** Three spellings: provider-class taxonomies (dependency-injector, that-depends — which
  multiply and generate feature-matrix requests,
  https://github.com/modern-python/that-depends/issues/114), lifetime words (MEDI, wireup, Koin), and a
  caching flag (dishka cache-by-default). modern-di's `Factory(cache=True)` matches MEDI's
  transient-as-safe-default guidance; no change warranted beyond vocabulary docs.
- **Teardown.** Python converged on generator factories: dishka
  (https://dishka.readthedocs.io/en/stable/provider/provide.html), wireup, svcs, FastAPI yield-dependencies,
  that-depends `Resource`. modern-di alone spells teardown as a second object
  (`CacheSettings(finalizer=...)`) — more explicit, and uniquely able to support async finalizers under sync
  resolution, but a second concept for every migrant. A sync-generator creator form meets the field's muscle
  memory without touching the sync-only constraint.
- **Scope entry.** dishka: `with container(context={Request: r}):`; wireup:
  `container.enter_scope({RequestContext: ctx})`
  (https://maldoinc.github.io/wireup/latest/lifetimes_and_scopes/); MEDI: `CreateScope()` (no context
  channel at all); modern-di: `build_child_container(scope=..., context=...)` — the longest name in the
  field, mechanism-named rather than intent-named. On the context half modern-di is at the field's front:
  `context={Type: obj}` equals dishka's design and beats MEDI, Spring's thread-locals, and Koin's
  `parametersOf`. One inconsistency: a directly resolved, unset ContextProvider returns `None` (the Angular
  "may be null" pattern, https://angular.dev/api/core/REQUEST) while dependent-parameter absence raises.
- **Resolution addressing.** By-type is the modern norm; by-provider-reference is modern-di's testing
  superpower (FastAPI keys `dependency_overrides` the same way); by-string-name is the failure-prone end
  (dependency-injector has no by-type API at all,
  https://python-dependency-injector.ets-labs.org/wiring.html). modern-di offering exactly the first two is
  correct; renaming `resolve` to `get` is not worth churn given wireup's serial-rename cautionary tale
  (https://maldoinc.github.io/wireup/latest/upgrading/).
- **Validation timing.** Every framework that revisited it moved earlier and default-on: dishka default with
  `skip_validation=True` (https://dishka.readthedocs.io/en/stable/errors.html), wireup unconditional
  (https://maldoinc.github.io/wireup/latest/what_wireup_validates/), Spring via eager singletons
  (https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html), Dagger
  at compile time, Koin's checkModules → `verify()` → K2 compiler plugin trajectory
  (https://insert-koin.io/docs/setup/compiler-plugin). The lazy laggards are the criticized ones (Fx,
  https://hn.algolia.com/api/v1/items/30487792; dependency-injector #811). modern-di has the best content
  (all-errors aggregation) behind an off-by-default flag, and shares the laggards' raw-`RecursionError`
  cycle experience when unvalidated.
- **Naming scorecard.** Good: `Scope`, `Container`, `Group`, `Alias`, `ContextProvider`,
  `override/reset_override`, `Factory(cache=)`. Watch: `build_child_container` (see above); `Factory` means
  transient to dependency-injector migrants; `Scope` collides with FastAPI's `Depends(scope=)`
  teardown-timing parameter since 0.121.0 (https://github.com/fastapi/fastapi/pull/14262).

### 3.2 Errors & diagnostics

Condensed from `findings-errors-diagnostics.md`.

- **Error-timing tiers.** Compile-time (Dagger; Koin's plugin endgame) → container-creation default (dishka,
  wireup, Spring) → opt-in (modern-di, MEDI `ValidateOnBuild`, Fx `ValidateApp`) → first-resolve-only
  (injector, svcs, Angular, that-depends, dependency-injector) — where the loudest criticism lives
  (https://rednafi.com/go/di-frameworks-bleh/). modern-di's declaration-time signature parsing fires earlier
  than any runtime framework's container-build check, but whole-graph validation defaults off — the only
  studied framework with whole-graph validation where it does. Its all-errors aggregation
  (`ValidationFailedError.errors`, ahead of wireup's first-error-only) is a differentiator worth
  advertising.
- **Error anatomy.** The dependency trace is the gold standard — so normative for Dagger that users file
  bugs when one error class lacks it (https://github.com/google/dagger/issues/1023); dig/Fx add file:line
  per hop. Anti-pattern end: Angular's `NullInjectorError` repeats one token
  (https://github.com/angular/angular/issues/46189); svcs has no message at all. modern-di's breadcrumbs are
  in the leading tier, with two gaps: scope errors (`ScopeNotInitializedError`/`ScopeSkippedError`) carry no
  breadcrumbs (factory.py:253 only catches `ResolutionError`), reproducing the Dagger-#1023 wrong-blame
  mode; and no definition sites (`ResolutionStep` is `(scope, name)` only, vs dig's
  `provided by pkg.NewFoo (file.go:42)`,
  https://raw.githubusercontent.com/uber-go/dig/master/cycle_error.go).
- **Did you mean.** Only dig/Fx (https://raw.githubusercontent.com/uber-go/dig/master/error.go) and
  modern-di ship fuzzy suggestions. A marketable differentiator; keep.
- **Remediation slot.** Spring Boot reformats every recognized failure as `Description:`/`Action:`; wireup
  embeds remedy text plus a docs URL in the message; Angular gives every error a stable NGxxxx code and page
  (https://angular.dev/errors/NG0201). modern-di remediation is ad hoc: one docs URL
  (`DuplicateProviderTypeError`) across ~20 exception classes.
- **Cycles.** Spring and dishka independently converged on drawing the cycle (ASCII diagrams,
  https://dishka.readthedocs.io/en/stable/errors.html); injector proves a runtime path-carrying cycle error
  is feasible in Python
  (https://raw.githubusercontent.com/python-injector/injector/master/injector/__init__.py). modern-di is
  top-tier under `validate()` and bottom-tier without it: raw `RecursionError`, the dependency-injector
  #811 experience (https://github.com/ets-labs/python-dependency-injector/issues/811).
- **Introspection.** The clearest absolute gap: Fx auto-provides `fx.DotGraph` in every container
  (https://pkg.go.dev/go.uber.org/fx); dishka ships `plotter.render_d2()/render_mermaid()`
  (https://dishka.readthedocs.io/en/stable/advanced/plotter.html); Spring has `/actuator/beans`. modern-di
  has nothing user-facing, though the graph exists internally (`get_dependencies` backs `validate()`), and
  zero logging anywhere in the package (verified by grep).
- **Misleading errors.** modern-di structurally avoids the field's cautionary tales (FastAPI's
  forgotten-Depends message, https://github.com/fastapi/fastapi/issues/5861; dependency-injector's silent
  raw-marker `AttributeError`, https://github.com/ets-labs/python-dependency-injector/issues/658) via
  `CreatorCallError` separation and no marker subsystem. The one remaining wrong-blame case is the
  breadcrumb-less runtime scope error.
- **Multi-error reports.** `ValidationFailedError.__str__` is a count header plus flat `- {error}` lines —
  serviceable, but unstructured against Spring's diagram-plus-Action banner for a 30-error graph.

### 3.3 Docs & onboarding

Condensed from `findings-docs-onboarding.md`.

- **Concept count predicts friction, not step count.** svcs and FastAPI reach first success on 2 concepts;
  wireup on ~4 (https://maldoinc.github.io/wireup/latest/getting_started/); dishka and modern-di on 5-6;
  dependency-injector's flagship tutorial lands its first injection ~60% in
  (https://python-dependency-injector.ets-labs.org/tutorials/flask.html); Dagger needed a second product
  (Hilt) to pay down onboarding debt. modern-di's quickstart front-loads two scopes, `cache=True`, and
  `build_child_container` before the first resolve; an APP-only Group + `resolve(T)` is an honest
  2-3-concept path. The shortest field paths cheat (injector `auto_bind`, Spring automagic,
  https://news.ycombinator.com/item?id=37830502) — the target is the shortest honest path.
- **Mental-model order.** modern-di teaches the right family ("business code stays plain") but then jumps to
  container mechanics before the reader has resolved anything. A portable device: MEDI's lifetime demo —
  resolve twice, print identity, observe rather than assert
  (https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection-usage).
- **IA.** modern-di's funnel (Quickstart → Introduction → Providers → Integrations → Recipes → Testing →
  Troubleshooting → Migration) is field-standard and partly ahead: a per-error troubleshooting section is
  matched only by Angular's NGxxxx registry and dishka's errors page. Gaps: no exception→URL contract
  (wireup puts the docs URL in the message itself); no `llms.txt` (that-depends, same org, publishes one —
  https://that-depends.modern-python.org/llms.txt); no anti-patterns page (injector's
  https://injector.readthedocs.io/en/latest/practices.html and MEDI's guidelines are the models); no
  enumerated non-goals (MEDI's "use the built-in container unless…" list is the standout precedent).
- **Vocabulary.** The field has no shared lifetime vocabulary; "create once" is spelled ten different ways,
  and modern-di deliberately has no Singleton class — the likeliest "where is X?" moment. svcs spends real
  docs estate on a glossary (https://svcs.hynek.me/en/stable/glossary.html). Urgent for the FastAPI
  audience: since 0.121.0 `Depends(scope=...)` means teardown timing, not lifetime
  (https://github.com/fastapi/fastapi/releases/tag/0.121.0), and FastAPI's app-scope gap is a top incoming
  motivation (https://vladiliescu.net/better-dependency-injection-in-fastapi/).
- **Migration guides.** wireup's per-version upgrading page is the strongest Python precedent
  (https://maldoinc.github.io/wireup/latest/upgrading/); that-depends shipped a dedicated v4 page. modern-di
  owns the good internal precedent (`to-1.x.md`, `to-2.x.md`, the 2.23 ContainerClosedWarning design is
  exactly the FutureWarning pattern) but has no `to-3.x.md` yet, for a release whose breaks already warn in
  production code. Competitive-migration guides are a proven acquisition channel: `from-that-depends.md`
  already paid off; dependency-injector (~4.9k stars, silent-failure wiring, boilerplate criticism) is the
  obvious unexploited target (https://maldoinc.github.io/wireup/latest/migrate_to_wireup/ shows the play).

### 3.4 Integration shape

Condensed from `findings-integration-shape.md`.

- **Packaging.** The field bundles integrations into core (dishka ~20, wireup 10, svcs 5, that-depends
  extras); modern-di splits into sibling repos. The split keeps zero-dependency airtight — a claim
  that-depends failed in practice (4.0.2 clean-install `ModuleNotFoundError`) — but forfeits uniformity: the
  shared machinery is copy-pasted per repo.
- **The three-piece contract.** The field converged on setup verb + container accessor + handler marker
  (dishka `setup_dishka`/`FromDishka[T]`, wireup `setup`/`Injected[T]`, svcs `init_app`/`svcs_from`).
  modern-di's siblings follow it consistently (`setup_di`, `fetch_di_container`, `FromDI`), and the contract
  is now written down (docs/integrations/writing-integrations.md). Remaining gap: the
  `isinstance(dep, AbstractProvider)` marker dispatch is re-implemented in seven sibling packages because
  core has no single provider-or-type entry point.
- **Registry reach-in.** Integrations contribute request-object providers via
  `container.providers_registry.add_providers(...)` — a two-attribute-deep un-blessed seam, at odds with the
  2026-06 privatization direction (commit 91c694a). dishka integrations do the same job through ordinary
  provider registration (https://dishka.readthedocs.io/en/stable/advanced/context.html); MEDI's
  `Add{GROUP NAME}` extension-method convention is the documented seam every .NET library uses
  (https://learn.microsoft.com/en-us/aspnet/core/fundamentals/dependency-injection?view=aspnetcore-9.0).
- **Lifespan.** modern-di supports both lifespan styles (async-with reopen; `open()`/`close_async`
  callbacks) — the reopenable-container design is a genuine piece of integration API most of the field
  lacks. Missing lever: eager construction at boot. Spring, Koin (`createdAtStart` +
  `createEagerInstances()`), that-depends and dependency-injector (`init_resources()`) all have one;
  `validate()` never runs creators, so a bad DB URL surfaces on the first request.
- **Request boundary.** modern-di sits in the field's best cluster (context-at-scope-entry, with dishka and
  wireup), and is ahead on connection-kind mapping (Request → REQUEST, WebSocket → SESSION; only dishka
  documents the same distinction) and on the Typer CLI ladder (command → REQUEST, `action_scope()` —
  a use case Fx users ask for and don't get, https://github.com/uber-go/fx/issues/755). wireup's
  raising-placeholder-factory variant leaked a production regression
  (https://github.com/maldoinc/wireup/issues/118).
- **Handler injection.** modern-di's split — ride host-native DI where it exists (`FromDI` returns a plain
  `fastapi.Depends`), minimal decorator where none does (Typer) — matches best practice and avoids the
  monkey-patching family's silent failure mode
  (https://github.com/ets-labs/python-dependency-injector/issues/658).
- **Testing contract.** modern-di's tree-wide runtime override with auto-clear at root close is among the
  most flexible in the field. What it lacks is the self-resetting context-manager form both
  dependency-injector (https://python-dependency-injector.ets-labs.org/providers/overriding.html) and wireup
  (https://maldoinc.github.io/wireup/latest/testing/) treat as the primary testing spelling. On plugins,
  nobody in the Python field ships a first-party pytest plugin; modern-di-pytest is a differentiator.
- **Conformance.** Seven sibling repos re-implement one contract with no shared test suite; wireup's 2.8→2.9
  `middleware_mode` regression (https://github.com/maldoinc/wireup/issues/118) shows the structurally
  available failure mode. .NET ships the exact mechanism as
  Microsoft.Extensions.DependencyInjection.Specification.Tests
  (https://www.nuget.org/packages/Microsoft.Extensions.DependencyInjection.Specification.Tests).

## 4. Consciously rejected field practices

Recorded so 3.0 declines these deliberately rather than by omission. "Violates" names the fixed constraint
or standing principle; where a practice recurred across surfaces it appears once per surface framing, as in
the study.

| Practice | Who does it | Violates | Note |
|---|---|---|---|
| Framework integrations inside the core package (onboarding framing) | dishka (~20), wireup (10), svcs, that-depends | Conservative feature set; settled separate-repos architecture; zero-dep erosion | Couples core cadence to framework churn (wireup #118 shipped as a core release); quickstart Option A links and writing-integrations.md already carry the docs weight |
| Async-first quickstart/examples | that-depends, wireup | Sync-only resolution | Would contradict the 2.x design decision; docs correctly teach sync resolve, async only for finalizers |
| Global-context bootstrapping for shorter hello-world | Koin `startKoin`, that-depends metaclass registry, dependency-injector wiring | No global state | Buys 1-2 quickstart lines, pays with a class of test-isolation docs (Koin's own leak warnings); explicit container passing is the differentiator |
| Zero-registration first success via implicit auto-binding | injector `auto_bind=True`, Spring component scanning | Conservative feature set; declaration-time-failure design bet | Silently defers missing-dep errors (injector) or breeds automagic archaeology (Spring); compete on the shortest honest path |
| Long build-a-whole-app flagship tutorials | dependency-injector (10-section Flask), Dagger 2 (14-section ATM) | None — rejected on field evidence | The two longest tutorials belong to the two worst onboarding reputations; short quickstart + recipes is the healthier shape |
| Graph visualization taught as onboarding | dishka plotter, Fx DotGraph, Spring actuator | Conservative feature set (as a docs commitment) | A core-API question, not a docs one — see ERR-7; docs substitute is `validate=True` in every example |
| Continuous API renaming cushioned by FutureWarning aliases | wireup (three naming generations in ~2 years) | Conservative feature set (stability is part of conservatism) | Adopt the cushioning mechanics (DOC-1) without the churn that made them necessary |
| Async resolution (await get / async factories / doubled API) | dishka, wireup, that-depends (whole API doubled) | Sync-only resolution | MEDI is the vendor-documented refusal precedent (https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection-guidelines); async finalizers cover the real need |
| Marker-based wiring subsystem (`@inject` + `Provide[...]` + `wire()`) | dependency-injector, that-depends, dishka (integration-scoped) | Conservative feature set | Top failure is silent: unwired functions get the raw marker (https://github.com/ets-labs/python-dependency-injector/issues/658); integrations resolve from the request container instead |
| Global container/context state | Koin, that-depends, FastAPI `app.dependency_overrides` | No global state | Koin's test docs warn to stop the global context between tests (https://insert-koin.io/docs/reference/koin-test/testing); instance-scoped Container sidesteps the bug class |
| Provider-class-per-lifetime taxonomy | dependency-injector, that-depends | Conservative feature set | Multiplies lifetime × thread-safety × sync/async, generates feature-matrix requests (https://github.com/modern-python/that-depends/issues/114); do not reintroduce even as migrant aliases |
| Auto-binding / recursive auto-registration | injector, dishka `recursive=True`, FastAPI `Depends()` class shortcut | Conservative feature set | Directly opposes the declaration-time `UnsupportedCreatorParameterError` guarantee — a differentiator worth protecting |
| Stringly-keyed registration/resolution | Koin `named()`, dependency-injector `Provide["x"]`, that-depends string paths, MEDI keyed services | Conservative feature set | Typos become runtime errors with no static help; `typing.NewType` + `bound_type` covers the multi-instance case — document the idiom |
| Ambient thread-local request context / cross-scope proxies | Spring `RequestContextHolder` + scoped proxies, MEDI `IHttpContextAccessor` | No global state | Source of Spring's most famous error; explicit child-container-with-context avoids the class structurally — a marketing point, not a gap |
| Bundling integrations in core (core-api framing) | dishka, wireup, svcs, that-depends | Conservative feature set | Separate-repo model is a standing decision (CLAUDE.md); integration repos own the sugar |
| Multibinding / collection injection | MEDI `IEnumerable<T>`, Spring, injector multibind, Angular `multi: true` | Conservative feature set | New registry semantics (multiple providers per type contradicts the type→provider map); revisit only on concrete post-3.0 demand |
| Auxiliary runtime services in core (pings, event logs, plotters) | svcs pings, Fx event log + DotGraph, dishka plotter | Conservative feature set | Each is an orthogonal subsystem; graph export weighed separately under ERR-7; pings belong in app code or integrations |
| Compile-time / codegen validation | Dagger, Koin K2 plugin, Google wire | Conservative feature set; zero deps for plugin distribution | Requires owning a toolchain component; declaration-time parsing + default-on validate() captures most of the value at zero toolchain cost |
| Validate-by-default via eager instantiation | Spring (eager singletons at refresh) | Conservative feature set (runs user side effects as "validation") | modern-di's validate() walks the graph without calling creators — strictly safer; eager init is a lifecycle feature (API-8/INT-3), not validation |
| Unconditional validation with no opt-out | wireup ("if the container starts, it works") | Conservative feature set (removes a legitimate escape hatch) | Default-on with explicit opt-out (dishka model, ERR-2) gets the same day-one experience; wireup also stops at first error — modern-di's aggregation is the better half |
| Environment-dependent diagnostics defaults | MEDI (`ValidateScopes` only in Development) | No global state (ambient env sniffing); conservative feature set | Dev/prod divergence is MEDI's documented footgun — captive deps ship silently to production; one behavior everywhere, chosen via the explicit flag |
| Built-in health pings and web introspection endpoints | svcs `get_pings()`, Spring `/actuator/beans` | Conservative feature set; endpoints belong to integration repos | If ever wanted, composes on top of ERR-7 + public registries from an integration package |
| Pluggable structured event-logger subsystem | Fx `fxevent.Logger`, Koin Logger abstraction | Conservative feature set (a public event API to maintain forever) | The narration value is real (ERR-8) but should ride stdlib logging, not an invented event vocabulary |
| Nullable/silent-None injection of unavailable context | Angular SSR `REQUEST` "may be null", MEDI `GetService<T>` null | Explicit-errors design principle | Masks wiring bugs as downstream `NoneType` errors; nullability stays the user's explicit choice (`X | None`, `absent_disposition`) — see API-6 |
| Bundled integrations for discoverability (integration-shape framing) | dishka, wireup, svcs, that-depends, Koin monorepo | Zero dependencies; conservative feature set | that-depends 4.0.2's clean-install failure shows the erosion in practice; recover uniformity via INT-2 + the written contract + INT-6 instead |
| Monkey-patching wiring for handler injection | dependency-injector (`wire(modules=)`) | Conservative feature set | The field's top silent integration failure (issues #658/#521/#328); integrations correctly ride host-native DI |
| Async resolution surface for integrations | dishka, wireup, that-depends | Sync-only resolution | MEDI precedent again; integrations already bridge async lifespans to sync resolution cleanly |
| Ambient/global container access for handlers and tests | Koin `KoinComponent`, that-depends class registry, MEDI accessor | No global state | Framework-owned storage (app.state, ContextRepo) is the acceptable boundary; a library-level ambient accessor is not |
| Raising placeholder factories for framework objects | wireup starlette/fastapi integrations | Conservative feature set (duplicate mechanism) | The pattern's failure mode escaped to production as wireup #118; ContextProvider + ScopeNotInitializedError expresses the same thing declaratively |
| Health-check pings as a core DI feature | svcs | Conservative feature set | Needs no core hook beyond the ordinary resolve path; belongs in an integration-layer package if ever wanted |

## 5. Ranked candidate shortlist

All 30 verified candidates, ranked by (impact for 3.0) × (fit within the one-time breaking-change budget).
Breaking candidates rank high because only the major can carry them; docs candidates rank by leverage and
time-sensitivity. Cross-surface duplicates are ranked adjacently and cross-referenced — each pair is one
maintainer decision. Amendments from verification are folded into the text; the verification line records
what was checked and corrected.

---

### 1. API-1 — Flip validate to default-on at root container construction (opt-out) in 3.0

- **Surface:** core-api (same decision as ERR-2, ranked next)
- **Problem:** modern-di has the best validation content in the study (aggregate-all-errors
  `ValidationFailedError`, cycle paths, inverted-scope checks) but ships it off by default
  (`validate=False`), so real projects hit the same lazy-failure class the field is criticized for; every
  framework that revisited this moved to default-on/earlier validation.
- **Precedent:** dishka validates the full graph at `make_container()` by default with
  `skip_validation=True` opt-out (https://dishka.readthedocs.io/en/stable/errors.html); wireup validates
  unconditionally ("if the container starts, it works"); Spring validates-by-default via eager singleton
  instantiation; Koin's trajectory (checkModules → verify() → K2 compiler plugin) shows an ecosystem
  correcting toward this.
- **Sketch:** `Container(scope=Scope.APP, groups=[...])` runs `validate()` automatically when it is a root
  container; opt out with `validate=False` (the parameter flips meaning from opt-in to opt-out). Child
  containers never re-validate. Docs pitch: modern-di keeps its aggregation edge over wireup (all errors at
  once, not first-error).
- **Breaking:** yes — graphs with latent wiring errors that construct today raise `ValidationFailedError`
  at root construction in 3.0.
- **Verification:** confirmed. Problem matches the repo (`modern_di/container.py:49` defaults
  `validate=False`; `architecture/validation.md` documents opt-in with all three check classes and
  aggregation). Roots are identified by `parent_container is None`; `build_child_container` already builds
  children without validate; validation runs correctly from a root APP container without runtime context.
  dishka and wireup precedents verified against live official docs; Spring and Koin corroborated in the
  per-framework notes with official citations. Constraints pass.
- **Ruling:** **accepted** (one decision with ERR-2).

### 2. ERR-2 — Flip validate to on-by-default in 3.0 (validate=True, explicit opt-out)

- **Surface:** errors-diagnostics (same decision as API-1; kept for its surface-specific evidence)
- **Problem:** modern-di is the only studied framework with whole-graph validation where it defaults off:
  dishka validates at `make_container()` by default (opt-out `skip_validation=True`), wireup unconditionally,
  Spring via eager singleton instantiation, Dagger at compile time. Koin's decade-long trajectory shows the
  market punishing runtime-only failure. modern-di already has the best aggregate-all-errors report in the
  field but hides it behind a flag most users never discover.
- **Precedent:** dishka runs full graph validation (missing factories, scope-direction violations, cycles)
  at container creation by default with `skip_validation=True` as the escape hatch
  (https://dishka.readthedocs.io/en/stable/errors.html).
- **Sketch:** In 3.0, `Container(scope=..., groups=[...])` defaults `validate=True`; `validate=False`
  remains the opt-out for startup-cost-sensitive or intentionally partial graphs. Only root containers with
  groups validate (children never re-walk). DFS cost is one-time at startup and touches no creators. 2.x
  could emit a one-time `FutureWarning` when an unvalidated graph later hits a wiring error, steering to the
  flag.
- **Breaking:** yes
- **Verification:** confirmed. Verified against `container.py:49`, `architecture/validation.md`, and the
  ground-truth digest; dishka precedent verified live. `get_dependencies` is a pure registry lookup, so
  default-on validation works on roots regardless of scope depth or context providers. Constraints pass.
- **Ruling:** **accepted** (one decision with API-1).

### 3. DOC-1 — Publish migration/to-3.x.md before the 3.0 tag, with a warnings-as-errors readiness recipe

- **Surface:** docs-onboarding
- **Problem:** `docs/migration/` has to-1.x and to-2.x but no to-3.x guide, while all three queued 3.0
  breaks (`ContainerClosedError`, `Alias(scope=)` removal, `cache_settings=` removal) already warn on 2.x.
  Users have no single page mapping each warning to its 3.0 removal; the only documented readiness step is a
  `filterwarnings("error")` snippet for `ContainerClosedWarning` alone, buried on the errors-and-exceptions
  page rather than a migration guide covering all three breaks.
- **Precedent:** wireup maintains a per-version upgrading page with before/after code per change, backed by
  `FutureWarning` deprecations for some renamed APIs and in-error rename breadcrumbs for others
  (https://maldoinc.github.io/wireup/latest/upgrading/); that-depends shipped a dedicated migration/v4 page
  with its 4.0 release.
- **Sketch:** New `docs/migration/to-3.x.md` published on 2.x docs: (1) removals table with before/after
  code per break; (2) readiness recipe — `filterwarnings("error")` for `ContainerClosedWarning` +
  `DeprecationWarning` so a green 2.x suite guarantees a clean 3.0 upgrade; (3) a short stated deprecation
  policy (warn one minor cycle, remove at major). Linked from release notes and the warnings' messages.
- **Breaking:** no (but time-boxed: must precede the tag)
- **Verification:** amended. Core claim holds (mkdocs nav confirms no to-3.x; all three breaks warn on 2.x
  at `container.py:286`, `alias.py:25`, `factory.py:50`). Both precedent URLs verified live. Corrections:
  the ContainerClosedWarning readiness snippet already exists on the errors page (so the gap is a single
  page covering all three, not "no documented way"), and wireup cushions only some renames with
  FutureWarnings — the precedent is the page, not a universal alias policy.
- **Ruling:** **accepted** — time-boxed: must ship before the 3.0 tag.

### 4. API-2 — Sync-generator creators: yield-based Factory with built-in teardown

- **Surface:** core-api
- **Problem:** Every Python peer (dishka, wireup, svcs, FastAPI, that-depends Resource) spells teardown as
  code after `yield` in the factory itself; modern-di migrants must instead learn a second object
  (`CacheSettings(finalizer=...)`) and move teardown away from setup code, and non-cached factories have no
  teardown channel at all.
- **Precedent:** dishka: "generator = finalizer", post-yield code runs on scope exit in reverse creation
  order (https://dishka.readthedocs.io/en/stable/provider/provide.html); wireup: "Generator → resource with
  cleanup"; svcs: generator factories run cleanup at `container.close()`; FastAPI yield-dependencies.
- **Sketch:**

  ```python
  def db_session(pool: DatabasePool) -> typing.Iterator[Session]:
      session = pool.acquire()
      yield session          # instance delivered here
      session.close()        # runs as a finalizer at container close (LIFO)

  session = providers.Factory(scope=Scope.REQUEST, creator=db_session, cache=True)
  ```

  `Factory` detects `inspect.isgeneratorfunction` at declaration; resolve advances to the yield for the
  instance and registers the post-yield continuation as a finalizer in the resolving container's creation
  order. `bound_type` from the `Iterator[T]` annotation. Async generators rejected at declaration with a
  clear error (sync-only resolution); async teardown stays `CacheSettings(finalizer=async_fn)`. Design point
  for Artur: allow generators on non-cached factories (per-instance finalizer records) or require `cache=`.
- **Breaking:** yes — verification established that `Factory(creator=generator_fn)` is legal today and
  resolves to the raw generator object (`bound_type` inferred as `collections.abc.Iterator`); auto-detection
  changes the resolved value and bound type for that existing legal usage.
- **Verification:** amended (breaking flag corrected from no to yes via an executed test against the current
  package). Problem verified against `architecture/providers.md`/`containers.md` (teardown only via cached
  `CacheSettings(finalizer=)`; LIFO close exists; no generator handling in `modern_di/`). dishka precedent
  verified live; wireup/svcs/that-depends/FastAPI corroborated in notes. Constraints pass (stdlib `inspect`,
  sync advance, sync finalizer continuation).
- **Ruling:** **rejected** — complexity not justified for core; `CacheSettings(finalizer=)` stays the single teardown channel; generator support can live in a Factory subclass outside core if demand appears. See `planning/decisions/2026-07-05-no-generator-creators.md`.

### 5. API-6 — Raise on direct resolve of an unset ContextProvider (kill the silent None) in 3.0

- **Surface:** core-api
- **Problem:** `container.resolve(HttpRequest)` with no context value supplied returns `None` today
  (`architecture/providers.md`), while the same absence on a dependent parameter raises
  `ArgumentResolutionError` — an internal inconsistency, and the silent-None path matches Angular's "may be
  null" pattern that produces downstream `AttributeError` archaeology instead of a named DI error.
- **Precedent:** dishka raises `NoContextValueError` for a declared-but-unsupplied context value
  (https://raw.githubusercontent.com/reagento/dishka/develop/src/dishka/exceptions.py); that-depends raises
  `RuntimeError: Context is not set. Use container_context`; both fail loudly at the resolve site.
- **Sketch:** In 3.0, `ContextProvider.resolve` raises a new `ContextValueNotSetError` (`ResolutionError`
  subclass, breadcrumb-capable) naming the context type and the container scope, with remedy text "pass
  context={T: value} to the container or set_context()". 2.x could bridge with a `DeprecationWarning` on the
  None return. Dependent-parameter behavior (default/nullable dispositions) is unchanged.
- **Breaking:** yes — the None return is documented public behavior.
- **Verification:** confirmed. Verified in source: `context_provider.py` returns None on absent context
  while `factory.py` `_resolve_context_value` raises for required dependent params; not covered by any
  queued 3.0 change. dishka precedent verified in source (raised on missing context key in
  factory_compiler.py); that-depends message live-reproduced. "Dependent behavior unchanged" is feasible
  because Factory reads context via `fetch_context_value` (UNSET sentinel), not `ContextProvider.resolve`.
- **Ruling:** **accepted**.

### 6. ERR-1 — Runtime cycle guard: CircularDependencyError with cycle path instead of raw RecursionError

- **Surface:** errors-diagnostics (same capability as API-7, ranked next)
- **Problem:** `architecture/validation.md` documents that runtime resolution has no cycle guard: an
  unvalidated circular graph raises a bare `RecursionError` on first resolve, with no cycle path. Since
  `validate()` defaults off, modern-di's default cycle experience equals dependency-injector's worst-cited
  bug class (issue #811) and FastAPI's bare RecursionError.
- **Precedent:** python-injector detects cycles at the moment of runtime hit and renders the path:
  "circular dependency detected: A -> B -> A"
  (https://raw.githubusercontent.com/python-injector/injector/master/injector/__init__.py); dig/Fx detect at
  graph-build time with file:line per hop and expose `IsCycleDetected(err)`.
- **Sketch (amended):** Keep the hot path free of per-resolve bookkeeping: `except RecursionError` around
  the provider-resolve call in `Container.resolve_provider`. Note `resolve_provider` is re-entrant —
  `Factory._resolve_kwargs` (factory.py:236) and `Alias.resolve` (alias.py:70) call it per dependency edge,
  so there is no single top-level entry: the try/except lives on every call and conversion happens at the
  innermost frame. That frame performs an ITERATIVE re-walk of the static graph from the failing provider
  (extract `validate()`'s cycle logic into an iterative shared helper — the existing recursive `_visit`
  closure cannot run safely on a nearly exhausted stack) and raises
  `CircularDependencyError(cycle_path=...) from the RecursionError`; outer frames re-raise the converted
  error cleanly. If the re-walk finds no static cycle reachable from the failing provider (e.g. a user
  creator that itself recurses), re-raise the original RecursionError. Zero cost on the happy path; reuses
  `validate()`'s cycle-path rendering and the existing `CircularDependencyError` type.
- **Breaking:** no — replaces a documented crash; `validation.md` must be updated in the same PR.
- **Verification:** amended. Problem verified against `validation.md` and source (no RecursionError handling
  anywhere; `CircularDependencyError` raised only in validate() at container.py:180). injector precedent
  verified verbatim in master source; dig verified at pkg.go.dev. Sketch corrected on two technical points
  (no distinguished entry frame; iterative re-walk required, with re-raise when no static cycle exists).
- **Ruling:** **accepted** (one decision with API-7; this amended sketch governs the mechanics).

### 7. API-7 — Turn unvalidated-cycle RecursionError into a self-diagnosing CircularDependencyError

- **Surface:** core-api (same capability as ERR-1; kept for its option framing)
- **Problem:** A circular graph that was never validated dies with a raw `RecursionError` on first resolve —
  the same undiagnosed failure mode users report against dependency-injector (#811, RecursionError from
  circularly-referencing providers during container deepcopy; #764 "Circular dependency in wiring") and that
  svcs/FastAPI share; the error names neither the cycle nor the fix.
- **Precedent:** injector detects cycles at resolve time via an injection stack ("circular dependency
  detected: A -> B -> A"); uber-go/dig detects at graph-build time and renders the full path;
  dependency-injector #811 is the cautionary tale of doing nothing
  (https://github.com/ets-labs/python-dependency-injector/issues/811).
- **Sketch:** Two options to surface: (a) zero-hot-path-cost — catch an escaping `RecursionError` once and
  re-raise as `CircularDependencyError` with the provider that started the resolve plus remedy text "run
  container.validate() to see the full cycle path"; (b) costlier — an in-flight set keyed by provider_id,
  giving the exact path. If API-1 lands, this becomes a backstop for `validate=False` users. ERR-1's amended
  sketch supersedes the mechanics of option (a); note `CircularDependencyError.__init__` currently requires
  `cycle_path` (exceptions.py:256), so a pathless variant needs it optional or a distinct message form, and
  an escaping RecursionError can originate from user creator code, so the catch must chain the original and
  hedge wording.
- **Breaking:** no
- **Verification:** amended. Problem real per `validation.md` lines 43-46; injector and dig precedents
  confirmed verbatim against primary sources. One precision fix: dependency-injector #811 fires during
  container deepcopy, not on first resolve; #764 is the wiring-cycle case. svcs and FastAPI claims match the
  notes. Constraints pass.
- **Ruling:** **accepted** (one decision with ERR-1; ERR-1's amended sketch governs).

### 8. ERR-3 — Breadcrumb dependency paths on runtime scope errors

- **Surface:** errors-diagnostics
- **Problem:** Verified in code: `Factory.resolve` only prepends breadcrumb steps to `ResolutionError`
  (factory.py:253), but scope errors are `ContainerError` subclasses raised inside `find_container`
  (factory.py:244). A runtime captive dependency (APP-cached factory pulling a REQUEST-scoped dep) therefore
  reports only "Provider of scope REQUEST cannot be resolved in container of scope APP" with no provider
  names and no chain, even though the user resolved from a valid REQUEST container — the wrong-blame failure
  mode users file bugs about elsewhere (Dagger #1023, Angular #58391). MEDI at least names both ends of the
  bad edge.
- **Precedent:** Dagger users treat the dependency trace as the expected baseline on every error class and
  filed https://github.com/google/dagger/issues/1023 specifically because the scope-violation error lacked
  the "is injected at / is requested at" chain; .NET MEDI's `ScopedResolvedFromRootException` names both
  endpoints.
- **Sketch:** Extract the `dependency_path`/`prepend_step` machinery from `ResolutionError` into a small
  mixin (or move it onto `ModernDIError`) and have `ScopeNotInitializedError`/`ScopeSkippedError` inherit
  it; widen the except clause in `Factory.resolve` to also catch these two classes and prepend the step
  before re-raising. Classes keep their `ContainerError` base, so existing `except ContainerError` code is
  unaffected. Implementer nuance from verification: widening the except at factory.py:253 alone prepends
  only consumer steps — the failing provider's own `find_container` call sits outside its own try block, so
  the raise site (or moving find_container inside the try) must also attach the failing provider's step to
  truly name both ends.
- **Breaking:** no — base classes and attributes survive; only the rendered message gains a chain.
- **Verification:** confirmed, including a live reproduction of the exact captive-dependency scenario
  yielding the no-names, no-chain message. Dagger #1023 and Angular #58391 fetched and confirmed as
  wrong-blame reports; MEDI message sourced from dotnet/runtime Strings.resx. Not covered by validate()'s
  opt-in declaration-time checks or the 2026-06 breadcrumb work.
- **Ruling:** **accepted**.

### 9. API-5 — Accept the creator as the first positional argument of Factory

- **Surface:** core-api
- **Problem:** modern-di's shortest registration is `providers.Factory(creator=UserService)` (scope already
  defaults to `Scope.APP`) — the only framework in the study whose registration call cannot lead with the
  class being registered; dishka `provide(Service)`, dependency-injector `Factory(Service, ...)`,
  `fx.Provide(ctor)`, svcs `register_factory(T, fn)` all read subject-first, and the field trend (wireup
  `@injectable`, Angular `@Service`, Koin `singleOf`) is toward one-word registration.
- **Precedent:** dishka `provider.provide(Service)` (https://dishka.readthedocs.io/en/stable/quickstart.html);
  dependency-injector `providers.Factory(Service, ...)`; Fx `fx.Provide(newHTTPServer)`.
- **Sketch (amended):**

  ```python
  repo = providers.Factory(UserRepository)              # == Factory(creator=UserRepository)
  # signature: Factory(creator, *, scope=..., ...)      # positional-OR-keyword, NOT positional-only:
  #                                                     # a `/` would break every existing creator= call site
  ```

  Same treatment considered for `ContextProvider(HttpRequest)` and `Alias(Concrete, bound_type=Proto)`.
  Combined with API-4, a request-group line shrinks to `repo = providers.Factory(UserRepository)`.
- **Breaking:** no — with the positional-or-keyword form, all existing keyword call sites keep working.
- **Verification:** amended. Keyword-only signatures verified in source (factory.py:34-44,
  context_provider.py:25-31, alias.py:17-23); dishka precedent fetched live; others corroborated in notes.
  Two defects fixed: the problem originally overstated today's verbosity (scope defaults to APP), and the
  original sketch's `/` would have made `creator` positional-only, breaking every existing `creator=` call —
  self-defeating; corrected to positional-or-keyword.
- **Ruling:** **accepted**.

### 10. API-4 — Group-level default scope for providers

- **Surface:** core-api
- **Problem:** Every provider in a Group must repeat `scope=Scope.X`; a typical request-scoped group states
  the same scope on every line, and the APP default silently applies when a line forgets it —
  dishka, that-depends, and wireup all provide a declare-once default at the provider-group level.
- **Precedent:** dishka `Provider(scope=Scope.REQUEST)` sets the default for all `@provide` members,
  overridable per registration, with a three-level priority (provide() > Provider(scope=) > class attribute)
  (https://dishka.readthedocs.io/en/stable/provider/index.html); that-depends has container-level
  `default_scope`; wireup's `@injectable` has a default lifetime.
- **Sketch:**

  ```python
  class RequestGroup(Group, scope=Scope.REQUEST):        # via __init_subclass__(scope=...)
      repo = providers.Factory(UserRepository)           # inherits REQUEST
      audit = providers.Factory(Audit, scope=Scope.APP)  # explicit still wins
  ```

  Needs a Factory-level "scope was defaulted, not chosen" marker (e.g. `scope=UNSET` sentinel) so Group can
  stamp it at class creation; inheritance follows normal MRO. Plan-stage design decision: same provider
  instance shared across two groups with different defaults — first-stamp-wins vs. error.
- **Breaking:** no — existing groups and providers omitting scope keep today's APP behavior.
- **Verification:** confirmed. `group.py` has no scope machinery; dishka's three-level priority verified
  live; secondary precedents check out in notes. `__init_subclass__` + UNSET are stdlib-only; Factory's
  declaration-time signature parsing does not consume scope, so deferred stamping is feasible.
- **Ruling:** **accepted**.

### 11. INT-1 — Container-level API for integration-contributed providers

- **Surface:** integration-shape
- **Problem:** Every framework integration registers its ContextProviders by reaching two attributes deep:
  `container.providers_registry.add_providers(...)` (modern-di-fastapi/main.py:49,
  modern-di-faststream/main.py:71; verification found the same reach-in in litestar, starlette, and aiohttp).
  This load-bearing seam is un-blessed public API with no Container-level verb, no root-vs-child guard, and
  it cuts against the 2026-06 direction of privatizing Container internals (commit 91c694a).
- **Precedent:** MEDI: the `Add{GROUP NAME}` extension-method convention on IServiceCollection is the
  documented integration seam every .NET library uses
  (https://learn.microsoft.com/en-us/aspnet/core/fundamentals/dependency-injection?view=aspnetcore-9.0);
  dishka: integrations contribute predefined context providers through the normal Provider registration
  mechanism, never by poking container internals.
- **Sketch:** Add `Container.add_providers(*providers)` (and optionally `register_groups(*groups)`) as the
  blessed post-construction registration verb: duplicate-type checked, documented in
  `architecture/containers.md` as the integration seam. Sibling repos migrate off the registry attribute;
  direct registry access can then be privatized in a later step.
- **Breaking:** no — purely additive; registry privatization deferred.
- **Verification:** confirmed. No post-construction verb exists in `container.py`; cited call sites exact,
  plus three more sibling repos found doing the same (seam more load-bearing than stated).
  `architecture/containers.md` even documents the registry as "populated once at root construction", which
  the integrations' mutation contradicts. Both precedents verified against live docs.
- **Ruling:** **accepted**.

### 12. INT-2 — Unified resolve entry point accepting provider-or-type

- **Surface:** integration-shape
- **Problem (amended: seven, not four):** `FromDI(provider_or_type)` semantics are re-implemented as the
  identical `isinstance(dep, AbstractProvider) -> resolve_provider/resolve` dispatch in seven sibling
  packages (modern-di-fastapi, -faststream, -typer, -pytest, -aiohttp, -starlette, -litestar). Core defines
  no single call for "resolve whatever a marker holds", so the marker contract lives in copy-paste.
- **Precedent:** dishka: one uniform `FromDishka[T]` marker contract shared by ~24 in-package integrations,
  all delegating to a single `container.get`
  (https://dishka.readthedocs.io/en/stable/integrations/index.html); svcs: all five integrations delegate to
  the one `container.get()` entry point.
- **Sketch:** `Container.resolve_dependency(dep: AbstractProvider[T] | type[T]) -> T` performing the
  dispatch once in core (override short-circuit and did-you-mean behavior inherited from the existing
  paths). The sibling implementations collapse to one call each; the Typer decorator and pytest fixtures
  share the same semantics by construction.
- **Breaking:** no — additive; `resolve`/`resolve_provider` untouched.
- **Verification:** amended (duplication count corrected 4 → 7, verified in local sibling source at exact
  file:line; strengthens the candidate). dishka and svcs precedents verified against live docs. Pure
  additive sync dispatch; constraints pass.
- **Ruling:** **accepted**.

### 13. API-8 — Eager warm-up: build all cached providers at startup (container.init_cache())

- **Surface:** core-api (same capability as INT-3, ranked next)
- **Problem:** `validate()` checks wiring but never calls creators, so a misconfigured DatabasePool that
  would fail in `__init__` still surfaces mid-request; the field treats eager instantiation as a separate
  startup lever and modern-di has no equivalent — cached APP providers are always lazy.
- **Precedent:** Spring eagerly instantiates all singletons at context refresh so "errors ... are discovered
  immediately"
  (https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html); Koin
  `single(createdAtStart=true)` + `createEagerInstances()`; that-depends `init_resources()` resolves all
  Resource/Singleton providers up front.
- **Sketch:** `container.init_cache()` (name open: warm_up/prebuild) resolves every registered provider that
  has cache settings and `effective_scope <= container.scope`, in registration order, populating the cache
  and creation order so finalizers run LIFO at close as usual. Integrations call it in the startup hook next
  to `open()`. Sync-only by construction (resolution is sync).
- **Breaking:** no — purely additive.
- **Verification:** confirmed. `validation.md` confirms static-only validation;
  `docs/providers/lifecycle.md` explicitly says there is no eager-startup call and the migration guide's
  only workaround is manual per-provider resolves. All three precedents verified against live sources.
  Maintainer note: the from-that-depends guide currently editorializes "no equivalent needed", so this
  reverses a documented stance — a design call, not a defect.
- **Ruling:** **accepted** — interface open: method name and exact semantics to be settled in the bundle's design (one decision with INT-3).

### 14. INT-3 — Eager initialization of cached providers for startup fail-fast

- **Surface:** integration-shape (same capability as API-8; kept for the lifespan-hook framing)
- **Problem:** Integrations can check graph shape (`validate()`) but cannot eagerly BUILD cached APP-scope
  providers during lifespan startup: a bad DB URL or unreachable broker in a `Factory(cache=...)` creator
  surfaces on the first request, not at boot.
- **Precedent:** that-depends `init_resources()` (verified in source:
  https://raw.githubusercontent.com/modern-python/that-depends/main/that_depends/container.py);
  dependency-injector `container.init_resources()`; Koin `createdAtStart=true` + `createEagerInstances()`;
  Spring eager singletons at refresh.
- **Sketch:** `container.init_cached()` (name TBD): resolve every provider with cache settings (including
  the `cache=True` shorthand) at this container's scope, in declaration order, respecting overrides;
  finalizers still run LIFO at close. Opt-in; integrations may call it inside `setup_di` or document it for
  lifespan hooks alongside `validate()`.
- **Breaking:** no
- **Verification:** confirmed. No eager-init method in `modern_di/`; all four precedents verified against
  live sources. Sync instance method over the existing registry using sync `resolve_provider`; constraints
  pass. Decide jointly with API-8 (one method, one name).
- **Ruling:** **accepted** — interface open (one decision with API-8).

### 15. INT-4 — Self-resetting context-manager form of override

- **Surface:** integration-shape
- **Problem:** `container.override()/reset_override()` is imperative-only: tests and integration TestClient
  suites must pair the calls manually, which is exactly the forget-to-reset leak FastAPI's
  `dependency_overrides` docs warn about. The two field frameworks with runtime overrides both treat
  auto-reset as the primary testing spelling; modern-di lacks the form entirely.
- **Precedent:** dependency-injector: `with container.api_client_factory.override(Mock(ApiClient)):`
  auto-resets on exit (https://python-dependency-injector.ets-labs.org/providers/overriding.html); wireup:
  `with container.override.injectable(EmailClient, new=fake_email_client):` context-manager overrides with
  nesting support since 2.8.
- **Sketch:**

  ```python
  with container.override(UserGroup.api_client, mock_client):   # returned handle is a CM
      ...                                                       # __exit__ restores the prior override
  container.override(UserGroup.api_client, mock_client)         # imperative callers unaffected
  ```

  `override(provider, obj)` returns a small handle object; used as a context manager, `__exit__` resets
  that provider's override, restoring any previously stacked value (the registry is a flat dict, so the
  handle captures the prior value at entry). modern-di-pytest can build fixture-scoped overrides on top.
- **Breaking:** no — the return-type change from None to a handle is invisible to callers that ignore it.
- **Verification:** confirmed. `container.py:232` shows `override(...) -> None` as the only spelling; both
  precedents verified against official docs, including wireup v2.8.0's nested-overrides release note.
  Stdlib-only handle; constraints pass.
- **Ruling:** **accepted**.

### 16. DOC-2 — Progressive-disclosure quickstart: 2-3 concept first success, scopes as lesson two

- **Surface:** docs-onboarding
- **Problem:** `docs/index.md` front-loads two scopes, `cache=True`, and `build_child_container` in the very
  first example — 5-6 concepts before first resolve, versus 2 for svcs/FastAPI and 4 for wireup. Nothing
  beyond Group + Factory + resolve is needed for an honest first success.
- **Precedent:** FastAPI's dependencies tutorial escalates from one trivial form to sub-dependencies and
  teardown and is widely cited as the best DI onboarding in Python
  (https://fastapi.tiangolo.com/tutorial/dependencies/); Angular splits an essentials page from the deep
  hierarchical-DI guide most users never open.
- **Sketch:** Restructure the quickstart ramp: step A = one Group, one APP Factory, `resolve(T)` — working
  in ~10 lines; step B = add `cache=True` + finalizer (observable identity demo, MEDI GUID-style: print
  `id()` across resolves); step C = add `Scope.REQUEST` + `build_child_container`. Deep material stays in
  Providers pages. No API changes.
- **Breaking:** no
- **Verification:** confirmed. Concept count verified against `docs/index.md`; the minimal path is honest
  (Factory defaults to `scope=Scope.APP`, factory.py:37). Comparator counts check out against the notes;
  FastAPI tutorial fetched live and escalates exactly as claimed. Not covered by the 2026-06 docs work.
- **Ruling:** **accepted**.

### 17. DOC-3 — "Migrate from dependency-injector" guide (with dishka as a follow-up)

- **Surface:** docs-onboarding
- **Problem:** modern-di has proved the competitive-migration play with from-that-depends.md (that-depends'
  README now points here), but has no guide for dependency-injector — the largest Python DI user base
  (~4.9k stars), whose dominant criticisms (boilerplate, silent wiring failures, no cycle detection, no
  resolve-by-type) map directly onto modern-di strengths.
- **Precedent:** wireup maintains a standing "Migrate to Wireup" page as an acquisition channel — and it
  already includes a dedicated dependency-injector section
  (https://maldoinc.github.io/wireup/latest/migrate_to_wireup/); modern-di's own from-that-depends.md is the
  in-house template (every provider mapped or explicitly noted as unmapped with workaround).
- **Sketch:** `docs/migration/from-dependency-injector.md` following the from-that-depends structure:
  provider taxonomy table (Factory→Factory, Singleton/ThreadSafeSingleton→`Factory(cache=True)`,
  Resource→`cache=CacheSettings(finalizer=)`, Dependency→ContextProvider, Configuration→plain settings
  object); a section replacing `@inject`/`Provide`/`wire()` with resolve-by-type; a diagnostics comparison
  (`validate()` vs RecursionError).
- **Breaking:** no
- **Verification:** confirmed. No such guide exists; problem claims match the dependency-injector notes
  (star count, no by-type API, no whole-graph validation, silent wiring failures #658/#521). wireup page
  fetched live — precedent stronger than claimed since it already targets dependency-injector migrators.
  that-depends README pointer confirmed.
- **Ruling:** **accepted**.

### 18. ERR-4 — Stable per-exception docs URLs and a uniform hint slot across the exception hierarchy

- **Surface:** errors-diagnostics (mechanism half; DOC-6, next, is the docs-coverage half)
- **Problem:** Remediation in modern-di errors is ad hoc: `DuplicateProviderTypeError` is the only exception
  (of ~20) carrying a docs URL, some messages embed a remedy sentence, others state the fact and stop
  (`ScopeNotInitializedError`; `CircularDependencyError`'s generic "Check your provider graph"). There is no
  stable code or link a user can follow from a production traceback to a dedicated explanation.
- **Precedent:** Every Angular runtime error has a stable NGxxxx code linking to a dedicated docs page
  (https://angular.dev/errors/NG0201); Spring Boot gives every recognized failure a structured
  `Description:`/`Action:` report; wireup embeds remedy text plus a docs URL directly in its scope-mismatch
  message.
- **Sketch:** Give `ModernDIError` an optional class-level docs slug; `__str__` appends a uniform trailing
  "See: https://modern-di.modern-python.org/errors/<slug>/" line. Add one docs page per exception class
  (docs already have the troubleshooting/ precedent) stating cause, example, and fix — the Action slot lives
  in docs, keeping messages terse. Pure string work, zero deps, no API change. Implementation caveat:
  `ResolutionError` overrides `__str__` for dependency-path rendering, so the trailing line must compose
  with that override.
- **Breaking:** no — message text only; hierarchy, attributes, raise sites unchanged.
- **Verification:** confirmed. Exception census verified in `exceptions.py`; all three precedents checked
  against primary sources (wireup's message confirmed in `factory_compiler.py` source).
- **Ruling:** **accepted** — one workstream with DOC-6.

### 19. DOC-6 — Complete the error-docs registry: one stable troubleshooting anchor per public exception

- **Surface:** docs-onboarding (docs-coverage half of ERR-4; coordinate as one workstream)
- **Problem (amended):** Troubleshooting has 5 pages but the public exception hierarchy is far larger (~20
  classes: `ScopeSkippedError`, `AsyncFinalizerInSyncCloseError`, `UnknownFactoryKwargError`,
  `ValidationFailedError`, `ContainerClosedWarning/Error`, ...). The exception-to-URL contract already
  exists as a one-off in the codebase — `DuplicateProviderTypeError` embeds its troubleshooting URL
  (exceptions.py:281) — but is not systematic; every other stranded user must search.
- **Precedent:** Angular's NGxxxx registry (https://angular.dev/errors/NG0201); wireup's scope-mismatch
  message with remedy + docs URL (confirmed verbatim in wireup/ioc/factory_compiler.py).
- **Sketch:** Audit `exceptions.py` against `docs/troubleshooting/`; add missing pages with a fixed template
  (symptom, cause, fix, escape hatches); adopt stable slugs per exception class; append
  "See: https://modern-di.modern-python.org/troubleshooting/<slug>/" to each raise-site message (string-only,
  coordinates with ERR-4's slug mechanism).
- **Breaking:** no
- **Verification:** amended. Page census verified (5 pages vs ~20 classes); the original claim that no
  message links to docs was false — DuplicateProviderTypeError already does, which strengthens feasibility:
  the proposal completes an existing in-repo pattern. Precedents verified against primary sources.
- **Ruling:** **accepted** — one workstream with ERR-4.

### 20. ERR-5 — ValidationFailedError report format: group by kind, render cycles as diagrams

- **Surface:** errors-diagnostics
- **Problem:** `ValidationFailedError.__str__` renders a count header plus flat `  - {error}` lines. For a
  graph with many issues this is a wall of text: errors are not grouped by kind, cycles render inline as
  "A -> B -> A" rather than visually (the flat prefix also mangles multi-line sub-errors such as
  "Did you mean:" suggestion blocks), and remediation is generic rather than per-kind. Spring and dishka
  independently converged on drawing the cycle.
- **Precedent:** Spring Boot's BeanCurrentlyInCreationFailureAnalyzer renders the cycle as an ASCII box
  diagram with an Action paragraph
  (https://raw.githubusercontent.com/spring-projects/spring-boot/main/core/spring-boot/src/main/java/org/springframework/boot/diagnostics/analyzer/BeanCurrentlyInCreationFailureAnalyzer.java);
  dishka's `CycleDependenciesError` renders ASCII art of the loop plus a targeted hint ("Did you mean
  @decorate instead of @provide?").
- **Sketch:** Rework `ValidationFailedError.__str__` (and `CircularDependencyError.__str__`) rendering only:
  group `.errors` by type with per-group headers and counts, indent each error's existing message, and
  render each `cycle_path` as a multi-line arrow diagram consistent with the existing breadcrumb style.
  `.errors` list and exception types unchanged; ships naturally with ERR-2.
- **Breaking:** no — human-readable message text only.
- **Verification:** confirmed. Current rendering verified at exceptions.py:353-367 and 259; both precedents
  verified in primary source (dishka's hint confirmed verbatim in exceptions.py source; Spring's
  box-drawing rendering in buildMessage()).
- **Ruling:** **accepted**.

### 21. ERR-7 — Zero-dependency graph export: container.export_graph(format='mermaid'|'dot')

- **Surface:** errors-diagnostics
- **Problem:** modern-di has no user-facing graph introspection or visualization at all — the clearest
  absolute gap on this surface. The dependency graph already exists internally
  (`provider.get_dependencies` backs `validate()`) but there is no public way to enumerate edges or dump the
  graph. dishka ships a built-in plotter and it reads as a headline differentiator; Fx auto-provides a DOT
  export in every container and colorizes it to the root cause on build failure.
- **Precedent:** `dishka.plotter.render_d2()/render_mermaid()` emit ready-to-view graph text from any
  container (https://dishka.readthedocs.io/en/stable/advanced/plotter.html); Fx's `fx.DotGraph` is
  auto-provided in every app and attached to build errors (https://pkg.go.dev/go.uber.org/fx).
- **Sketch:** One pure function walking `providers_registry` via the existing `get_dependencies`: emit
  Mermaid (and/or DOT) text with one node per provider (name + scope, scopes as subgraphs) and one edge per
  dependency. String generation only — no rendering, no I/O, no new deps; roughly the size of
  `suggester.py`. Doubles as the debugging companion to `validate()`.
- **Breaking:** no
- **Verification:** confirmed. No existing capability (grep + ground truth); internal foundation real
  (abstract.py:40 backing container.py:188); both precedents verified against official docs, including Fx's
  "colorized to highlight the root cause" wording.
- **Ruling:** **accepted**.

### 22. API-3 — Intent-named scope entry: container.enter_scope(scope=None, context=...) as the taught spelling

- **Surface:** core-api
- **Problem:** `build_child_container` is the longest scope-entry name in the field and names the mechanism
  (build a container) rather than the intent (enter a scope); dishka spells the same operation
  `with container(context=...)`, wireup `enter_scope({Type: obj})`, MEDI `CreateScope()` — the per-request
  line every integration and user writes is measurably heavier in modern-di.
- **Precedent:** wireup: `with container.enter_scope({RequestContext: ctx}) as scope:`
  (https://maldoinc.github.io/wireup/latest/lifetimes_and_scopes/); dishka: callable container
  `with container(context={Request: r}) as request_container:`; MEDI: `provider.CreateScope()`. Nuance from
  verification: wireup scopes are flat siblings, not a parent/child chain, so the precedent supports the
  name, not identical semantics — the sketch keeps modern-di semantics.
- **Sketch:** Add `Container.enter_scope(scope=None, context=None) -> Container` with identical semantics to
  `build_child_container` (auto-increment on scope=None, context dict, usable as sync/async CM). Decide:
  keep `build_child_container` as the primitive forever, deprecate it in 3.0, or reject the alias as API
  bloat — all three options surfaced; renaming churn has a cautionary precedent in wireup's serial renames.
- **Breaking:** no — purely additive; any deprecation is a separate maintainer ruling.
- **Verification:** confirmed. `build_child_container` is the sole scope-entry spelling
  (container.py:93); wireup docs fetched live with the verbatim spelling; dishka/MEDI corroborated in notes.
  The conservative-feature-set/API-bloat tension is explicitly a decision option.
- **Ruling:** **rejected** — `build_child_container` stays the single, mechanism-accurate spelling; the migrant-familiarity gap is closed in docs instead (DOC-4/DOC-5 carry the cross-framework name mapping). See `planning/decisions/2026-07-05-no-enter-scope-alias.md`.

### 23. DOC-4 — "modern-di for FastAPI users" page disambiguating the two meanings of scope

- **Surface:** docs-onboarding
- **Problem (amended):** FastAPI users are the largest incoming audience (its app-scope gap is documented in
  an open discussion with community workarounds and is a recurring critique in third-party writing), and
  since FastAPI 0.121.0 `Depends(scope="function"|"request")` means yield-teardown timing, not lifetime —
  the exact word modern-di uses for its central IntEnum. No modern-di docs page translates Depends idioms
  (`use_cache`, yield teardown, `dependency_overrides`, `lru_cache` singletons) into modern-di equivalents
  or flags the terminology collision.
- **Precedent:** FastAPI 0.121.0 introduced dependency scopes as teardown timing (release verified via
  GitHub API); the app-scope gap and lifetime critique are documented in
  https://github.com/fastapi/fastapi/discussions/13913 (open, low-traffic) and
  https://vladiliescu.net/better-dependency-injection-in-fastapi/.
- **Sketch (amended):** New introduction (or integrations/fastapi) section: side-by-side table —
  `Depends(fn)` ↔ `Factory(creator=)`; `use_cache` per-request memo ↔ REQUEST-scope `Factory(cache=True)`
  (a bare Factory creates a fresh instance per resolve, i.e. `use_cache=False`); yield teardown ↔
  `cache=CacheSettings(finalizer=...)`; `lru_cache` singleton ↔ APP-scope `Factory(cache=True)` with
  finalizer; `dependency_overrides` dict ↔ `container.override(provider, mock)`; a callout box: "FastAPI's
  scope= is teardown timing; modern-di's Scope is lifetime".
- **Breaking:** no
- **Verification:** amended. No such page exists (integrations/fastapi.md is setup-only; zero docs hits for
  use_cache/dependency_overrides/0.121). Release semantics verified via `gh api`; discussion verified real
  but low-engagement (problem wording toned down accordingly). Sketch mapping fixed: `use_cache` equivalent
  is a cached REQUEST-scope Factory, not a bare one.
- **Ruling:** **accepted**.

### 24. DOC-5 — Cross-framework lifetime vocabulary table ("where is Singleton?")

- **Surface:** docs-onboarding
- **Problem (amended):** modern-di deliberately has no Singleton class, and every arriving user speaks
  another framework's lifetime dialect (`Singleton` class, `@singleton`, `lifetime="singleton"`,
  `AddSingleton`). The docs answer "how do I spell create-once-and-reuse" only piecemeal: factories.md shows
  a cached-Factory singleton example, about-di.md maps singleton/scoped/transient onto scopes+cache, and the
  from-that-depends guide has a mapping table — but only for that-depends. There is no single
  cross-framework translation table; comparison.md compares capabilities without translating vocabulary.
- **Precedent:** svcs dedicates a glossary to defining DI terminology and pre-rebutting confusion
  (https://svcs.hynek.me/en/stable/glossary.html); modern-di's own from-that-depends guide already ships
  exactly this table for one framework (`Singleton` → `Factory(cache=True)`) — the proposal generalizes a
  proven in-repo pattern. (dishka's Alternatives page is a feature-comparison table plus prose critique, not
  a vocabulary mapping — weak precedent, dropped as primary.)
- **Sketch:** Extend `docs/introduction/comparison.md` (or a new rosetta.md) with a translation table:
  rows = singleton / transient / request-scoped / runtime value / interface binding / test override;
  columns = dependency-injector, dishka, wireup, svcs, FastAPI, modern-di spelling. Each modern-di cell
  links to the owning Providers page.
- **Breaking:** no
- **Verification:** amended. Gap real (grep confirms no cross-framework spelling translation anywhere); the
  original "no direct docs answer" overstatement corrected (three pages partially answer it), and the dishka
  Alternatives citation was fetched and reclassified as weak — svcs glossary promoted to primary precedent.
- **Ruling:** **accepted**.

### 25. DOC-7 — "Good and bad practices" anti-pattern catalog page

- **Surface:** docs-onboarding
- **Problem:** modern-di documents happy paths but has no anti-patterns page, though it has real named
  footguns: cached factory built before `set_context` silently keeps the stale graph; unvalidated cycles die
  as raw RecursionError; container_provider overuse turns DI into service location; overrides leak across
  tests without `reset_override`. These are currently scattered or implicit in capability pages.
- **Precedent:** injector ships a "Good and bad practices" page (service-locator warning, IO-in-modules
  deadlock warning) (https://injector.readthedocs.io/en/latest/practices.html); Microsoft's DI guidelines
  include a named anti-pattern catalog (captive dependency, disposable transients, async factory deadlock).
- **Sketch:** New docs page (Introduction or Recipes): 5-7 named anti-patterns, each with a bad/good code
  pair and a link to the enforcing mechanism (`validate()`, `reset_override`, ContextProvider timing).
  Cross-linked from quickstart's "Where to next".
- **Breaking:** no
- **Verification:** confirmed. No practices page exists (mkdocs nav + grep); all four cited footguns
  verified as real and scattered at exact locations; injector page fetched live with both warnings present;
  Microsoft catalog corroborated.
- **Ruling:** **accepted**.

### 26. ERR-6 — Definition sites (module:line of the creator) in breadcrumb steps and cycle paths

- **Surface:** errors-diagnostics
- **Problem:** `ResolutionStep` carries only (scope, name); cycle paths carry type names only. In a large
  codebase "UserService" does not localize which Group attribute or creator declared the provider. The
  field's best traces carry source anchors: dig/Fx print "provided by pkg.NewFoo (file.go:42)" per hop;
  Dagger prints the injection site per hop.
- **Precedent:** uber-go/dig renders every hop of its cycle and missing-dependency errors with the providing
  function's package path and file:line
  (https://raw.githubusercontent.com/uber-go/dig/master/cycle_error.go — quoted example confirmed verbatim
  in the file's doc comment).
- **Sketch:** At Factory declaration time (signature parsing already runs `inspect` there — factory.py:104),
  capture the creator's location with a silent fallback for C callables; prefer
  `creator.__code__.co_filename/co_firstlineno` (free) or lazy capture at render time over eager
  `getsourcelines` to keep declaration cost nil. Add an optional location field to `ResolutionStep` and to
  `validate()`'s cycle records; render as a dim trailing "(app.groups:42)" on each breadcrumb line.
  Error-path-only cost; stdlib-only.
- **Breaking:** no — optional field defaults; `cycle_path` stays `list[str]`.
- **Verification:** confirmed. Source structure verified (exceptions.py:13-24, container.py:177-180; no
  source-location capture anywhere); dig precedent fetched and matched verbatim. Minor nit folded into the
  sketch (avoid eager getsourcelines per Factory at import).
- **Ruling:** **accepted**.

### 27. ERR-8 — Opt-in resolution tracing via stdlib logging (DEBUG-level narration)

- **Surface:** errors-diagnostics
- **Problem:** There is no logging call anywhere in `modern_di` (verified by grep), so questions like "why
  did I get this instance", "which container's cache served this", or "which finalizers ran in what order"
  are answerable only with a debugger. Fx's structured event log narrating container activity is one of its
  two distinctive UX features; Koin ships `logger(Level.INFO)` in startKoin.
- **Precedent:** Uber Fx prints structured "[Fx] PROVIDE / RUN / HOOK OnStart" events for every container
  action via a swappable fxevent.Logger (https://uber-go.github.io/fx/get-started/minimal.html); Koin's
  startKoin takes `logger(Level.DEBUG)` (default EmptyLogger — also opt-in).
- **Sketch:** A module-level `logging.getLogger("modern_di")` with DEBUG records at the few chokepoints:
  resolve start (provider, scope, container), cache hit vs creator call, override short-circuit, context
  read, finalizer run. Guard with plain `logger.isEnabledFor(DEBUG)` (per-container caching of the flag can
  go stale if the user changes level at runtime) so the hot path pays one boolean when disabled.
  Stdlib-only; logger config stays entirely in user hands — no global state added.
- **Breaking:** no — DEBUG records are dropped by default logging config.
- **Verification:** confirmed. Zero logging verified by grep and ground truth; Fx and Koin precedents
  verified against official docs (both opt-in). Module-level getLogger adds no library-owned global state.
- **Ruling:** **deferred** — revisit on the first user issue a resolution trace would have answered; see `planning/deferred.md`.

### 28. DOC-9 — Expand design-decisions.md into an explicit non-goals page for 3.0

- **Surface:** docs-onboarding
- **Problem (amended):** design-decisions.md already declares async resolution a permanent non-goal (with
  the lifespan-recipe alternative) and rules out a global container, but it does not enumerate the remaining
  deliberate omissions — auto-binding/auto-registration, in-package framework integrations, a
  dependency-graph plotter — so those gaps read as oversights and generate recurring feature requests
  instead of deflecting them; nothing in the repo routes issue reporters or contributors to the decisions
  page.
- **Precedent:** Microsoft's DI guidelines explicitly enumerate the built-in container's deliberate
  omissions and say to use it "unless you need a specific feature that it doesn't support"
  (https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection-guidelines); svcs's author
  states the keep-the-API-envelope-narrow philosophy in a public design discussion and uses it to decline
  auto-injection features (https://github.com/hynek/svcs/discussions/8).
- **Sketch (amended):** Extend `docs/introduction/design-decisions.md` with the missing non-goals —
  auto-binding, in-package integrations, graph plotting — each as what/why (link planning/decisions/ where
  one exists)/sanctioned alternative, matching the format the async-resolution and no-global-state sections
  already use. The repo has no CONTRIBUTING or issue templates, so either add a minimal
  `.github/ISSUE_TEMPLATE` config linking the page, or reference it from README and comparison.md instead.
- **Breaking:** no
- **Verification:** amended. Two of five originally claimed unenumerated items are in fact already
  documented (async resolution, global container); the genuinely missing three stand. Both precedents
  verified at primary sources. Sketch corrected to stop citing nonexistent CONTRIBUTING/issue-template
  files. Note: section 4's rejected-practices table is ready source material for this page.
- **Ruling:** **accepted as amended** — non-goals limited to auto-binding and in-package integrations; the graphs entry states the ERR-7 boundary (text export in scope, rendering/visualization out).

### 29. DOC-8 — Publish llms.txt (and per-page markdown endpoints) for the docs site

- **Surface:** docs-onboarding
- **Problem:** AI coding assistants are now a primary onboarding channel; modern-di ships
  `docs/context7.json` but no llms.txt, so agents must scrape the mkdocs HTML nav. Sibling project
  that-depends already publishes one and it demonstrably improves machine-assisted onboarding (this study's
  own research consumed it directly).
- **Precedent:** that-depends (same modern-python org) serves llms.txt plus per-page index.md endpoints from
  its mkdocs site (https://that-depends.modern-python.org/llms.txt).
- **Sketch:** Add an mkdocs llms.txt plugin (dev-dependency only — the library stays zero-dep) or a small
  build script emitting llms.txt with the nav tree + one-line page summaries, and expose raw .md endpoints;
  wire into `just docs` build and CI.
- **Breaking:** no
- **Verification:** confirmed. Absence verified (repo grep, built site, and
  https://modern-di.modern-python.org/llms.txt returning 404); precedent verified live including a sampled
  per-page markdown endpoint. Docs-site tooling only; published library stays zero-dep.
- **Ruling:** **accepted**.

### 30. INT-6 — Shared conformance test suite for sibling integration repos

- **Surface:** integration-shape
- **Problem:** Seven repos re-implement one contract with zero shared tests; invariants such as "a second
  lifespan cycle works against the same container", "an override set on the root is visible inside the
  middleware-built request container", and "the request container closes even when the handler raises" are
  re-verified (or silently regressed) per repo. wireup shipped exactly this class of integration regression
  in 2.9.
- **Precedent (amended):** wireup issue #118: a 2.8→2.9 integration regression ("Request in Wireup is only
  available during a request." raised in middleware despite middleware_mode=True) reached users because
  integration behavior had no contract gate (https://github.com/maldoinc/wireup/issues/118); .NET ships
  exactly the proposed mechanism as Microsoft.Extensions.DependencyInjection.Specification.Tests — a
  published xUnit conformance suite third-party containers inherit and run in CI
  (https://www.nuget.org/packages/Microsoft.Extensions.DependencyInjection.Specification.Tests).
- **Sketch:** A reusable pytest contract suite parametrized over each integration's app factory + setup_di,
  asserting the lifespan/scope/override/close invariants from the written integration contract. Published
  outside core (e.g. as part of modern-di-pytest or a modern-di-conformance sibling) so core stays
  zero-dependency; each integration repo runs it in CI.
- **Breaking:** no — no core public API changes.
- **Verification:** amended. Problem verified against ground truth and the integration findings; wireup #118
  verified at source. The original secondary citation (ploeh's "Conforming Container" essay) was
  misdescribed — it argues the abstraction is an anti-pattern and is inverted relative to this proposal;
  replaced with the on-point MEDI Specification.Tests precedent (verified on NuGet, v10.0.9).
- **Ruling:** **deferred** — revisit after INT-1/INT-2 land and the sibling repos migrate to the new seams; see `planning/deferred.md`.

## 6. Appendix

### Refuted candidates

| Id | Title | Refutation |
|---|---|---|
| INT-5 | Written integration contract in the architecture truth home | The proposed document already exists: `docs/integrations/writing-integrations.md` is a prescriptive integration specification covering every item in the sketch (setup_di/fetch_di_container/FromDI naming and dispatch rule, connection-kind→scope table, both lifespan idioms with reopen semantics, per-framework realization matrix, decorator path, repo scaffolding, normative checklist); the only residue — it lives under docs/ rather than architecture/ — is a file-placement quibble, not a missing capability. |

### Research artifact index (scratchpad — ephemeral, not retained in-repo)

All under `/private/tmp/claude-501/-Users-kevinsmith-src-pypi-modern-di/80e02115-d3d2-46d6-b845-aa34b4523ccb/scratchpad/v3-ux-research/`:

- `ground-truth.md` — modern-di v2.23 digest (constraints, surface, queued 3.0 breaks, don't-re-propose list)
- Per-surface syntheses: `findings-core-api.md`, `findings-errors-diagnostics.md`,
  `findings-docs-onboarding.md`, `findings-integration-shape.md`
- Per-framework notes (13): `notes-dishka.md`, `notes-wireup.md`, `notes-svcs.md`, `notes-that-depends.md`,
  `notes-dependency-injector.md`, `notes-injector.md`, `notes-fastapi-depends.md`, `notes-spring.md`,
  `notes-dotnet-medi.md`, `notes-koin.md`, `notes-dagger2.md`, `notes-uber-fx.md`, `notes-angular-di.md`
- `svcs_core.py` — vendored source snapshot used during svcs verification

These are session-scratch files; this report is the durable record. If any notes file is wanted long-term,
promote it into `planning/` before the scratchpad is garbage-collected.
