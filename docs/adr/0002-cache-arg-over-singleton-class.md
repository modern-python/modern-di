# Caching is one `cache=` argument, not a `Singleton` class

**Decision:** `Factory`'s caching toggle is a single `cache` argument: absent / `None` / `False`
off, `True` on with defaults, `CacheSettings(...)` on and tuned. `CacheSettings` stays the tuning
object and normalizes into `cache_settings`. Since 3.0 there is no other spelling.

**Why:** every alternative expresses caching twice. A `Singleton` class says "cached" in the class
name and again in a still-required `cache_settings` for finalizers, and the two can drift. A
`cached=True` flag beside `cache_settings=` needs a both-passed conflict rule and has no path to a
finalizer. Overloading `cache_settings=True` works but reads wrong. One argument, one model.
