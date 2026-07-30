---
summary: Three unexecuted pieces of adoption groundwork that gate each other — no verified PyPI download data for anyone in the field, no presence on the lists newcomers search, and no FastStream or Typer starter template for a framework's docs to link at.
---

# Adoption groundwork: market data, listings, templates

Three pieces of pre-outreach work, filed separately on 2026-06-18 and folded
here on 2026-07-30 because they are one push with one gate: **know the market,
be findable in it, and have something worth linking to.** None has been
executed.

## Why it is open

### 1. Size the market with real download data

Pull PyPI download trends for `modern-di`, `dishka`, `dependency-injector`,
`wireup`, `svcs`, and `that-depends`, and for the integration packages.

The 2026-06-18 adoption research verified **no download figures for any
framework in the field** — its own single biggest gap. That research's central
thesis is that adoption compounds through *being depended upon inside a host
framework*, not through feature count; its evidence is Pydantic, depended on by
roughly 466,400 GitHub repositories and 8,119 PyPI packages, anchoring
transformers (~138k), LangChain (~99k), and FastAPI (~80k). The thesis is
plausible. What was never verified is where `modern-di` actually sits, so
anything the thesis implies rests on intuition rather than market size.

Three further gaps from the same research need the same data and belong in the
same pass:

- Whether `injector`, `punq`, `svcs`, and FastAPI's own `Depends` genuinely
  contest the minimal-container niche.
- Consolidate or compete: the long-term relationship between `that-depends` and
  `modern-di`.
- Which host framework, if any, offers a real path to framework-default status,
  restated as something measurable rather than argued from precedent.

### 2. Get listed where newcomers look

Three discovery surfaces, all zero-cost and durable once done:

- `awesome-dependency-injection-in-python`
- each host framework's third-party / ecosystem page
- rival comparison pages — dishka, for instance, publishes an `alternatives.html`

These are where someone lands when they go looking for a Python DI container
without already knowing the names. Being absent means being invisible to exactly
the audience the adoption strategy targets, however good the library is. It was
drafted as a section of the org launch playbook and never executed. There is no
technical work here — it is submissions and pull requests to other people's
lists.

### 3. Reference templates as funnels

Frameworks and blog posts link to **starters**, not to libraries. A template is
the artifact a host framework's documentation will actually point at.

The org publishes `fastapi-sqlalchemy-template` and
`litestar-sqlalchemy-template`. There is **no FastStream template and no Typer
template**, so two integrations with official support have no starter to link.

### Why they are one item

They sequence. The download data decides *which* framework is worth the
outreach; the template is what that framework's docs would link at; the listings
are the standing surface that keeps working after the push ends. Executing any
one alone spends maintainer time against a target the other two have not
confirmed.

## Revisit trigger

Before committing maintainer time to any adoption or outreach effort — spending
it against the wrong framework is the failure this prevents. Do the download
data first; it is what makes the other two targeted rather than speculative.
