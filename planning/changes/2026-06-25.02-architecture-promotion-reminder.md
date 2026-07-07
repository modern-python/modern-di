---
summary: Add an agent-facing note in CLAUDE.md reminding that a behavior change must promote to the matching architecture/<capability>.md in the same PR.
---

# Change: Agent-facing architecture/ promotion reminder

**Lane:** lightweight — one file (`CLAUDE.md`), a few lines, no code, no test.

## Goal

Close the last unenforced step of the planning convention: the `architecture/`
promotion. The whole convention hinges on hand-editing the affected
`architecture/<capability>.md` in the implementing PR, and it is the easiest step
to forget. This is evaluation **Finding 3**.

We deliberately reject the heavier options (a git-diff heuristic that warns/blocks
when `modern_di/` changes without an `architecture/` change, with an escape
hatch). That heuristic is inherently fuzzy — most code changes (bugfixes,
refactors, perf) legitimately touch no capability contract — so it would produce
frequent false positives and train cargo-cult acknowledgments, exactly the
ceremony this convention has been shedding. A reminder at the point an agent
reads the code is enough.

## Approach

Add a single agent-facing imperative to `CLAUDE.md`'s `## Architecture` intro
blockquote — the spot an agent consults to orient on a capability *before*
changing its behavior. It names the action and the *why*. `architecture/README.md`'s
"Promotion rule" stays the canonical statement for the truth-home audience; the
CLAUDE.md line is a deliberate one-line echo aimed at agents (who reliably load
`CLAUDE.md` but rarely open `architecture/README.md`).

New blockquote text:

> Quick orientation. The authoritative, code-current account of each capability
> lives in [`architecture/`](architecture/). **When a change alters a
> capability's behavior, update the matching `architecture/<capability>.md` in
> the same PR** — that promotion is what keeps `architecture/` true; code that
> changes without it silently rots the truth home.

## Files

- `CLAUDE.md` — extend the `## Architecture` intro blockquote with the promotion
  imperative.

## Verification

- [ ] Apply the edit to `CLAUDE.md`.
- [ ] `just check-planning` — `planning: OK` (this bundle's frontmatter is valid).
- [ ] `just lint-ci` — clean.
- [ ] `just docs-build` — succeeds (`CLAUDE.md` is outside the docs build; confirms no collateral breakage).
