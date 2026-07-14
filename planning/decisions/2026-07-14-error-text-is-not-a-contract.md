---
status: accepted
summary: Rendered error text is diagnostic, not a public contract — the structured attributes are; a change may reformat a message without a deprecation cycle.
supersedes: null
superseded_by: null
---

# Rendered error text is not a public contract

**Decision:** The *rendered* text of a `ModernDIError` is diagnostic output and
may change in any release. The **structured attributes** each error carries
(`.provider_type`, `.cycle_path`, `.suggestions`, `.dependency_path`, …) and the
**class hierarchy** callers catch on are the public contract, and those change
only with the usual care.

## Context

Came up while designing
[2026-07-14.08-one-error-renderer](../changes/2026-07-14.08-one-error-renderer.md).
Unifying the two chain drawers means `CircularDependencyError` renders through the
same code path as `DependencyPathMixin`, which prints an aligned scope column.
Either the cycle message gains that column (a user-visible change), or the shared
drawer carries a `show_scope` flag forever to preserve byte-identical output.

The same question sits under the suggestion work: `.suggestions` currently holds
pre-rendered bullet strings, and making it hold structured `Suggestion` records
changes what a caller reading that attribute sees.

## Decision & rationale

Error text is for a human reading a traceback. Freezing its bytes buys nothing
real and costs compounding: every renderer grows a compatibility flag, and the
formatting can never be improved. So the cycle message gains the scope column,
and the drawer needs no flag.

The attributes are a different matter, and the distinction is the point of the
split: a caller who wants to *act* on an error should read `.cycle_path`, not
regex the message. Pre-rendering suggestions into `.suggestions` violated that —
it forced a programmatic consumer to parse glyphs back out. Structured records
fix the contract rather than break it.

This does not license churn. It licenses a message *improving* without a
deprecation cycle, and it means message-text assertions in tests are pinning an
implementation detail, not a promise.

Rejected: freezing the rendered text. It would have preserved output nobody
depends on, at the price of a permanent flag in the one drawer this change exists
to unify.

## Revisit trigger

A downstream consumer (an integration, or a user in an issue) is found parsing
`str(exc)` to recover structured facts. That means the attribute surface is
missing something — add the attribute, and keep this decision.
