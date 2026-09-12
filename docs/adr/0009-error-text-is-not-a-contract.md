# Rendered error text is not a public contract

**Decision:** the rendered text of a `ModernDIError` is diagnostic output and may change in any
release. The structured attributes each error carries (`.provider_type`, `.cycle_path`,
`.suggestions`, `.dependency_path`, ...) and the class hierarchy callers catch on are the contract.

**Why:** freezing the bytes means every renderer grows a compatibility flag and formatting can
never improve; unifying the two chain drawers was the forcing case. A caller who wants to act on an
error reads an attribute, never a regex over the message, so the attribute surface is what has to
be complete. A message-text assertion in a test pins an implementation detail, not a promise. If a
consumer is ever found parsing `str(exc)`, the fix is the missing attribute, not a frozen string.
