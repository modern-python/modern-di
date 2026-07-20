# Exec Hot-Path Reconsideration — 2026-07-19

**Date:** 2026-07-19
**Method:** Desk research, no new code or benchmarks. Sources: the 2026-07-16
competitor-perf and 2026-07-19 perf-readability audits, the 2026-07-17 nogil
report, the settled `planning/decisions/` corpus, `planning/deferred.md`, and
the vendored rival source in `benchmarks/comparative/.venv`. Spec:
planning/changes/2026-07-19.13-exec-hot-path-reconsideration.md. Baseline: 5a9409b.
**Motivation:** The `exec`-codegen ceiling is the one remaining known resolve
hot-path gap, filed in `deferred.md` as "a stance, not a task." Its stated
ground — "rejected for a zero-dependency library" — conflates two things.

**Verdict:** (filled in Task 7)

## 1. The reframe: "zero-dependency" is not the objection

`exec` is a stdlib builtin; it imports nothing. `dataclasses`, `attrs`, and
`cattrs` all `exec`-codegen and add zero dependencies. So a compiled-source
resolver does not touch the zero-*dependency* guarantee at all. Whatever the
real cost of `exec` codegen is, "it adds a dependency" is not it.

Once dependency-purity is set aside, the objection reduces to four separable
claims, each adjudicated on its own below:

1. Debuggability — can you get a real traceback / PDB through generated code?
2. Maintainability / audit trust — standing cost + the "no magic" posture.
3. Free-threading / nogil — generated resolvers + captured cells under PEP 703.
4. Deployment / exec bans — runtimes and policies that forbid `exec`.

Each is judged against one binding constraint, stated next.
