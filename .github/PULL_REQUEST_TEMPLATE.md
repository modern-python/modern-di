<!--
This body IS the spec for the change. It is reviewed alongside the diff and is
the permanent record of why — there is no change file to write.

Trivial PR (typo, dep bump, formatter, CI tweak, mechanical rename)? Delete this
whole template and ship a conventional-commit title.
-->

## Why

The problem or need. What is wrong, missing, or costly today — not what you did
about it.

## Design

The approach, and the trade-off it takes. Show a sketch if the design needs code;
never the full diff-to-be. Most PRs fit well under ~700 words — length must buy
information.

## Non-goals

What this deliberately does **not** do, and why. This is the scope boundary that
stops "why didn't you also fix X" in review and six months from now.

## Verification

How you know it works: the tests added, `just test-ci` (100% line coverage, the
gate), `just lint-ci`, and any measurement if the change claims a performance
effect. State the numbers, not "benchmarked".

---

### Before merging

- [ ] **Behaviour changed?** If a wrong change here could pass silently, pin it with
      a test whose name is the claim and whose docstring opens `INVARIANT:` and says
      what breaks it. Do **not** write prose about mechanism — there is no page for
      it. See [`planning/README.md`](../planning/README.md#where-a-fact-goes).
- [ ] **Adding a fact anywhere?** Run the admission check: derivable from
      `modern_di/` → don't write it; enforceable → a test; deliberately not
      guaranteed → `planning/decisions/`; a user needs it → `docs/`.
- [ ] **Rejected an alternative** with reasoning that would otherwise be
      re-litigated? File it in [`planning/decisions/`](../planning/decisions/)
      with a revisit trigger — not here.
- [ ] **Found real work you are not doing now?** File it in
      [`planning/deferred/`](../planning/deferred/), self-contained, with a
      revisit trigger — not here.
- [ ] `just lint-ci` and `just test-ci` pass.
