---
summary: One line — shown in the generated index. Written at creation; finalize at ship to state the realized result.
---

# Change: One-line capitalized title

**Lane:** lightweight — ≲30 LOC net, ≤2 files, no new file, no public-API
change, a single straightforward test. If it outgrows this, rewrite it from
the design template.

## Goal

One or two sentences: what changes and why.

## Approach

The shape of the change in brief — enough that a reviewer sees the design
without a full spec. Link the truth home (`architecture/<capability>.md`) if a
capability contract moves.

## Files

- `path/to/file.py` — what changes
- `tests/test_x.py` — test added / updated

## Verification

- [ ] Failing test first — command + expected error.
- [ ] Apply the change.
- [ ] Test passes — command.
- [ ] `just test` — full suite green.
- [ ] `just lint` — clean.
