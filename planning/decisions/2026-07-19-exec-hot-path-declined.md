---
status: accepted
summary: Re-decline exec codegen on the resolve hot path — the reframe that "zero-dependency" was never the real objection holds, but the bounded 1.3-1.9x prize (high-arity/deep-chain only) does not clear the standing maintainability and free-threading costs.
supersedes: null
superseded_by: null
---

# Re-decline exec codegen on the resolve hot path

**Decision:** Keep the shipped closure-compiled resolver as the single resolve
path. Do not add `exec`-based source-generation codegen, additive or otherwise.

## Context

`deferred.md`'s codegen-ceiling item filed the remaining 1.3-1.9x gap behind
`dishka`/`wireup` on transient and deep-chain graphs as "rejected for a
zero-dependency library" — a stance, not a task. This reopened that stance to
check its ground: `exec` is a stdlib builtin, not a dependency, so
`dataclasses`/`attrs`/`cattrs`-style `exec` codegen would not touch the
zero-*dependency* guarantee at all. Full analysis:
[`planning/audits/2026-07-19-exec-hot-path-reconsideration-report.md`](../audits/2026-07-19-exec-hot-path-reconsideration-report.md).

## Decision & rationale

The reframe holds — "it adds a dependency" was never the real objection, once
unbundled the objection separates into four claims:

- Debuggability — mitigable, but only via the attrs `linecache` discipline
  (script-builder, hygiene rules, unique-filename scheme).
- Maintainability / audit trust — real, no neutralizer; a fixed standing cost
  and a second mental model, independent of how small the win is.
- Free-threading / nogil — real and open, modern-di-specific; swaps captured
  cells for generated-module globals under a concurrency contract still at
  Beta, and cannot be retired without out-of-scope parallel-resolution work.
- Deployment / exec bans — mitigable via an additive fallback resolver, but
  that fix doubles the resolve surface and deepens the maintainability cost
  rather than escaping it.

The perf gate bounds the prize before any of that: `exec` is 0-4% faster than
a hand-unrolled closure at fixed arity (inside the noise band), with its only
exclusive win — ~1.3-1.9x — confined to high-arity nodes and deep
singleton/scoped chains, where closures already capture ~80-90% of the
ceiling. Every path that neutralizes an objection pays for it in the
maintainability row, and dissolving the dependency-purity framing manufactures
no win the measurement denies.

**Holding: re-decline.** The shipped closure-compiled resolver stays the
single resolve path; `exec` codegen stays out, additive or otherwise.

## Revisit trigger

A user-reported, real-world resolve bottleneck on a high-arity node or a deep
singleton/scoped chain — the two forms where `exec` could pay — that the closure
resolver provably cannot close. A synthetic micro-benchmark or a hypothetical
does not qualify.

*Filed at `planning/decisions/2026-07-19-exec-hot-path-declined.md`, linked
from the codegen-ceiling item in [`planning/deferred.md`](../deferred.md).*
