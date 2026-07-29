---
summary: Become the path-of-least-resistance DI inside one host framework — Litestar and FastStream, not FastAPI — so that framework's users adopt modern-di without shopping for a container.
---

# Framework-default status: the beachhead

The central thesis of the 2026-06-18 adoption research: adoption compounds by
*being depended upon inside a host framework*, not by feature count. The play is
to become the path of least resistance for DI inside one host framework, so that
framework's users adopt modern-di without ever evaluating containers.

## Why it is open

The evidence is Pydantic. It is depended on by roughly **466,400 GitHub
repositories and 8,119 PyPI packages**, and it anchors transformers (~138k),
LangChain (~99k), and FastAPI (~80k). It won by being a **transitive dependency of
anchor projects**, plus type-hints-as-schema ergonomics — "if you're writing
modern Python, you already know how to use them." Not by having the longest
feature list.

**Pick Litestar and FastStream, not FastAPI.** FastAPI is saturated by its own
`Depends`; Litestar and FastStream have less DI incumbency, and modern-di already
ships integrations for both. The target is a referenced mention of
`modern-di-litestar` / `modern-di-faststream` in those frameworks' own ecosystem
or third-party documentation. Outreach is maintainer-driven; it is not something
that can be shipped from this repo.

Note the live tension to reconcile before any launch: the org launch playbook's
Show HN post opens with a FastAPI story — chosen for relatability, not as
targeting. Those two should not contradict each other in public.

## Revisit trigger

When there is data to choose with — see
[`di-market-download-data`](2026-06-18-di-market-download-data.md), whose absence
is why this beachhead choice currently rests on intuition. Also gated on the
on-ramp being good enough to survive a blessing request.
