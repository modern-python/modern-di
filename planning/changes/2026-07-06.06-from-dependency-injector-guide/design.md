---
summary: Migration guide from dependency-injector (DOC-3) — provider taxonomy mapping, wiring replacement, diagnostics comparison, in the from-that-depends template.
---

# Design: "Migrate from dependency-injector" guide

## Summary

Implements shortlist ruling DOC-3 (2026-07-05 UX research). dependency-injector
is the largest Python DI user base (~4.9k stars) and its dominant criticisms —
boilerplate, silent wiring failures (#658/#521), no cycle detection, no
resolve-by-type — map directly onto modern-di strengths. The in-house template
is `docs/migration/from-that-depends.md` (every source concept mapped or
explicitly noted unmapped with a workaround); wireup's standing migrate page
is the field precedent. A dishka guide is a separate future change.

## Design

New `docs/migration/from-dependency-injector.md`, following the
from-that-depends structure (install → container/declaration mapping →
provider taxonomy table → per-topic sections → testing → diagnostics):

1. **Declaration mapping:** `DeclarativeContainer` + providers as attributes →
   `Group` + `Container(groups=[...], validate=True)`; explicit
   schema-vs-runtime split (their container is both).
2. **Provider taxonomy table:** `Factory`→`Factory`;
   `Singleton`/`ThreadSafeSingleton`→`Factory(cache=True)` (note modern-di's
   cache is lock-guarded by default — `use_lock`); `Resource`→
   `Factory(cache=CacheSettings(finalizer=...))`; `Dependency`→
   `ContextProvider`; `Configuration`→plain settings object registered as a
   provider (no config subsystem — state the design decision);
   `Object`/`Callable`/`List`/`Dict`/`Aggregate` etc. — map or explicitly
   "no direct equivalent + workaround", per the template's rule that no
   source concept goes unaddressed.
3. **Wiring replacement:** `@inject` + `Provide[...]` markers + `wire()` →
   resolve-by-type from a container (and integration `FromDI` markers for web
   frameworks); call out their silent-unwired-marker failure mode vs.
   modern-di's declaration-time and resolve-time errors.
4. **Scopes:** their scoping (singleton/factory per provider class) vs.
   modern-di's ordered Scope hierarchy + child containers.
5. **Testing:** `container.override()`/`reset_override` equivalences
   (theirs is per-provider context-managed; ours registry-wide with the CM
   form pending — describe current API only).
6. **Diagnostics comparison:** their RecursionError-on-cycles (#811) and
   silent wiring vs. `validate()` all-errors report + runtime cycle guard +
   breadcrumb chains.

Accuracy protocol: every dependency-injector spelling verified against its
live docs at writing time (report citations are the starting set); every
modern-di spelling verified against architecture/ and source. Nav: after
"From that-depends" in mkdocs.yml. Modern-di snippets runnable (spot-run);
dependency-injector snippets verified against docs but not executed (do not
add it as a dependency).

## Non-goals

No dishka guide; no changes to existing pages except the nav and (if natural)
a one-line cross-link from comparison.md; no editorializing about
dependency-injector's maintenance state — facts with citations only.

## Testing

`just docs-build` (strict), `just lint-ci`; spot-runs of modern-di snippets;
reviewer independently re-verifies a sample of dependency-injector claims
against live docs.

## Risk

Misdescribing dependency-injector (medium/high — migrants know their tool
better than we do): mitigated by the live-verification protocol and
independent review sample.
