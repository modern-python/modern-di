---
summary: Adopted the two-axis planning convention (architecture/ truth + changes/ bundles) from faststream-outbox.
---

# Design: Adopt the portable planning convention

## Summary

Replace this repo's flat `planning/specs/` + `planning/plans/` layout with the
two-axis convention already running in `faststream-outbox`: a living
`architecture/` truth home at the repo root plus `planning/changes/{active,archive}/`
folder bundles. The portable README "Conventions" section and the three
`_templates/` are copied byte-identical from `faststream-outbox`; only the
README "Index" and the back-authored `architecture/` prose are repo-specific.
Every existing spec/plan is migrated into a dated change bundle; all of them are
shipped, so they land in `archive/`. This adoption change itself is the lone
occupant of `active/`, dogfooding the convention.

## Motivation

`modern-di` has no truth home today. The "how it works now" knowledge is spread
across `CLAUDE.md`, the user-facing `docs/` site, and a pile of point-in-time
specs/plans under `planning/specs/` and `planning/plans/` — none of which is
authoritative once a release ships. The flat layout also never had an archive:
shipped work and (hypothetical) in-flight work sit in the same two directories,
distinguished only by filename.

`faststream-outbox` (sibling repo, same maintainer) solved this with a portable
convention: an `architecture/` directory of living capability prose as the
single promotion target, and `planning/changes/` folder bundles that freeze the
*why* once shipped. Adopting the same convention here keeps the two repos
consistent and gives `modern-di` a real truth home for the first time.

## Non-goals

- Not changing the user-facing `docs/` mkdocs site — it stays the published
  documentation; `architecture/` is the internal capability truth.
- Not rewriting or re-validating the historical specs/plans — they are relocated
  and have frontmatter normalized, not edited for content.
- Not introducing `retros/` — the convention describes it, but the repo has none
  and we create none speculatively.
- Not promoting this adoption change into an `architecture/` capability file —
  it is tooling/process; its "promotion" is the CLAUDE.md + README edits it
  already makes (mirrors how `faststream-outbox` archived its own adoption).

## Design

### 1. Target layout

```
architecture/                      # NEW truth home — living prose, no frontmatter, outside the docs build
  README.md                        # index naming it the promotion target
  scopes.md  containers.md  providers.md  resolution.md  validation.md  testing-and-overrides.md
planning/
  README.md                        # NEW: Conventions (byte-identical) + repo-specific Index
  _templates/                      # NEW: design.md, plan.md, change.md (copied verbatim from faststream-outbox)
  changes/
    active/2026-06-13.03-portable-planning-convention/   # this change
    archive/<11 migrated bundles>/
  audits/                          # unchanged (2 reports; already plural)
  releases/                        # unchanged (inbound links inside are repointed)
  scripts/workflow.mjs             # unchanged (repo-specific extra, not part of the portable core)
  deferred.md                      # unchanged
```

`planning/specs/` and `planning/plans/` are removed — every file folds into a
`changes/` bundle.

### 2. Back-authored `architecture/` capability set

Six living-prose files, no frontmatter (dated by git), sourced from the existing
specs, the `docs/` site, and the code. Each describes a capability *as it is
now*, not its history.

| File | Covers |
|------|--------|
| `scopes.md` | `Scope` IntEnum (APP→SESSION→REQUEST→ACTION→STEP), the same-or-deeper resolution rule, `find_container` parent-chain walk |
| `containers.md` | `Container` as the entry point, the four registries (`ProvidersRegistry`/`OverridesRegistry` shared vs `CacheRegistry`/`ContextRegistry` per-container), `build_child_container`, close/reopen lifecycle, `container_provider` |
| `providers.md` | `Group` namespace declaration, `Factory` + `CacheSettings` (singleton via caching), sync/async finalizers, `kwargs`/`skip_creator_parsing`, `ContextProvider`, `Alias` |
| `resolution.md` | `resolve`/`resolve_provider` flow, overrides-first short-circuit, `types_parser` introspection, kwargs precedence, `X \| None` nullable injection |
| `validation.md` | `validate=True` / `container.validate()`, cycle detection, transitive scope check via `effective_scope`, deprecated decorative `Alias(scope=...)` |
| `testing-and-overrides.md` | `override`/`reset_override`, `OverridesRegistry`, the sibling `modern-di-pytest` integration (`modern_di_fixture`, `expose`) |

`architecture/README.md` lists these files and states the promotion rule:
shipping a change hand-edits the affected capability file(s) here, then archives
the bundle.

This set is the proposed default; splits/merges are easy to adjust during
execution.

### 3. Change-bundle inventory and `.NN` assignment

The slug is the current filename minus the date prefix and the
`-design`/`-plan` suffix. Inside each bundle, files are renamed to `design.md` /
`plan.md`, and frontmatter is normalized to the convention (`status: shipped`,
plus `pr:` and `outcome:` filled from the release notes and git log; `plan.md`
gets `spec:`). `.NN` within a colliding date follows merge order.

All eleven migrate to `changes/`:

| Bundle id | Files | Source PR / release |
|-----------|-------|---------------------|
| `2026-06-05.01-bug-hunt-audit` | design + plan | 2.15.0 (#188–#197) |
| `2026-06-05.02-singleton-rlock` | design + plan | 2.15.0 |
| `2026-06-05.03-validate-rework` | design + plan | 2.15.0 |
| `2026-06-07.01-mkdocs-github-pages-migration` | design + plan | docs hosting move |
| `2026-06-08.01-scheduled-dep-check` | design + plan | shipped (`.github/workflows/scheduled.yml`) |
| `2026-06-09.01-docs-improvements` | design only | shipped (docs) |
| `2026-06-09.02-migration-guide-from-that-depends` | design only | shipped (`docs/migration/from-that-depends.md`) |
| `2026-06-12.01-code-docs-audit` | design + plan | 2.16.0 |
| `2026-06-12.02-audit-fixes` | plan only | #202 / 2.16.0 |
| `2026-06-13.01-audit-fixes-round2` | plan only | #203 / 2.16.0 |
| `2026-06-13.02-alias-scope-transparency` | plan only | #207 / 2.17.0 |

The one active bundle, `2026-06-13.03-portable-planning-convention/`, holds this
`design.md` (and its `plan.md` once writing-plans runs). It is in-flight and
promotes to `archive/` on merge. `active/` is therefore non-empty: it
demonstrates the convention with exactly this change.

`.NN` ties broken by merge order: 06-05 audit→singleton→validate; 06-12
audit-run→fixes; 06-13 round2 (#203) → alias (#207) → this adoption (`.03`).
The 06-09 pair order (`docs-improvements` `.01`, `migration-guide` `.02`) is a
judgment call — both are same-day docs designs with no strict merge ordering.

### 4. Orphan handling

- **design-only** bundles (`docs-improvements`, `migration-guide-from-that-depends`):
  keep only `design.md`. The convention permits a full-lane bundle that never
  needed a separate plan.
- **plan-only** bundles (`audit-fixes`, `audit-fixes-round2`,
  `alias-scope-transparency`): keep only `plan.md`; the frontmatter `spec:`
  points at the relevant report in `audits/` (the de-facto spec for fix work).
  The README Index line notes "plan-only; spec = audit report."

### 5. Repointing, README, and CLAUDE.md

- **Inbound links** in `planning/releases/2.15.0.md`, `2.16.0.md`, and
  `2.17.0.md` that target `planning/specs/…` or `planning/plans/…` are repointed
  to `planning/changes/<id>/design.md|plan.md`. Links to
  `planning/audits/…` stay valid (audits/ is unchanged).
- **`planning/README.md`** is created with the "Conventions" section copied
  byte-identical from `faststream-outbox/planning/README.md` and a repo-specific
  Index: **Active** lists this adoption; **Archived** lists the eleven bundles
  newest-first; **Other** lists `architecture/` (the promotion target),
  `audits/`, `deferred.md`, and `scripts/workflow.mjs` (the repo-specific extra,
  in place of faststream's `lint-suppressions.md`).
- **CLAUDE.md** gains a new `## Workflow` section (none exists today) describing
  the lanes and bundle layout and naming `architecture/` as the promotion
  target. It adds a pointer that CLAUDE.md's existing `## Architecture` section
  is quick orientation while `architecture/` holds the living capability truth.

### 6. Spec location override

The brainstorming skill's default spec path is
`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. Because this change
*establishes* the new location, the spec is written directly to
`planning/changes/active/2026-06-13.03-portable-planning-convention/design.md`
instead — dogfooding the convention and avoiding a file in a path we would
immediately deprecate.

## Testing

- `just lint-ci` passes clean (eof-fixer + ruff format + ruff check + ty, no
  auto-fix).
- The docs build (`mkdocs build`, as `.github/workflows/docs.yml` runs it)
  succeeds. `docs_dir: docs` excludes both `planning/` and `architecture/`, so a
  green build confirms the migration caused no collateral breakage rather than
  testing the new files directly.
- A `grep` over the repo confirms no remaining inbound references to
  `planning/specs/` or `planning/plans/` outside the migrated bundles
  themselves.

## Risk

- **Broken relative links inside migrated files.** Plans/specs reference each
  other and the audit reports by relative path; moving them two levels deeper
  (`changes/<id>/`) shifts every `../` prefix. *Mitigation:* the grep
  check in Testing, plus per-bundle link review during execution. Likelihood
  medium, impact low (dead links, not broken code).
- **Frontmatter drift.** Hand-filling `pr:`/`outcome:` across eleven bundles
  risks wrong PR numbers. *Mitigation:* derive each from the release notes and
  git log already mapped in this spec; where a bundle spans multiple PRs (the
  2.15.0 trio), record the release and PR range rather than a single number.
  Likelihood low, impact low.
- **`architecture/` divergence from reality.** Back-authored prose can be subtly
  wrong. *Mitigation:* source each file from the shipped code and the existing
  reviewed specs/docs, not from memory; this is the same content the maintainer
  already validated. Likelihood low, impact medium (it becomes the truth home).
