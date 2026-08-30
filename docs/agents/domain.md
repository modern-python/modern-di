# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the
codebase. This repo is **single-context**.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: the domain glossary.
- **`docs/adr/`**: read the decision records that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest
creating them upfront. The `/domain-modeling` skill creates them lazily when terms or decisions
actually get resolved.

## File structure

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-….md
│   └── 0002-….md
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
  URL and GitHub follows it as a file. From one ADR to another, that is `[ADR-NNNN](NNNN-slug.md)`.
- **Never link from a file inside `docs/` to a path outside it.** It cannot resolve in both
  renderings: MkDocs emits `links.not_found` and ships the link verbatim, so it 404s on the site.
  Cite `modern_di/...`, `tests/...`, and root files as inline code, never as links.

## Flag ADR conflicts

If your output contradicts an existing decision record, surface it explicitly rather than silently
overriding:

> _Contradicts ADR-NNNN (its title), but worth reopening because…_
