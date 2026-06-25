---
date: 2026-06-25
slug: canonical-convention-repo
summary: Extract the portable planning convention into a personal canonical repo (lesnik512/planning-convention) that agents apply/update into any repo via an APPLY.md instruction doc + a per-repo version marker.
outcome: Realized result — filled at ship time (~1–3 sentences); see README "Frontmatter".
---

# Design: Canonical planning-convention repo applied by agents

## Summary

The portable planning convention (the `planning/index.py` validator + index, the
`_templates/`, the Conventions + Quick-path prose, the `justfile` recipes, and the
`CLAUDE.md` snippets) is currently shared by **byte-identical copy-paste** across
repos. There is no update path, so the three changes shipped this week (#236,
#237) now have to be hand-re-copied into every sibling — the classic template
drift problem.

Replace copy-paste with a **canonical source repo plus an agent-applied
instruction doc**. A personal, public repo `lesnik512/planning-convention` holds
the single source of truth for the convention and its scripts. Each consuming
repo records the version it last applied in `planning/.convention-version`. To
adopt or update, an agent reads the canonical repo's `APPLY.md`, applies the
delta since the recorded version (verbatim copy for clean files, judgment-merge
for files that mix convention with repo-specific content — something a
template engine like Copier cannot do), verifies with `just check-planning`, and
opens a PR.

The repo is **personal, not org-scoped**, because the convention is generic and
will be consumed across several orgs (not only `modern-python`). The canonical
prose is generalized to drop `modern-di`/`modern-python` specifics.

`modern-di` becomes the **first consumer** of its own extracted convention.

## Motivation

Copy-paste sharing has no version, no diff, and no update command. The README
even instructs humans to "copy this section plus `_templates/`." Every
convention change (this week alone: the validator, dropping `pr`/`status`,
the promotion reminder) silently increases drift across the org's repos until
someone manually reconciles each one.

The research sweep (Copier, pre-commit hosted hooks, published dev tool,
reusable workflows) surfaced Copier as the best *tool-based* answer — but the
convention spans files that **mix** convention with repo-specific content
(`justfile`, `CLAUDE.md`), which Copier's whole-file ownership handles poorly. An
**agent** as the apply engine merges those intelligently, needs no new tooling or
runtime dependency, and matches how these repos are already developed
(agent-first). The maintainer chose this over Copier/package/pre-commit for that
reason.

## Non-goals

- Not applying the convention to the other sibling repos in this change — that
  becomes a per-repo agent task (the new `deferred.md` item). This change ships
  the canonical repo + marks `modern-di` as consumer #1.
- Not introducing Copier, a PyPI package, or pre-commit. The agent is the engine.
- Not changing the convention's *content* (lanes, frontmatter, validator
  behavior) — this is purely about how it is distributed. The only edits to the
  prose are generalizing org-specific wording.
- Not building drift *detection* tooling (a CI check that a repo is N versions
  behind). Updates are pulled on demand by an agent; detection can come later.

## Design

### 1. Canonical repo layout (`lesnik512/planning-convention`)

Public, personal repo, seeded from `modern-di`'s current files (which are the
reference-quality versions):

```
README.md         # what this is; how to consume (points to APPLY.md); the version/CHANGELOG
APPLY.md          # agent-facing apply/update instructions — the engine
CHANGELOG.md      # version → deltas (the source an updating agent reads)
convention.md     # the portable Conventions + Quick-path prose (generalized)
index.py          # the validator + index generator (single source of truth)
_templates/
  change.md  design.md  plan.md  decision.md  release.md
```

Versioned with **git tags** (semver, e.g. `1.0.0`). `CHANGELOG.md` maps each tag
to a human-readable list of deltas, written so an agent can apply them
incrementally. Seeded at **`1.0.0`** describing the current state (validator;
`date`/`slug`/`summary`/`outcome` frontmatter with `pr`/`status`/supersession
dropped from change bundles, kept on decisions; flat newest-first index; the
`architecture/` promotion note).

The repo has minimal CI of its own: a check that `index.py --check` runs against
a tiny fixture and that the templates parse. (Light; keeps the source honest.)

### 2. Per-consumer version marker

Each consuming repo carries `planning/.convention-version` — a one-line file with
the last-applied semver (e.g. `1.0.0`). Absent ⇒ never applied (fresh adopt). It
is the only state the consumer stores about the canonical source.

### 3. `APPLY.md` — the apply/update procedure

`APPLY.md` is written **for an agent** (imperative, checklist-shaped, like a
skill). It instructs:

1. **Determine the baseline.** Read `planning/.convention-version` in the target
   repo. Absent ⇒ fresh adopt (do step 5). Else read `CHANGELOG.md` from the next
   version forward to know the deltas.
2. **Overwrite the clean files verbatim** (the canonical repo owns them
   outright): `index.py` → `planning/index.py`; `_templates/*` →
   `planning/_templates/*`.
3. **Merge the prose.** Replace the portable Conventions + Quick-path block in the
   target's `planning/README.md` with `convention.md`. The target keeps its own
   repo-local Index and "Other" pointers below.
4. **Judgment-merge the mixed files** (cannot be owned wholesale):
   - `justfile`: ensure the `index` and `check-planning` recipes exist and match,
     and that `lint-ci` runs `uv run python planning/index.py --check`.
   - `CLAUDE.md`: ensure the `## Workflow` pointer and the `## Architecture`
     promotion note are present and current.
5. **Fresh-adopt scaffolding only** (skipped on update): create the `planning/`
   skeleton (`changes/`, `decisions/`, `_templates/`, `releases/`,
   `deferred.md`) and an `architecture/` directory with a `README.md` carrying
   the promotion rule. The repo authors its own capability files; the canonical
   repo supplies structure + the README, not capability content.
6. **Record + verify + PR.** Write the new version to
   `planning/.convention-version`; run `just check-planning` and `just lint-ci`
   (both green); open a PR whose body lists the applied deltas (from the
   CHANGELOG) so the human reviews exactly what changed.

`APPLY.md` names the verbatim-copy set explicitly so those files are never
"merged" (deterministic), and reserves judgment only for `justfile`/`CLAUDE.md`/
the README portable block.

### 4. Generalizing the prose

`convention.md` is `modern-di`'s current portable section with org-specific
wording removed: "identical across the modern-python repos" → a generic
statement that it is a portable convention; example paths stay generic. The
result reads cleanly for any project in any org.

### 5. `modern-di` as consumer #1

In `modern-di` (this PR):

- Add `planning/.convention-version` = `1.0.0`.
- Add a short pointer in `planning/README.md` naming
  `lesnik512/planning-convention` as the upstream source and `APPLY.md` as the
  update path (replacing today's "copy this section" instruction).
- `modern-di`'s `index.py`/`_templates/`/prose already equal the canonical
  `1.0.0` (the canonical repo is seeded from them), so no file churn beyond the
  marker + pointer.

### 6. Out-of-repo work (Operations)

Creating and pushing `lesnik512/planning-convention` is a one-time step
(`gh repo create lesnik512/planning-convention --public`, push the assembled
contents, tag `1.0.0`). The implementation assembles the repo contents in a
scratch directory; the maintainer (or the agent, with the maintainer's account)
creates and pushes the actual repo.

## Operations

- Create `lesnik512/planning-convention` (public) and push the `1.0.0` contents +
  tag. This is outside the `modern-di` repo; the `modern-di` PR only adds the
  marker + pointer.
- Future: run the `APPLY.md` flow against the other consuming repos
  (faststream-outbox, the modern-di integrations) — tracked in `deferred.md`.

## Out of scope

Sibling-repo rollout, Copier/package/pre-commit mechanisms, convention-content
changes, and drift-detection CI — all excluded (see Non-goals).

## Testing

- The canonical repo's own check: `python index.py --check` passes against a
  throwaway fixture; the five templates parse as valid frontmatter.
- In `modern-di`: `just check-planning`, `just lint-ci`, and `just docs-build`
  stay green after adding the marker + pointer.
- A dry-run of `APPLY.md` against `modern-di` itself is a no-op (it is already at
  `1.0.0`) — confirming the procedure converges (idempotent) on an
  already-current repo.

## Risk

- **Agent-apply is less deterministic than a tool.** A judgment-merge could vary
  between runs. *Mitigation:* the verbatim-copy set covers the bulk (script,
  templates); judgment is reserved for two small, stable files; the PR diff is
  human-reviewed every time; `just check-planning` gates correctness.
- **Canonical repo and consumers drift in the *other* direction** (a repo edits
  its `planning/index.py` locally). *Mitigation:* `APPLY.md` overwrites the
  clean files verbatim, so local edits to owned files are reverted on next apply
  by design — the canonical repo is authoritative for them. Repo-specific
  behavior belongs only in the mixed files.
- **Version marker forgotten on apply.** *Mitigation:* writing
  `.convention-version` is an explicit, final step in `APPLY.md`, and the PR body
  references the version — a missing bump is visible in review.
