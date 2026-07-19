export const meta = {
  name: 'perf-readability-audit',
  description: 'Two-lens (performance + readability) decision-grade audit of modern_di, gated against the settled decisions/deferred corpus, producing a leverage-vs-risk report.',
  whenToUse: 'Run for a fresh both-axes refactor survey that separates new perf hypotheses from already-settled ground and finds off-hot-path readability seams.',
  phases: [
    { title: 'Discover',   detail: 'file map + settled corpus (decisions, deferred, guard scenarios)' },
    { title: 'Find',       detail: 'two parallel lens finders: performance, readability' },
    { title: 'Verify',     detail: 'three lenses per finding, majority vote' },
    { title: 'Synthesize', detail: 'dedup, leverage-vs-risk triage, write report' },
  ],
}

// ---------- schemas ----------

const CONTEXT_BLOB_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['baseline_commit', 'file_map', 'decisions', 'deferred_items', 'guard_scenarios', 'competitive_note', 'recent_commits'],
  properties: {
    baseline_commit: { type: 'string', description: 'short HEAD sha from `git rev-parse --short HEAD`' },
    file_map: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['path', 'lines', 'role'],
        properties: {
          path:  { type: 'string' },
          lines: { type: 'integer' },
          role:  { type: 'string', description: 'one-line responsibility' },
        },
      },
    },
    decisions: {
      type: 'array',
      description: 'Every planning/decisions/*.md ruling: slug + one-line holding (especially what was rejected).',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['slug', 'holding'],
        properties: {
          slug:    { type: 'string' },
          holding: { type: 'string' },
        },
      },
    },
    deferred_items: {
      type: 'array',
      description: 'Every deferred.md item: short title, one-line gist, revisit trigger.',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'gist', 'revisit_trigger'],
        properties: {
          title:           { type: 'string' },
          gist:            { type: 'string' },
          revisit_trigger: { type: 'string' },
        },
      },
    },
    guard_scenarios: {
      type: 'array',
      description: 'The G1-G15 catalog from benchmarks/README.md: id + what it isolates.',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'isolates'],
        properties: {
          id:       { type: 'string' },
          isolates: { type: 'string' },
        },
      },
    },
    competitive_note: { type: 'string', description: 'The current standing summary from deferred.md (where modern-di sits vs rivals and the accepted floor).' },
    recent_commits:   { type: 'array', items: { type: 'string' } },
  },
}

const RAW_FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'title', 'file', 'line', 'description', 'evidence', 'suggested_direction', 'leverage', 'risk', 'confidence', 'guard_scenario', 'hot_path', 'invariant_at_risk', 'settled_ref'],
  properties: {
    lens:                { enum: ['performance', 'readability'] },
    title:               { type: 'string', description: 'short noun phrase' },
    file:                { type: 'string', description: 'relative path' },
    line:                { type: 'string', description: 'integer or "start-end" as string' },
    description:         { type: 'string', description: '1-3 sentences on what could be better' },
    evidence:            { type: 'string', description: 'exact code snippet indicted' },
    suggested_direction: { type: 'string', description: 'one-line direction, not a patch' },
    leverage:            { enum: ['high', 'medium', 'low'], description: 'estimated payoff (perf: expected speedup magnitude / breadth; readability: how much clarity it buys)' },
    risk:                { enum: ['high', 'medium', 'low'], description: 'risk to an invariant or a settled stance' },
    confidence:          { enum: ['high', 'medium', 'low'] },
    guard_scenario:      { type: 'string', description: 'PERF: the G-id (G1-G15) that would confirm it, plus expected-leverage note. READABILITY: "n/a".' },
    hot_path:            { type: 'boolean', description: 'true if the code is on the resolve hot path' },
    invariant_at_risk:   { type: 'string', description: 'READABILITY: the invariant the change must not break (frame count / 100% cov / zero-dep / behavior), or "none". PERF: "n/a".' },
    settled_ref:         { type: 'string', description: 'if you suspect this matches a decisions/ or deferred.md item, name it here; else "".' },
  },
}

const FINDER_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'findings'],
  properties: {
    lens:     { enum: ['performance', 'readability'] },
    findings: { type: 'array', items: RAW_FINDING_SCHEMA },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'confirmed', 'reasoning', 'settled_match'],
  properties: {
    lens:          { enum: ['read-real-code', 'decision-conflict', 'invariant-safety'] },
    confirmed:     { type: 'boolean', description: 'read-real-code: code matches claim. decision-conflict: finding is FRESH (not already settled). invariant-safety: change is safe & leverage-honest. Default false when uncertain.' },
    reasoning:     { type: 'string', description: '1-3 sentences citing what the code/decision actually is.' },
    settled_match: { type: 'string', description: 'decision-conflict lens only: the decision slug / deferred title this duplicates, or "" if genuinely fresh. Other lenses set "".' },
  },
}

const SYNTH_SUMMARY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['report_path', 'counts'],
  properties: {
    report_path: { type: 'string' },
    counts: {
      type: 'object',
      additionalProperties: false,
      required: ['do_first', 'needs_decision', 'cleanup', 'skip', 'already_settled'],
      properties: {
        do_first:        { type: 'integer' },
        needs_decision:  { type: 'integer' },
        cleanup:         { type: 'integer' },
        skip:            { type: 'integer' },
        already_settled: { type: 'integer' },
      },
    },
  },
}

// ---------- prompts ----------

const DISCOVER_PROMPT = `You are the discover agent for a two-lens refactor audit (performance + readability) of the modern-di repository (a zero-dependency Python DI library). Produce a single structured context blob that grounds the downstream finders and, crucially, the "already-settled" guardrail. Do NOT analyze or opine.

Do exactly this:

1. baseline_commit: run \`git rev-parse --short HEAD\`.

2. file_map: every file under modern_di/ (source) — relative path, line count, one-line role. Skip __pycache__.

3. decisions: read every file under planning/decisions/. For each, record its slug (the filename without date/extension is fine) and a one-line holding — WHAT WAS DECIDED, especially what was rejected (e.g. "declined folding ContextRegistry into Container", "no exec codegen"). These are the settled-ground guardrail.

4. deferred_items: read planning/deferred.md. For each "## " item, record a short title, a one-line gist, and its revisit trigger. Capture the perf items faithfully (warm-singleton memo-swap dropped, codegen ceiling, free-threaded non-scaling) — these must not be re-proposed as open.

5. guard_scenarios: read benchmarks/README.md and record the G1-G15 catalog: each id and what it isolates.

6. competitive_note: one paragraph from deferred.md summarizing where modern-di currently sits vs rivals and what the accepted floor is (the no-exec stance, the C2 warm-singleton gap).

7. recent_commits: subject lines from \`git log --oneline -20\`.

Return the structured blob only.`

const PERF_FINDER_PROMPT = (ctx) => `You are the PERFORMANCE-lens finder for a refactor audit of modern-di (zero-dependency Python DI library). The resolve hot path is already at a documented floor — your job is NOT to find easy wins, it is to surface genuinely-new, defensible perf HYPOTHESES and be honest about what is already settled.

CONTEXT BLOB (file map + the settled corpus you must respect):
${JSON.stringify(ctx, null, 2)}

RULES:
- Read the ACTUAL source before any finding (open modern_di/resolver_compiler.py, container.py, registries/*.py, providers/*.py, wiring.py, dependency_graph.py). The blob is a map, not the code.
- Every finding is a HYPOTHESIS, not a claim. Set guard_scenario to the G-id (G1-G15) that would confirm it plus a one-line expected-leverage note. No prototyping, no bench runs — you are proposing what to measure, not measuring.
- SETTLED GROUND IS OFF LIMITS as an "open" proposal. If your idea matches a decisions/ ruling or a deferred.md item (warm-singleton memo-swap, child lazy-alloc, exec/codegen, free-threaded immortalization, per-provider compile seam, folding ContextRegistry), you may only raise it if you bring GENUINELY NEW evidence — and you MUST name the settled item in settled_ref. When in doubt, set settled_ref and let the verifier judge.
- Respect the stances as settled: no exec/codegen (zero-dep), conservative feature set, sync-only resolution. Do not propose them.
- No lint/style. ruff and ty own those.
- Set hot_path (is this on the resolve path?), leverage, risk, confidence. Set invariant_at_risk to "n/a" for perf.

Aim for 4-12 findings; quality over quantity. An empty list is acceptable if there is nothing new. Return the structured object with lens="performance".`

const READABILITY_FINDER_PROMPT = (ctx) => `You are the READABILITY/STRUCTURE-lens finder for a refactor audit of modern-di (zero-dependency Python DI library). Find concrete file:line seams and simplifications that make the code clearer WITHOUT regressing performance or breaking invariants.

CONTEXT BLOB (file map + settled corpus):
${JSON.stringify(ctx, null, 2)}

WEIGHTING — spend your depth where complexity lives:
- FULL-DEPTH read: exceptions.py (663 lines), container.py, resolver_compiler.py, factory.py, dependency_graph.py, wiring.py, types_parser.py.
- LIGHT confirmation pass: the small stable files (scope.py, group.py, alias.py, context_provider.py, container_provider.py, abstract.py, types.py, suggester.py, integrations.py, registries/*).

RULES:
- Read the ACTUAL file before any finding. Cite exact file:line and quote the evidence.
- HOT-PATH TENSION: resolver_compiler.py deliberately inlines the override-guard/navigate/closed-check preamble across all six compiled closures to hold the per-node frame at 1. Do NOT propose extracting shared hot-path helpers unless you can argue it is frame-count-neutral — set hot_path=true and name the invariant. Off-hot-path clarity is the open ground.
- For every finding set invariant_at_risk to the thing the change must not break (frame count / 100% coverage / zero-dep / behavior), or "none".
- No lint/style (ruff/ty own it). No behavior changes dressed as readability — if it changes semantics, it is out of scope.
- If a structural idea matches a settled decision (e.g. "fold ContextRegistry into Container", "provider-facing seam"), name it in settled_ref.
- Set guard_scenario="n/a", leverage (clarity bought), risk, confidence.

Aim for 6-16 findings. Return the structured object with lens="readability".`

const verifierPrompt = (lens, finding, ctx) => {
  const f = JSON.stringify(finding, null, 2)
  if (lens === 'read-real-code') {
    return `You are the READ-REAL-CODE verifier for a refactor-audit finding. Open the cited file at the cited line and confirm the code ACTUALLY does what the finding claims. Finders hallucinate; catch it.

Default confirmed=false when uncertain. False positives waste attention.

FINDING:
${f}

DO: open the file, read the cited line + 10-30 lines of context. If the code matches the claim (the seam / cost really is there), confirmed=true. If the cited line is something else or the evidence is fabricated/misquoted, confirmed=false and quote what the code actually does. Set lens="read-real-code", settled_match="". Return the verdict.`
  }
  if (lens === 'decision-conflict') {
    return `You are the DECISION-CONFLICT verifier — the mature-repo guardrail. Decide whether this finding is GENUINELY FRESH or already settled.

SETTLED CORPUS (decisions + deferred items):
decisions: ${JSON.stringify(ctx.decisions, null, 2)}
deferred_items: ${JSON.stringify(ctx.deferred_items, null, 2)}

FINDING:
${f}

DO:
1. Check the finding against every decision holding and deferred item.
2. If it duplicates a settled ruling/deferred item WITHOUT genuinely new evidence: confirmed=false, and set settled_match to that decision slug / deferred title. Quote the holding in reasoning.
3. If it is genuinely fresh (or brings new evidence a skeptic would accept): confirmed=true, settled_match="".
Default confirmed=false when the overlap is real and the "new evidence" is thin. Set lens="decision-conflict". Return the verdict.`
  }
  // invariant-safety / leverage-realism
  return `You are the INVARIANT-SAFETY / LEVERAGE-REALISM verifier. Judge whether the finding is safe and honest, not whether it is nice.

FINDING:
${f}

DO:
- READABILITY finding (guard_scenario="n/a"): would the suggested direction preserve behavior, 100% coverage, zero-dependency, AND (if hot_path) the per-node frame count? If it silently changes semantics or would regress the hot path, confirmed=false and say why. Else confirmed=true.
- PERFORMANCE finding: is guard_scenario a REAL G-id that actually isolates the claimed cost, and is the expected-leverage estimate defensible rather than hand-waved (given the documented floor)? If the scenario mapping is wrong or the leverage is fantasy, confirmed=false. Else confirmed=true.
Default confirmed=false when uncertain. Set lens="invariant-safety", settled_match="". Return the verdict.`
}

const synthPrompt = (survivors, ctx) => `You are the synthesizer for a two-lens (performance + readability) refactor audit of modern-di. You receive findings each adversarially verified by 3 lenses (read-real-code, decision-conflict, invariant-safety). Write ONE decision-grade report.

BASELINE COMMIT: ${ctx.baseline_commit}

TRIAGE — each finding carries verifier_votes (3), plus derived flags. Assign exactly one bucket:
- already-settled — the decision-conflict verdict has a NON-EMPTY settled_match. Route here regardless of other votes; record the citation. (These exist so the next audit doesn't re-raise them.)
- Otherwise a finding must SURVIVE (read-real-code confirmed AND invariant-safety confirmed — i.e. it is real and safe/honest) to be actionable. Drop findings that fail read-real-code (hallucination) entirely.
- Among survivors, bucket by the finder's leverage/risk:
  - do-first — leverage high, risk low.
  - needs-decision — leverage high AND risk high (a maintainer must rule: an invariant or stance is in play). Also route here any survivor whose invariant_at_risk is non-trivial even at medium leverage.
  - cleanup — leverage medium/low, risk low.
  - skip — leverage low, risk high (record briefly so it's not re-found).

DEDUPLICATE first: a perf and a readability finding on the same file:line region are often one root; merge, keep the sharper title, union evidence, list both lenses.

WRITE the report to planning/audits/2026-07-19-perf-readability-audit-report.md with your Write tool, EXACTLY this structure:

# Perf & Readability Refactor Audit Report — 2026-07-19

**Spec:** planning/changes/2026-07-19.08-perf-readability-audit.md
**Baseline:** ${ctx.baseline_commit}
**Method:** Two-lens multi-agent workflow (perf + readability finders; 3-lens adversarial verify: read-real-code, decision-conflict, invariant-safety; majority survive). No code changes; perf findings are bench-mapped hypotheses.

## Summary

| Bucket | Count |
|---|---|
| do-first | … |
| needs-decision | … |
| cleanup | … |
| skip | … |
| already-settled | … |

One paragraph: the dominant themes and the single most important takeaway (e.g. "the hot path is at floor; the readable gains are off-path in exceptions.py / container.py").

## do-first
### <title>
- Lens(es): performance | readability
- File: modern_di/x.py:NN
- Leverage / Risk: high / low   ·   Confidence: high   ·   Hot path: no
- (perf only) Confirming scenario: G2 — expected leverage: …
- (readability only) Invariant guarded: none | frame-count | coverage

**What.** …

**Evidence.**
\`\`\`python
…
\`\`\`

**Direction.** … (one line, not a patch)

(repeat per finding)

## needs-decision
(same structure; add a **Decision.** line naming the invariant/stance the maintainer must weigh)

## cleanup
(same structure)

## skip
(same structure; one-line **Why skip.**)

## already-settled
### <title>
- Matches: <decision slug / deferred title>
- Lens(es): …

**Why settled.** Quote the ruling/deferred holding. (These are recorded, not actioned.)

After writing, return the structured summary (report_path + counts per bucket). If survivors is empty, still write the report with each bucket "(no findings)" and return zero counts.

SURVIVORS (verified):
${JSON.stringify(survivors, null, 2)}`

// ---------- script body ----------

phase('Discover')
const context = await agent(DISCOVER_PROMPT, {
  label: 'discover',
  schema: CONTEXT_BLOB_SCHEMA,
  model: 'haiku',
})
log(`discover: ${context.file_map.length} files, ${context.decisions.length} decisions, ${context.deferred_items.length} deferred items, ${context.guard_scenarios.length} guard scenarios @ ${context.baseline_commit}`)

phase('Find')
const lenses = [
  { lens: 'performance', prompt: PERF_FINDER_PROMPT(context) },
  { lens: 'readability', prompt: READABILITY_FINDER_PROMPT(context) },
]

// Pipeline: each lens flows Find -> Verify with no barrier between them.
const perLensVerified = await pipeline(
  lenses,
  ({ lens, prompt }) =>
    agent(prompt, { label: `find:${lens}`, phase: 'Find', schema: FINDER_RESULT_SCHEMA, model: 'haiku' }),
  (finderResult, original) => {
    const findings = finderResult?.findings ?? []
    log(`verify:${original.lens}: ${findings.length} findings entering verify`)
    return parallel(findings.map((f, i) => () =>
      parallel(['read-real-code', 'decision-conflict', 'invariant-safety'].map(vl => () =>
        agent(verifierPrompt(vl, f, context), {
          label: `verify:${original.lens}#${i}:${vl}`,
          phase: 'Verify',
          schema: VERDICT_SCHEMA,
          model: 'haiku',
        })
      )).then(votes => {
        const valid = votes.filter(Boolean)
        const decisionVote = valid.find(v => v.lens === 'decision-conflict')
        const codeVote = valid.find(v => v.lens === 'read-real-code')
        const safeVote = valid.find(v => v.lens === 'invariant-safety')
        return {
          ...f,
          verifier_votes: valid,
          settled_match: decisionVote?.settled_match ?? '',
          real: codeVote?.confirmed ?? false,
          safe_or_honest: safeVote?.confirmed ?? false,
        }
      })
    ))
  }
)

const verifiedFlat = perLensVerified.filter(Boolean).flat().filter(Boolean)
// Keep: anything matched-as-settled (for the record) OR a real+safe survivor.
const survivors = verifiedFlat.filter(v => v.settled_match || (v.real && v.safe_or_honest))
log(`verify: ${verifiedFlat.length} verified, ${survivors.length} kept (survivors + already-settled)`)

phase('Synthesize')
const summary = await agent(synthPrompt(survivors, context), {
  label: 'synth',
  phase: 'Synthesize',
  schema: SYNTH_SUMMARY_SCHEMA,
  agentType: 'general-purpose',
})

log(`synth: report at ${summary.report_path}`)
log(`synth: do-first=${summary.counts.do_first} needs-decision=${summary.counts.needs_decision} cleanup=${summary.counts.cleanup} skip=${summary.counts.skip} already-settled=${summary.counts.already_settled}`)

return summary
