# Glossary

The project's ubiquitous language — the domain terms that code, specs, and
capability pages share. Living prose, no frontmatter, dated by git. Each entry is
a term, what it *is* (not what it does), and the synonyms to avoid. No
implementation detail; this is a glossary, not a spec.

**Connection**:
The framework-specific object a unit of work carries — an HTTP request, a
broker message, a CLI invocation's context. Not every unit of work has one (a
Typer command's underlying callable does not).
_Avoid_: request (too HTTP-specific — a broker message is also a connection)

**Connection match**:
A child container's derived `scope` and `context`, produced by binding a
connection to one `ContextProvider`. See
[integration-kit.md](integration-kit.md).

**Integration kit**:
The framework-agnostic primitives (`modern_di.integrations`) an integration
adapter composes to derive connection scope/context and to run the
`Annotated`-marker injector, instead of hand-rolling either. See
[integration-kit.md](integration-kit.md).
