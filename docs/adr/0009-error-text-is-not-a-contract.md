# Rendered error text is not a public contract

**Decision:** the *rendered* text of a `ModernDIError` is diagnostic output and may change in any
release. The **structured attributes** each error carries (`.provider_type`, `.cycle_path`,
`.suggestions`, `.dependency_path`, …) and the **class hierarchy** callers catch on are the public
contract, and those change only with the usual care.

The forcing case: unifying the two chain drawers means `CircularDependencyError` renders through the
same path as `DependencyPathMixin`, which prints an aligned scope column. Either the cycle message
gains that column, or the shared drawer carries a `show_scope` flag forever to keep output
byte-identical. Freezing the bytes buys nothing real and costs compounding — every renderer grows a
compatibility flag and the formatting can never improve — so the cycle message gains the column and
the drawer needs no flag.

The attributes are the other half of the split: a caller who wants to *act* on an error should read
`.cycle_path`, not regex the message. Pre-rendering suggestions into `.suggestions` violated that by
forcing a programmatic consumer to parse glyphs back out; structured `Suggestion` records fix the
contract rather than break it. This licenses a message *improving* without a deprecation cycle, and
it means message-text assertions in tests pin an implementation detail, not a promise.

**Revisit trigger:** a downstream consumer — an integration, or a user in an issue — is found
parsing `str(exc)` to recover structured facts. That means the attribute surface is missing
something: add the attribute, and keep this decision.
