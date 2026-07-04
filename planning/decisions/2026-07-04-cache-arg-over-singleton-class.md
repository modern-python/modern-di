---
status: accepted
summary: Chose `Factory(cache=bool|CacheSettings)` over a `Singleton` class, a `cached=` flag, or `cache_settings=True`.
supersedes: null
superseded_by: null
---

# Ergonomic caching toggle: `cache=` argument, not a `Singleton` class

**Decision:** Make `Factory`'s caching toggle a single `cache` argument accepting
`bool | CacheSettings | None`, deprecating the `cache_settings=` alias — rather
than reintroducing a `Singleton` provider class, adding a separate `cached=True`
flag, or overloading the old `cache_settings=` to accept `True`.

## Context

`cache_settings=providers.CacheSettings()` is verbose for the common "just cache
it" case. A cross-framework survey found modern-di in the least ergonomic bucket
(a construction-time settings object); the ergonomic patterns are verb-level
(Koin `single {}`, .NET `AddSingleton<T>()`) or a distinct `Singleton` class
(dependency-injector, that-depends). Options considered:

1. **`Singleton` provider class** — a thin `Factory` preset with caching on.
2. **`cached=True` flag** — new boolean arg alongside `cache_settings=`.
3. **`cache_settings=True`** — overload the existing arg to accept a bool.
4. **`cache=` argument** (chosen) — rename to `cache`, accept
   `bool | CacheSettings | None`, deprecate `cache_settings=`.

## Decision & rationale

`cache=` collapses caching onto one axis: absent/`None`/`False` off, `True` on
with defaults, `CacheSettings(...)` on and tuned. One argument, one mental model,
one place caching is expressed.

- **Rejected `Singleton` class.** It expresses "caching is on" in two places —
  the class name *and* a still-required `cache_settings` for finalizers (the most
  common advanced case). Those two can drift, and forbidding `cache_settings` on
  a `Singleton` would strand finalizers. It also reverses the 2.x "no separate
  `Singleton` class" decision. A single `cache` axis has neither problem.
- **Rejected `cached=True` flag.** Two arguments both meaning "cache" requires a
  both-passed conflict rule and gives `cached=True` no path to a finalizer
  without switching forms — the same two-places-can-drift smell.
- **Rejected `cache_settings=True`.** Works and needs no new name, but the noun-y
  argument reads wrong (`settings=True`). Renaming to `cache` keeps the
  single-axis model *and* reads naturally in both forms (`cache=True` /
  `cache=CacheSettings(...)`); the deprecation is a soft warn-only alias.

`CacheSettings` is retained unchanged as the tuning object; only the entry point
gets sugar. Internals are untouched — the sugar normalizes into the existing
`self.cache_settings` attribute in `__init__`.

## Revisit trigger

Reopen if the `cache_settings=` deprecation is scheduled for removal (a major
release), or if a caching mode arises that a single `bool | CacheSettings`
argument cannot express cleanly.
