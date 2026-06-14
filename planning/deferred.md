# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## Free-threaded (nogil) safety of kwargs compilation — from 2026-06-14 audit (A-1)

`Factory._ensure_kwargs_cached` compiles the kwargs buckets outside the container lock
(`modern_di/providers/factory.py`). Under the GIL this is safe — the buckets are a deterministic
function of the fixed providers registry, so concurrent compiles are idempotent. Under free-threaded
CPython, however, `cache_item.kwargs_compiled` is set *after* the bucket fields are rebound; without a
memory barrier another thread could observe `kwargs_compiled is True` while the bucket dicts are still
empty/partial, and resolve with wrong kwargs.

**Revisit trigger:** if/when free-threading (PEP 703 / `--disable-gil`) support becomes a goal. Fix
options: set `kwargs_compiled` last under an explicit barrier, compile under the existing lock, or use
an immutable compiled-kwargs object published atomically. Until then, document modern-di as
GIL-assuming for compilation. See [2026-06-14 audit A-1](audits/2026-06-14-deep-audit-report.md).
