# Ergonomic caching toggle: `cache=` argument, not a `Singleton` class

**Decision:** `Factory`'s caching toggle is one `cache` argument accepting `bool | CacheSettings |
None` — absent/`None`/`False` off, `True` on with defaults, `CacheSettings(...)` on and tuned. One
argument, one mental model, one place caching is expressed. `CacheSettings` is unchanged as the
tuning object; the sugar normalizes into the existing `self.cache_settings` attribute.

Rejected alternatives, all forms of expressing caching twice:

- **A `Singleton` provider class.** Says "caching is on" in the class name *and* in a still-required
  `cache_settings` for finalizers (the most common advanced case); the two can drift, and forbidding
  `cache_settings` on a `Singleton` would strand finalizers. It also reverses the 2.x "no separate
  `Singleton` class" call.
- **A `cached=True` flag alongside `cache_settings=`.** Two arguments meaning "cache" needs a
  both-passed conflict rule, and `cached=True` has no path to a finalizer without switching forms.
- **Overloading `cache_settings=` to accept `True`.** Works and needs no new name, but the noun-y
  argument reads wrong (`settings=True`); renaming keeps the single-axis model and reads naturally
  in both forms.

**Revisit trigger:** a caching mode a single `bool | CacheSettings` argument cannot express cleanly.
The other half of the original trigger has fired and resolved: 3.0 dropped the `cache_settings=`
alias, so `cache=` is the only spelling.
