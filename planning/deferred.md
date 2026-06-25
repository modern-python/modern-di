# Deferred work

Items intentionally not actioned in the current work, kept here so they aren't lost. Each has enough context to pick up cold.

## Free-threaded (nogil) safety of wiring-plan compilation — from 2026-06-14 audit (A-1)

`Factory._ensure_plan` builds the `WiringPlan` outside the container lock and publishes it to
`cache_item.wiring_plan` (`modern_di/providers/factory.py`). Under the GIL this is safe: the plan is a
deterministic function of the fixed providers registry, so two threads that both see
`wiring_plan is None` build identical plans — at worst the work is repeated once — and the GIL ensures a
thread seeing a non-`None` `wiring_plan` also sees the fully-built (frozen) object.

Under free-threaded CPython that publication guarantee is lost: without a memory barrier a reader could
observe the non-`None` reference before the `WiringPlan`'s fields are visible and resolve against a
partially-constructed plan. (The WiringPlan refactor narrowed the window — one immutable-object publish
replaced the old set-`kwargs_compiled`-after-the-bucket-fields sequence — but did not add a barrier.)

**Revisit trigger:** if/when free-threading (PEP 703 / `--disable-gil`) support becomes a goal. Fix
options: build and publish `wiring_plan` under the existing container lock, or publish the reference
behind an explicit barrier/atomic. Until then, document modern-di as GIL-assuming for plan compilation.
See [2026-06-14 audit A-1](audits/2026-06-14-deep-audit-report.md).
