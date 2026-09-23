# Docs style

How to write and edit the pages MkDocs builds from `docs/`. `exclude_docs` drops `/agents/` and
`/adr/`, so this file and its siblings are outside what it governs. The em-dash rule below also
covers `README.md` and `AGENTS.md`; nothing else here reaches them. Link style between files is in
[`domain.md`](domain.md); this file is everything else.

## Headings and nav

Sentence case, in page headings and in the `mkdocs.yml` nav alike. Proper nouns keep their
capitals: `FastAPI`, `Celery`, `ContextProvider`, `Async SQLAlchemy`.

Troubleshooting pages are the exception. A page's H1 is the **exact exception class name**
(`# ContainerClosedError`), because a reader arrives by pasting it. Lead with a sentence-case
symptom phrase only when the class name describes the symptom poorly, the way
`ContextValueNotSetError` becomes `# ContextProvider has no value`.

Recasing a heading is anchor-safe: MkDocs slugify lowercases, so `## Framework Context Objects` and
`## Framework context objects` share the slug `framework-context-objects`. Changing a heading's
*punctuation* is not, because ` — ` to `: ` collapses a double hyphen and moves the slug. Grep for
inbound links before any punctuation change.

## Link text tracks its target

Link text names the target's heading, so recasing a heading means sweeping what points at it:

```bash
grep -rnE '\[[A-Z][a-z]+ [A-Z][a-zA-Z]*[^]]*\]\(' docs/ --include='*.md'
```

Every drift found so far came from a pass that recased headings and stopped there.

## Em dashes

Mid-sentence em dashes go, per the humanizer skill's §8. Four shapes keep theirs, because the dash
separates a term from its gloss instead of joining two clauses:

- `## See also` bullets — `- [Scopes](scopes.md) — the APP → REQUEST lifetime model.`
- Table cells.
- Term-gloss bullets, the same shape outside a See-also list.
- Comments inside fenced code blocks.

## Contrast markers in code samples

A good/bad pair marks its branches `# Broken:` and `# Works:`, never ❌ and ✅. The words survive
copy-paste into a terminal, a plain-text diff, and a screen reader. A glyph that *is* the content
stays: the feature matrix in `introduction/comparison.md` holds cells, not prose.

## Error text is load-bearing

On a troubleshooting page, every exception class name and every quoted error message is
byte-identical to what the library raises, because a reader pastes the string from a terminal and it
has to match. `tests/test_docs_slug_census.py` binds the page filenames to the `docs_slug` on each
exception class, so a page cannot be renamed, added, or deleted by itself.

## The `CONTEXT.md` avoid-list bans names, not words

`_Avoid_: service, dependency` under **Provider** means don't call a Provider a "service". It does
not ban the English words: an example class may be a `UserService`, and an application may have
"30+ providers". Agents have over-applied this twice.
