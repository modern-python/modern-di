---
summary: A root-lifecycle conformance check, parametrized over each integration's app factory and setup function, exercising the documented execution contexts where the framework's startup/shutdown hook does not fire — the one failure class shared code cannot prevent, and one that has already escaped once.
---

# Root-lifecycle conformance suite for integration repos

A reusable pytest suite, parametrized over each integration's app factory plus
its setup function, that drives the app through the **execution contexts where
the framework's startup or shutdown hook does not fire** and asserts what
modern-di guarantees there. Published outside core — in `modern-di-pytest` or a
dedicated conformance sibling — so core stays zero-dependency; each of the 12
sibling repos runs it in CI.

## Why it is open

**The failure class is real and has escaped once.** 3.0 made `open()` mandatory
and produced six production defects across integrations, all one root cause: the
root's open hook does not fire in some execution contexts, so the first unit of
work raises. Six separate repos shipped the same bug because each tested its own
happy path and none tested the contexts where the hook is skipped.

**3.1 changed the failure mode without removing it, which makes the check more
valuable, not less.** A root container is now open from construction, so a
skipped hook no longer raises — it means the root's *close* never runs and
finalizers silently do not fire. A hard raise gets caught by any smoke test; a
silent finalizer skip does not. Nothing in a sibling repo's CI currently notices
it.

**The contexts to parametrize over are already enumerated**, in the D3 column of
the 2026-07-22 blessed-ready audit and in each integration's deployment caveats:

| Integration | Context where the hook does not fire |
|---|---|
| fastapi, starlette | ASGI lifespan is optional — a mounted sub-app, or `lifespan="off"` |
| faststream | `TestBroker` / `TestApp` deliberately skip `on_startup` |
| taskiq | `run_receiver_task(run_startup=False)` — the default |
| celery | `task_always_eager` bypasses the worker signals that open the root |
| flask | no app-shutdown hook exists; the root close is the caller's |
| grpc | the server's `start()`/`stop()` is caller-owned |
| typer | neither side is owned by `setup_di` |

Those caveats are currently *prose* — in the
[lifecycle rules](../../docs/integrations/writing-integrations.md#lifecycle-rules)
and on each integration page. Prose does not regress-test. A parametrized suite
turns each documented caveat into an assertion that its stated behavior is what
actually happens, and catches the case where a framework upgrade silently
changes it.

## Why it is narrow

This was filed on 2026-07-05 as a **broad** contract suite — lifespan, scope,
override, and close invariants across every integration, on the
`Microsoft.Extensions.DependencyInjection.Specification.Tests` model. Two things
since have cut it to the root-lifecycle axis, and the narrowing is the substance
of this revision:

1. **The invariants are not uniform, so a broad contract would be mostly an
   exception table.**
   [`d3-root-lifecycle-inherent`](../decisions/2026-07-25-d3-root-lifecycle-inherent.md)
   established that 8 of 12 integrations have inherent lifecycle gaps, and
   [`inject-asymmetry-inherent`](../decisions/2026-07-25-inject-asymmetry-inherent.md)
   splits injection 4 vs 8. A suite asserting one shared contract across those
   would need an opt-out per row for most of its interesting assertions.
2. **Shared code now supplies the uniformity a shared test was going to
   police.** The original second argument was that, since bundling integrations
   into core was rejected (zero dependencies, conservative feature set, with
   that-depends 4.0.2's clean-install failure as evidence that bundling erodes
   uniformity), uniformity across separately published packages had to come from
   a written contract plus a suite. The integration kit has since put the actual
   skeleton — `bind`, `classify_connection`, `Marker`/`from_di` — in core.
   Uniformity by construction is a stronger guarantee than uniformity by
   assertion, and it covers the wiring half.

What shared code cannot cover is this item's remaining scope: the hook that does
not fire lives in the **host framework's execution context**, not in the
adapter's code, so no amount of shared skeleton prevents it. That is the residue
worth a suite. Take MEDI's *form* — one suite, parametrized over
implementations — without its breadth.

`Container.add_providers` landed as the integration registration seam (see
[`containers.md`](../../architecture/containers.md)), and 3.1 settled the
lifecycle contract the suite would assert against, so the original "wait for the
core seams to settle" gate is discharged.

## Revisit trigger

The sibling integration repos have migrated onto 3.1. The suite asserts the 3.1
contract — root open from construction, silent finalizer skip as the failure
mode — so writing it against repos still on 3.0 would encode the wrong
expectation. Also: any integration adding a new documented deployment caveat,
which is a row the suite should have had.
