---
summary: No PyPI download figures were ever verified for any framework in the field — the adoption research's own biggest evidence gap, so where modern-di actually sits in the market is unknown.
---

# Size the DI market with real download data

Pull real PyPI download trends for `modern-di`, `dishka`, `dependency-injector`,
`wireup`, `svcs`, and `that-depends` — and for the integration packages — so the
field's actual shape is known rather than assumed.

## Why it is open

The 2026-06-18 adoption research verified **no download figures for any framework
in the field** — its own single biggest gap.

The reason it matters: that research's central thesis is that adoption compounds
through *being depended upon inside a host framework*, not through feature count.
Its evidence is Pydantic, depended on by roughly 466,400 GitHub repositories and
8,119 PyPI packages, anchoring transformers (~138k), LangChain (~99k), and
FastAPI (~80k). The thesis is plausible; what was never verified is where
`modern-di` actually sits, so any move it implies rests on intuition rather than
on market size.

Three further evidence gaps from the same research are unresolved and worth
folding into the same pass, since they need the same data:

1. Whether `injector`, `punq`, `svcs`, and FastAPI's own `Depends` genuinely
   contest the minimal-container niche — no verified data either way.
2. Consolidate or compete: the long-term relationship between `that-depends` and
   `modern-di`.
3. Which host framework, if any, offers a real path to framework-default status —
   restated as something measurable rather than argued from precedent.

## Revisit trigger

Before committing maintainer time to any adoption or outreach effort — spending
it against the wrong framework is the failure this prevents.
