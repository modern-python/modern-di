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

## 1. Summary

**Verdict: re-decline (no-go).** The reframe holds — dependency-purity was never
the objection — but the bounded 1.3-1.9x prize (§3) is outweighed by two real
costs (§4.2 maintainability, §4.3 free-threading) that the two mitigable rows
(§4.1, §4.4) only deepen. Reopens only on a user-reported high-arity or
deep-chain bottleneck closures provably cannot close.

## 2. The reframe: "zero-dependency" is not the objection

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

## 3. The performance gate (the binding constraint)

Every objection below is judged against this measured ceiling, taken as
established from the 2026-07-16 audit (not re-measured here):

- At **fixed arity**, `exec` codegen is **0-4%** faster than a hand-unrolled
  closure (196 ns generic / 109 ns closure / 104 ns codegen; competitor-perf
  audit §1). Closures capture ~80-90% of the ceiling.
- `exec`'s **only exclusive win** is unrolling to arbitrary argument count:
  ~1.5-2x, and **only at high arity** (competitor-perf audit §2 scaling table).
- Translated to modern-di's shipped resolver, the real-world gap is the
  **1.3-1.9x behind dishka/wireup on transient (C1) and deep-chain (C3) only**
  (`deferred.md`) — exactly the per-node closure-call frame (~13 ns/frame)
  those two eliminate by inlining dep calls into generated source.

So the prize is bounded. The narrow forms where `exec` could actually pay:
**(a) high-arity nodes** (the unroll win), and **(b) deep singleton/scoped
chains** (inline the whole chain, collapse N frames to ~1). Anything outside
those two is inside the 0-4% band, where `exec` buys effectively nothing.

**This section is the guardrail:** reconsidering the ethos cannot manufacture a
win the measurement denies. A dissolved objection is not a win.

## 4. Objection ledger

Each row: what the 2026-07-16 audit assumed → unbundle it from
dependency-purity → the neutralizer (or its absence) → verdict.

### 4.1 Debuggability — VERDICT: mitigable (fully, at a known cost)

**Assumed.** Generated code produces opaque tracebacks; you cannot step
through what you cannot see.

**Unbundled.** This has nothing to do with dependencies; it is a tooling
question with a documented answer.

**Neutralizer.** attrs registers generated source into `linecache.cache`
under a unique `<attrs generated ...>` filename (`_linecache_and_compile`,
`_generate_unique_filename`, `_compile_and_eval`; competitor-perf audit §4),
so exceptions inside generated code yield real tracebacks and PDB steps
through. modern-di would have to add the same: build the script as data,
register it in `linecache`, `_`-prefix injected names, route builtins through
a passed name. The anti-pattern to avoid is `wireup`, which does NOT register
generated source in `linecache` — its tracebacks show a frame name and line
number but no source line (audit §3b#5; confirmed against the vendored
`factory_compiler.py`).

**Verdict: mitigable.** Fully solvable, but only by adopting and maintaining
the attrs linecache discipline — a real, standing cost that lands in §4.2, not
a free win.

### 4.2 Maintainability / audit trust — VERDICT: real (does not dissolve)

**Assumed.** Generated-source machinery is ongoing maintenance load, and a DI
layer users wire their whole app through carries a "no magic" trust posture
that runtime-assembled code erodes.

**Unbundled.** Also not a dependency question — but unlike §4.1 it has no clean
neutralizer. The attrs linecache discipline from §4.1 IS this cost: a
script-builder, hygiene rules, a unique-filename scheme, and a second mental
model (read the generator, not the resolver) that every future contributor
must hold. Today's `resolver_compiler.py` closures are readable Python in the
file; generated source is not.

**Weighed against the prize (§3):** the win this cost buys is 0-4% at fixed
arity, 1.3-1.9x only on construction-heavy graphs. The maintenance and
trust-posture cost is fixed regardless of how small the win is.

**Verdict: real.** This objection survives unbundling intact. It is the one
that does the load-bearing work in the synthesis, and it is a maintainer-values
call, not a measurement.

### 4.3 Free-threading / nogil — VERDICT: real (open, modern-di-specific)

**Assumed.** (The generic competitor audit never covered this — it is
modern-di's own.) Free-threading changes how compiled resolvers behave.

**Unbundled.** Not a dependency question, and not one the rival audits answer.
Today's compiled-closure resolvers already capture shared state in cells; the
`deferred.md` cell-capture item flags that every `LOAD_DEREF` of a shared
capture is a read whose free-threaded refcount behavior is
implementation-dependent, and the free-threading support sits at **Beta (P1,
correctness-only)** per the 2026-07-17 report. An `exec` resolver would
replace captured cells with generated-module globals — a *different* sharing
model (module dict vs cell), not obviously better or worse, and one the current
Beta contract and stress tests were not written against.

**Weighed:** whichever direction it cuts, it adds a second concurrency model to
reason about under a contract that is only Beta. That is cost, not win, and it
cannot be retired without the parallel-resolution stress work the nogil report
(§7) already scoped as out-of-scope-for-now.

**Verdict: real (open).** Not disqualifying, but a genuine unpriced cost
specific to this codebase; mark the module-globals-vs-cells sharing question as
an explicit open item for any future spike, not something this desk doc
resolves.

### 4.4 Deployment / exec bans — VERDICT: mitigable (via additive fallback)

**Assumed.** Some locked-down runtimes and security policies forbid `exec`
(RestrictedPython-style sandboxes, audited environments). A pure-Python DI
library that requires `exec` on the only resolve path excludes them.

**Unbundled.** Not a dependency question; a deployment-surface question.

**Neutralizer.** Keep the shipped closure resolver as the always-available
path and add `exec` codegen as an *optional, additive* second resolver behind
a capability check / fallback — never a replacement. This dissolves the ban
objection, but it **reframes the whole proposal**: `exec` becomes a *second*
resolver to maintain alongside the closure one, which multiplies the §4.2
maintenance cost (two resolve paths, two test matrices, two concurrency models
per §4.3) rather than replacing it.

**Verdict: mitigable — but the mitigation raises the §4.2 cost.** The clean way
to satisfy exec-banned environments is exactly the way that makes the
maintenance objection worse.

## 5. Synthesis & recommendation

Laid against the gate, the ledger does not net out in `exec`'s favor. §3 fixes
the prize: 0-4% at fixed arity — inside the noise band a hand-unrolled closure
already occupies — and 1.3-1.9x only on the two narrow forms (high-arity nodes,
deep singleton/scoped chains) where inlining collapses per-frame closure calls.
That is the entire upside, and it is bounded by measurement, not argument. On
the cost side, two of the four rows survive unbundling intact: §4.2
(maintainability / audit-trust) has no neutralizer — the generated-source
machinery, hygiene rules, and second mental model are a fixed standing load
regardless of how small the win is — and §4.3 (free-threading) is a genuine,
modern-di-specific open cost that swaps captured cells for module globals under
a concurrency contract still at Beta, and cannot be retired without the
parallel-resolution stress work already scoped out. The two "mitigable" rows do
not offset this: §4.1's debuggability fix *is* the attrs linecache discipline,
which is itself the §4.2 cost; and §4.4's clean answer to exec-bans — an
additive fallback resolver — keeps the closure path and bolts `exec` on beside
it, doubling the resolve surface, the test matrix, and the §4.3 concurrency
question. Every path that neutralizes an objection pays for it in §4.2. The
reframe in §2 is sound — "it adds a dependency" was never the real objection —
but dissolving that framing manufactures no win the measurement denies (§3's
guardrail). A bounded prize bought with two real costs plus cost-raising
mitigations does not clear the bar.

**Recommendation — re-decline (no-go).** Keep `exec` codegen out of the resolve
hot path and leave `deferred.md`'s stance in place: the shipped
closure-compiled resolver stays the single resolve path. The reasoning is not
"exec is impure" — §1 retires that — but that the honest ledger is lopsided:
the exclusive win is a bounded 1.3-1.9x confined to high-arity and deep-chain
graphs, while the standing maintainability/trust cost (§4.2) is real and
unavoidable, the free-threading model shift (§4.3) is a real unpriced cost under
a Beta contract, and the only clean fixes for the debuggability (§4.1) and
exec-ban (§4.4) objections both deepen the §4.2 cost rather than escape it.
Closures already capture ~80-90% of the ceiling with readable in-file Python; the
marginal construction-heavy speedup does not justify a second resolver, a second
concurrency model, and a permanent generated-source discipline. No narrow form
surfaced in the rows that clears the bar freshly enough to escalate a hybrid —
even the additive-fallback shape that would make a hybrid deployable is the
very thing that multiplies the load-bearing cost.

**One measured trigger reopens this, and only one:** a user-reported,
real-world resolve bottleneck on a high-arity node or a deep singleton/scoped
chain — the two §3 forms — that the closure resolver provably cannot close.
That is a bottleneck closures cannot close, established from a real workload,
not a synthetic micro-benchmark and not a hypothetical. Absent that signal, the
1.3-1.9x is a number without a victim, and the costs above bind.

*This recommendation is argued from the evidence in §3-§4; the ruling is the
maintainer's.*
