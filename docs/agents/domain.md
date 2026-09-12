# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the
codebase. This repo is **single-context**.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: the domain glossary.
- **`docs/introduction/design-decisions.md`**: the deliberate choices behind the public API and
  the non-goals. Anything a user can observe is decided there, in user-facing terms.
- **`docs/adr/`**: decisions about internals only, the ones a maintainer would otherwise "fix":
  the shape of the resolve path, registry memo invalidation, and the like. An ADR earns its place
  only when the decision is hard to reverse, surprising without context, and a real trade-off;
  most internal choices are none of these and need no record.

## File structure

```
/
├── CONTEXT.md
├── docs/introduction/design-decisions.md   ← public API choices and non-goals
├── docs/adr/                               ← internal design decisions
├── modern_di/
└── tests/
```

There is no `CONTEXT-MAP.md` and no per-package `CONTEXT.md`: one package, one context.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test
name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly
avoids: write `Container` and not `injector`, `Provider` and not `service`, `Resolution` and not
`injection`.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language
the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Link style inside `docs/`

`docs/` is the MkDocs `docs_dir`, and the same files are read on GitHub. Two rules keep a link
working in both renderings:

- **Between files inside `docs/`, use a plain relative `.md` link.** MkDocs rewrites it to a site
  URL and GitHub follows it as a file.
- **Never link from a file inside `docs/` to a path outside it.** It cannot resolve in both
  renderings: MkDocs emits `links.not_found` and ships the link verbatim, so it 404s on the site.
  Cite `modern_di/...`, `tests/...`, and root files as inline code, never as links.

## Flag conflicts with a recorded decision

If your output contradicts a choice on the design-decisions page or an ADR, surface it explicitly
rather than silently overriding:

> _Contradicts design decision "…" (or ADR-NNNN), but worth reopening because…_
