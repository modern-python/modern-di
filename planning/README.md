# Planning

Specs, plans, and change history for `modern-di`. The living truth about *what
the system does now* lives in [`architecture/`](../architecture/) at the repo
root; this directory records *how it got there*.

## Quick path (start here)

> The fast lane for making a change. The full reference is in
> [Conventions](#conventions) below — read it only when this isn't enough.

**1. Choose a lane — first matching rule wins:**

1. Any of: needs design judgment · new file/module · public-API change ·
   cross-cutting or multi-file · non-trivial test design → **Full** (design template)
2. Purely mechanical: typo · dep bump · linter/formatter/CI tweak ·
   mechanical rename · single-line config → **Tiny** (no change file, conventional
   commit)
3. Small-but-real, none of the above: ≲30 LOC net · ≤2 files · no new file ·
   no public-API change · one straightforward test → **Lightweight** (change template)

Ambiguous between two? Take the heavier. A lightweight change file that outgrows its lane is rewritten from the design template.

**2. Create the change file** (Full / Lightweight only):
`planning/changes/YYYY-MM-DD.NN-<slug>.md`, where `.NN` is a zero-padded
intra-day counter — copied from the matching template (design or change) in
[`_templates/`](_templates/).

**3. Ship in the implementing PR:** hand-edit the affected
`architecture/<capability>.md`, finalize the change file's `summary:` to the
realized result, and run `just check-planning` before pushing.

## Conventions

> This is the portable convention, sourced from the canonical repo
> [`lesnik512/planning-convention`](https://github.com/lesnik512/planning-convention)
> (applied version in [`.convention-version`](.convention-version)). To update
> it, run that repo's `APPLY.md` flow. The generated change index (`just index`)
> and the `## Other` pointers below are repo-local.

### Two axes, never mixed

- **`architecture/` (repo root) — the present.** One file per capability, plus
  a single `glossary.md` (the ubiquitous language); living prose, updated in the
  same PR that ships the change. The truth home.
- **`planning/changes/` — the past-and-pending.** One file per change,
  kept in place after ship.

A change **promotes** its conclusions into the affected
`architecture/<capability>.md` by hand **in the implementing PR, alongside the
code** — the edit rides in the same diff and is reviewed with it, never applied
as a separate post-merge step. That hand-edit is what keeps `architecture/`
true; the change file stays in `changes/` as the *why*.

### Glossary

`architecture/glossary.md` is the project's **ubiquitous language** — one page
defining the domain terms that code, specs, and capability pages all share. Like
the capability files beside it, it is living prose with **no frontmatter**, dated
by git, and authored lazily: it appears when the first term is worth pinning down.

Each entry is a term, a one-or-two-sentence definition of what it *is* (not what
it does), and an optional `_Avoid_:` line naming the synonyms to reject:

```md
**Timer**:
A scheduled future delivery, identified by a timer id.
_Avoid_: job, task, alarm
```

Keep it a glossary, not a spec — no implementation detail. A change that
introduces or sharpens a term updates `glossary.md` in the same PR, the same way
a behavior change promotes into a capability file.

### Change files

A change is a file `changes/YYYY-MM-DD.NN-<slug>.md`:

- `YYYY-MM-DD` — proposal date; `.NN` — zero-padded intra-day counter
  (`.01`, `.02`, …) that breaks same-date ties so the timeline sorts stably.
- `<slug>` — kebab-case description, not a story ID.

`summary` is written when the change is created (the intent one-liner) and
**finalized at ship** to state the realized result — set in the implementing
PR, alongside the code and the `architecture/` promotion. No post-merge
bookkeeping, no file move. `date` and `slug` are never written — they are
read from the file name.

### Three lanes

| Lane | Artifacts | Use when |
|------|-----------|----------|
| **Full** | one change file from the design template | design judgment; new file/module; public-API change; cross-cutting/multi-file; non-trivial test design |
| **Lightweight** | one change file from the change template | small-but-real: ≲30 LOC net, ≤2 files, no new file, no public-API change, single straightforward test |
| **Tiny** | none — conventional commit | typo, dep bump, linter/formatter/CI tweak, mechanical rename, single-line config |

Heavier lane wins on ambiguity. A lightweight change file that outgrows its lane is rewritten from the design template.

### Plans are ephemeral

The executable plan — task checklists, embedded code, commit sequences,
whatever the executor needs — is a working artifact, not history. Keep it out
of `changes/` and out of version control (git-ignored scratch, e.g.
`.superpowers/`). Once the change ships, the diff and the PR are the record
of execution; a committed plan duplicates them. `check-planning` rejects
anything in `changes/` that is not a flat change file.

### Lean specs

The change file is the single home of a change's rationale:

- The PR body summarizes and links to the change file — it never restates it.
- Rejected alternatives live in `decisions/` and are referenced, not retold.
- Show a sketch when the design needs code; never the full diff-to-be.
- Delete template sections that don't apply — an empty section is ceremony.
- Most designs fit well under ~700 words; length must buy information.

### Artifacts at a glance

- **design template** — the spec: the *thinking* (why, design, trade-offs,
  scope); the change file it produces is the single home of rationale (see
  [Lean specs](#lean-specs)).
- **change template** — the condensed spec for the lightweight lane.
- **`releases/<semver>.md`** — per-release user-facing notes.
- **`audits/<date>-<slug>.md`** — findings from a code/docs/bug-hunt sweep;
  spawns fix changes.
- **`retros/<date>-<slug>.md`** — what we learned after a body of work.
- **`deferred.md`** — real-but-unscheduled items, each with a revisit trigger.
- **`decisions/<YYYY-MM-DD>-<slug>.md`** — one file per design decision taken
  (especially options *rejected*), each with a revisit trigger; listed by
  `just index`.

Templates live in [`_templates/`](_templates/).

### Frontmatter

`date` and `slug` are **derived from the file name** — never
repeated in frontmatter. So:

- `changes/*.md`: `summary` (single line) only.
- `decisions/*.md`: `status` (accepted|superseded), `summary`, and optional
  `supersedes` / `superseded_by`.
- Files in `architecture/` carry **no** frontmatter — living prose, dated by git.

**`summary`** is one line: written at creation as the intent, then **finalized
at ship** to state the realized result — what shipped and its effect. It is the
only field the index renders.

## Index

The listing is **generated**, not maintained — run `just index` to print it:
changes then decisions, newest first. The frontmatter in each change / decision file is the
single source of truth; there is no committed copy to drift.

## Other

- **[`architecture/`](../architecture/)** at the repo root — the living
  capability truth (scopes, containers, providers, resolution, validation,
  testing & overrides). This is the promotion target on every ship.
- **[audits/](audits/)** — findings reports (2026-06-05 bug-hunt, 2026-06-12
  code+docs, 2026-06-13 docs-ux, 2026-06-14 deep audit).
- **[deferred.md](deferred.md)** — real-but-unscheduled items with revisit
  triggers.
- **[decisions/](decisions/)** — design decisions taken (and alternatives
  rejected), so reviews don't re-litigate them; indexed by `just index`.
- **[scripts/bug-hunt-audit.workflow.mjs](scripts/bug-hunt-audit.workflow.mjs)**
  — repo-specific extra (the reusable audit harness), not part of the portable
  core.
