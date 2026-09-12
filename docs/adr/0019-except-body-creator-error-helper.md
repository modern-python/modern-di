# The creator-call error rule lives in one classmethod

**Decision:** `CreatorCallError.from_type_error` owns the rule for turning a `TypeError` raised by
a creator call into a `CreatorCallError` (or leaving it alone). Every resolve site keeps its own
`try: return creator(...)` and calls the classmethod only inside `except TypeError`.

**Why:** a helper wrapping the whole creator call costs a frame on every resolve; extracting only
the `except` body costs a frame only on the already-failing path. One home for the rule replaces
four copies and the equivalence test that policed them, and the return-or-`None` contract keeps a
bare `raise` at each site so a creator-body `TypeError` keeps its traceback.
