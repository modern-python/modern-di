# Adoption Strategy Research Report — 2026-06-18

**Question:** How can modern-di be improved and become more popular, relative to
existing Python DI frameworks and DI in other languages?
**Method:** deep-research workflow (5 search angles, 23 sources fetched, 91 claims
extracted, 25 adversarially verified) + maintainer review.

> **Corrections applied 2026-07-14 — read this first.**
>
> The original run adversarially verified its claims about **competitors**, but not
> its claims about **modern-di itself**. Every claim that later failed was in the
> second group. Three were wrong:
>
> 1. **"Decorator-free" is false.** `@inject` is required in **7 of 12**
>    integrations. See [§1](#1-python-di-competitive-landscape).
> 2. **"Sync-only" / "lags on async resolution" is misleading.** Async apps are
>    first-class; only the *resolve path* is synchronous. See [§2](#2-the-async-question-corrected).
> 3. **The dishka integration gap has closed.** It was "many more"; it is now
>    roughly comparable.
>
> Treat competitor facts as solid, adoption-volume statements as directional
> (**no PyPI download figures were verified for any framework** — the single
> biggest evidence gap), and **any claim about modern-di as requiring a source
> check** before it reaches public copy.

---

## 1. Python DI competitive landscape

**Figures re-checked 2026-07-14.**

| Framework | Core model | `await` in resolve | Scopes | Stars | Integrations |
|---|---|---|---|---|---|
| dependency-injector | declarative container + markers | yes | yes | ~4k | ~11 providers |
| **dishka** (closest rival) | `Provider` + `@provide` | **yes** | custom, APP→…→STEP | **1,211** | **~15** |
| wireup | type autowiring + decorators | no | 3 lifetimes | 421 | medium |
| that-depends (sibling) | async-first | yes | yes | 251 | — |
| **modern-di** | type-annotation autowiring | **no (by design)** | 5 levels APP→…→STEP | **58** | **13** |

### Where modern-di actually stands

**Leads on:** minimal core (3 provider types, zero runtime dependencies), and a
lighter declaration model — providers are plain class attributes on a `Group`,
so there is **no `@provide`** anywhere, where dishka requires one on every provider.

**The "decorator-free" claim, corrected.** The original report made this modern-di's
headline differentiator. It does not survive the integrations:

- **No DI decorator needed:** FastAPI, Litestar, FastStream, taskiq (4).
- **`@inject` required:** Starlette, Flask, aiohttp, Celery, arq, aiogram, Typer (7).

So the defensible claim is narrower: *no `@provide` ever, and no `@inject` in the
four biggest integrations* — where dishka needs `@inject` even for FastAPI and
Litestar. Note also that `FromDI(Dependencies.user_service)` at the FastAPI
boundary **is** a marker, structurally like `dependency-injector`'s `Provide[...]`.
Do not market "decorator-free" unqualified; it will be refuted in one `grep`.

**Integration breadth is no longer a gap.** modern-di has 13, dishka ~15. The
original "dishka has many more integrations" is stale and *undersells* modern-di.

**The real ceiling [assessment].** The standalone-DI market is small and
fragmented. Most Python developers use FastAPI `Depends` or hand-wiring and never
adopt a container. modern-di's nearest *active* competitor is dishka; its largest
*passive* competitor is "no DI framework at all."

---

## 2. The async question (corrected)

The original report listed "lags on async resolution — every major rival has it"
as a headline gap, and proposed a whole thrust (D1) to fight the *perception* of an
async gap. **The framing was wrong, and it made modern-di look worse than it is.**

What is true: **`container.resolve(X)` never awaits.** That is the design decision.

What is also true, and the report missed:

- `Container` is an **async context manager** (`async with container:`), with
  `await container.close_async()`.
- **Async finalizers are first-class** — there is a dedicated
  `AsyncFinalizerInSyncCloseError` whose message directs you to `close_async`.
- Genuinely async resources (an `aiohttp` session, an `asyncpg` pool) are
  constructed in the framework lifespan and injected by type via a
  `ContextProvider` — a documented recipe (`docs/recipes/async-lifespan.md`).
- **Most of the 13 integrations are async frameworks.**

**Async apps are the majority use case, not a caveat.** The public `ROADMAP.md`
already states this correctly ("Sync resolution by design — async work belongs in
the framework lifespan, not in dependency resolution"). Say "the resolve path is
synchronous", never "sync-only" — the latter reads as "can't do async" and drives
away exactly the FastAPI/Litestar/FastStream audience worth winning.

---

## 3. that-depends — the sibling

Same org, same author. Async-first, 251 stars, v4.0.2, zero runtime dependencies.
**modern-di ships the migration guide** (`docs/migration/from-that-depends.md`, plus
`from-dependency-injector.md`); that-depends' own `docs/migration/` covers only its
v2/v3/v4 upgrades.

**Strategic conclusion:** differentiate, do not merge or deprecate — that-depends
owns *async-first*, modern-di owns *minimal, sync-resolve*.

**Caveat that still stands [assessment]:** two sibling DI frameworks in one org
splits the org's mindshare and confuses newcomers ("which modern-python DI do I
use?"). The "differentiate" call only works if the positioning is loud and
explicit. *Partly addressed since:* `docs/introduction/comparison.md` now covers
dishka, that-depends, dependency-injector, wireup, svcs, injector and `Depends`,
and the org profile + `modern-python.org` now carry a "which one?" steer.

---

## 4. DI in other ecosystems — ideas worth borrowing (all pillar-safe)

- **Go Wire** — compile-time DI codegen: missing dependencies are *compile-time*
  errors, wired by type not string key. modern-di's `validate=True` already
  approximates "catch it before runtime"; a static/CLI validation story would let
  it market "fail-fast like Wire, zero config."
- **.NET built-in DI** — three lifetimes, an explicit scope abstraction, and
  **lifetime-mismatch validation that throws in development**. modern-di's
  scope-direction enforcement is the same idea, under-marketed.
- **NestJS** — four provider mechanisms (`useValue`/`useClass`/`useFactory`/
  `useExisting`). A reminder that *ergonomics*, not raw provider count, is what
  users feel.

**The borrowable theme is fail-fast validation as a headline feature** — which
modern-di can market today without adding async or new provider types. The
capability already exists (`validate=True`, plus 22 troubleshooting pages
including `validation-failed-error.md` and `scope-chain.md`); what is missing is
the marketing, not the code.

---

## 5. Adoption mechanics — what actually moves the needle

**Pydantic** is depended on by 466,400 GitHub repositories and 8,119 PyPI
packages; it anchors transformers (138k), LangChain (99k), FastAPI (80k). It won
by being a **transitive dependency of anchor projects** and by
type-hints-as-schema ergonomics ("if you're writing modern Python, you already
know how to use them").

**The lesson, and this report's most valuable finding:** adoption compounds
through **being depended upon inside a host framework**, not through feature
lists. The highest-leverage move for modern-di is becoming the **default/blessed
DI inside a host framework**. The open follow-ups in `deferred.md` all serve that
one thesis.

---

## What has shipped since this research

| Original item | Status |
|---|---|
| "Coming from FastAPI `Depends`?" page | **Shipped** — `docs/introduction/for-fastapi-users.md` |
| 3-way positioning page | **Shipped** — `docs/introduction/comparison.md`; org-level steer added on the profile and `modern-python.org` |
| Async lifecycle as a first-class, named capability | **Shipped** — `docs/recipes/async-lifespan.md`, in the nav |
| Fail-fast validation | **Built and documented**; only the *marketing* is outstanding |
| that-depends signposting | **Shipped** — migration guide, both directions signposted |

Still-open items are tracked in [`../deferred.md`](../deferred.md).

---

## Open questions / evidence gaps

1. **Real PyPI download figures across the field** — none were verified. Needed to
   size the market and pick the beachhead with data rather than intuition.
2. Whether `injector` / `punq` / `svcs` / `FastAPI Depends` genuinely contest the
   minimal niche (no verified data).
3. Consolidate vs compete: that-depends / modern-di, long-term.
4. Which host framework offers the best path to framework-default status.

## Sources

Primary (verified against): python-dependency-injector.ets-labs.org ·
github.com/reagento/dishka · github.com/modern-python/that-depends ·
github.com/maldoinc/wireup · go.dev/blog/wire ·
learn.microsoft.com (.NET service lifetimes) · docs.pydantic.dev/latest/why ·
docs.nestjs.com/fundamentals/custom-providers

Secondary: sfermigier/awesome-dependency-injection-in-python ·
dishka.readthedocs.io/en/stable/alternatives.html ·
wasinski.dev/comparison-of-dependency-injection-libraries-in-python

**Corrections (2026-07-14)** were verified directly against this repo's source
(`modern_di/`, `docs/`), the 12 integration READMEs, the GitHub API, and PyPI.
