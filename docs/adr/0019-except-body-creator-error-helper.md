# Extract the creator-call error rule via an except-body-only helper

**Decision:** the creator-call `TypeError` rule lives in one `CreatorCallError.from_type_error`
classmethod, called from inside each site's `except TypeError` block. This supersedes the earlier
drift-lock work's "do not extract a shared helper" non-goal, which locked four copies of the rule
with a cross-path equivalence test instead.

That rejection weighed exactly one helper shape: a helper wrapping the whole `creator(...)` call,
which adds a Python frame on **every** resolve — the success path the single-path compiled resolver
(#334) exists to keep frame-free. It did not weigh extracting only the `except` body (the `tb_next`
discriminate, the `CreatorCallError` construction, the `prepend_step`) while leaving
`try: return creator(...)` at each site, which runs only on the already-failing raise path. Under
that form:

- The hot path stays `return creator(*args)` byte-for-byte — no frame is restored, confirmed before
  ship by a `--benchmark-compare-fail=mean:5%` resolve-bench gate.
- The rule gets one home; changing it is one edit, not four.
- The equivalence test that existed only to police the copies is retired — one source cannot drift
  from itself.
- Traceback fidelity is preserved: the return-or-`None` contract keeps the bare `raise` at each
  site, so a creator-body `TypeError` propagates with its traceback unchanged.

**Revisit trigger:** the resolve hot path regresses after this lands (meaning the success path was
not as frame-free as argued), **or** a future change needs the creator-call rule to differ per site
again, making a single shared rule wrong.
