export const meta = {
  name: '3.0-scope-research',
  description: 'UX-weighted 3.0-scope research: UX/API/DX + integration UX (+ light perf/readability re-confirm), gated against the v3-ux prior-candidate ledger, producing a leverage-vs-risk report with a 3.0-relevance cross-tab.',
  whenToUse: 'Run to gather fresh evidence for what should ride the modern-di 3.0 breaking-change budget, beyond the five queued switches.',
  phases: [
    { title: 'Discover',   detail: 'file map + v3-ux prior-candidate ledger + decisions/deferred/switches' },
    { title: 'Find',       detail: 'three lenses: ux-api-dx, integration-ux, perf-readability re-confirm' },
    { title: 'Verify',     detail: 'read-real-code, prior-art-conflict, ux-realism; majority vote' },
    { title: 'Synthesize', detail: 'leverage-vs-risk grid + 3.0-relevance cross-tab, write report' },
  ],
}

// ---------- schemas ----------

const LEDGER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['prior_candidates', 'queued_switches'],
  properties: {
    prior_candidates: {
      type: 'array',
      description: 'Every candidate from the 2026-07-05 v3-ux report (§4 rejected, §5 shortlist of 30, appendix refuted).',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title', 'ruling'],
        properties: {
          id:     { type: 'string', description: 'e.g. API-1, ERR-8, INT-6, DOC-3' },
          title:  { type: 'string' },
          ruling: { enum: ['shipped', 'accepted', 'declined', 'deferred', 'rejected', 'refuted', 'unknown'], description: 'as recorded in the report' },
        },
      },
    },
    queued_switches: {
      type: 'array',
      description: 'The five queued 3.0 breaking switches from docs/migration/to-3.x.md.',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['change', 'signal'],
        properties: {
          change: { type: 'string' },
          signal: { type: 'string', description: 'the 2.x warning' },
        },
      },
    },
  },
}

const MAP_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['baseline_commit', 'file_map', 'decisions', 'deferred_items', 'recent_commits'],
  properties: {
    baseline_commit: { type: 'string' },
    file_map: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['path', 'lines', 'role'],
        properties: {
          path:  { type: 'string' },
          lines: { type: 'integer' },
          role:  { type: 'string' },
        },
      },
    },
    decisions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['slug', 'holding'],
        properties: { slug: { type: 'string' }, holding: { type: 'string' } },
      },
    },
    deferred_items: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'gist'],
        properties: { title: { type: 'string' }, gist: { type: 'string' } },
      },
    },
    recent_commits: { type: 'array', items: { type: 'string' } },
  },
}

const RAW_FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'title', 'surface', 'description', 'evidence', 'suggested_direction', 'leverage', 'risk', 'confidence', 'three_oh', 'prior_ref', 'integration_confidence', 'guard_scenario'],
  properties: {
    lens:                   { enum: ['ux-api-dx', 'integration-ux', 'perf-readability'] },
    title:                  { type: 'string', description: 'short noun phrase' },
    surface:                { type: 'string', description: 'the cited surface: file:line, a public API signature, an error string, or a doc path' },
    description:            { type: 'string', description: '1-3 sentences on the friction/gap and what would improve it' },
    evidence:              { type: 'string', description: 'exact signature / error text / doc quote / code snippet indicted' },
    suggested_direction:    { type: 'string', description: 'one-line direction, not a patch' },
    leverage:               { enum: ['high', 'medium', 'low'], description: 'estimated payoff for users' },
    risk:                   { enum: ['high', 'medium', 'low'], description: 'risk to an invariant, a settled stance, or backward compat' },
    confidence:             { enum: ['high', 'medium', 'low'] },
    three_oh:               { enum: ['breaking', 'non-breaking', 'post-3.0', 'n-a'], description: 'is this a breaking change (needs the 3.0 budget), a non-breaking add that could ride 3.0, post-3.0, or n/a' },
    prior_ref:              { type: 'string', description: 'if it matches a v3-ux ledger id or a decision/deferred item, name it; else ""' },
    integration_confidence: { enum: ['needs-sibling-confirmation', 'core-visible', 'n-a'], description: 'integration-ux lens only: whether it needs sibling-repo source to confirm' },
    guard_scenario:         { type: 'string', description: 'perf-readability lens only: a G-id if perf, else "n/a"' },
  },
}

const FINDER_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'findings'],
  properties: {
    lens:     { enum: ['ux-api-dx', 'integration-ux', 'perf-readability'] },
    findings: { type: 'array', items: RAW_FINDING_SCHEMA },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'confirmed', 'reasoning', 'settled_match'],
  properties: {
    lens:          { enum: ['read-real-code', 'prior-art-conflict', 'ux-realism'] },
    confirmed:     { type: 'boolean', description: 'read-real-code: the surface exists as claimed. prior-art-conflict: the finding is FRESH (not already shipped/ruled). ux-realism: real evidenced friction & defensible leverage. Default false when uncertain.' },
    reasoning:     { type: 'string' },
    settled_match: { type: 'string', description: 'prior-art-conflict only: the ledger id / decision / deferred item this duplicates, or "".' },
  },
}

const SYNTH_SUMMARY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['report_path', 'counts', 'three_oh_counts'],
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
    three_oh_counts: {
      type: 'object',
      additionalProperties: false,
      required: ['breaking', 'non_breaking', 'post_3_0'],
      properties: {
        breaking:     { type: 'integer' },
        non_breaking: { type: 'integer' },
        post_3_0:     { type: 'integer' },
      },
    },
  },
}

// ---------- prompts ----------

const LEDGER_PROMPT = `You are the ledger agent for a modern-di 3.0-scope research pass. Extract the prior-decision guardrail so downstream finders do not re-surface settled or shipped ideas. Do NOT analyze or opine.

1. Read planning/audits/2026-07-05-v3-ux-research-report.md. Extract EVERY candidate:
   - Section 4 (consciously rejected field practices),
   - Section 5 (the ranked shortlist of 30 — headers like "### 1. API-1 — ..."),
   - the appendix refuted candidates.
   For each: its id (API-1, ERR-8, INT-6, DOC-3, ...), a short title, and its ruling as the report records it — map to one of: shipped, accepted, declined, deferred, rejected, refuted, unknown. Look for **Ruling:** / **Verdict:** lines and the summary table near the top.

2. Read docs/migration/to-3.x.md and extract the five queued 3.0 switches (the "five switches" table): each change + its 2.x signal.

Return the structured object. Be complete on the 30 shortlist candidates — this is the guardrail.`

const MAP_PROMPT = `You are the map agent for a modern-di 3.0-scope research pass. Produce a structured context blob. Do NOT analyze.

1. baseline_commit: \`git rev-parse --short HEAD\`.
2. file_map: every file under modern_di/ (path, line count, one-line role), plus top-level docs structure (README.md, docs/ subdirs at one level) and modern_di/integrations.py. Skip __pycache__.
3. decisions: every planning/decisions/*.md — slug + one-line holding.
4. deferred_items: every deferred.md "## " item — title + one-line gist.
5. recent_commits: \`git log --oneline -30\` subject lines (signals what shipped since 2026-07-05).

Return the structured blob.`

const UX_FINDER_PROMPT = (ctx) => `You are the UX / API / DX lens finder for a modern-di 3.0-scope research pass (zero-dependency Python DI library). Find concrete, evidenced friction in the developer experience of the CORE library that 3.0 (or a near-term minor) could improve.

CONTEXT (file map + the prior-candidate ledger you MUST respect + queued switches + decisions/deferred):
${JSON.stringify(ctx, null, 2)}

SCOPE: API ergonomics, error/diagnostic quality, docs/onboarding, surprising defaults, naming, discoverability. Read the ACTUAL source and docs (modern_di/*.py, exceptions.py, container.py, providers/*, README.md, docs/). The blob is a map.

RULES:
- Cite a real surface: a signature, an error string, a default, a doc path. Quote it as evidence. No opinion without a cited surface.
- GUARDRAIL: check every idea against prior_candidates (the v3-ux ledger) and decisions/deferred. If it is already shipped/accepted/declined/deferred/rejected, only raise it with GENUINELY NEW evidence and name it in prior_ref. The five queued_switches are settled facts, not findings.
- Tag three_oh for each: "breaking" (needs the 3.0 budget), "non-breaking" (an add that could ride 3.0 or a minor), "post-3.0", or "n-a".
- Respect the fixed stances: zero-dependency, sync-only resolution, conservative feature set, no exec/codegen. Do not propose them.
- Set integration_confidence="n-a" and guard_scenario="n/a" for this lens. Set leverage/risk/confidence.

Aim for 6-14 findings; quality over quantity. Return the structured object with lens="ux-api-dx".`

const INTEGRATION_FINDER_PROMPT = (ctx) => `You are the INTEGRATION-UX lens finder for a modern-di 3.0-scope research pass. Assess the developer experience of adopting modern-di INSIDE a host framework (12 sibling integrations: aiohttp, FastAPI, FastStream, Litestar, Starlette, Typer, Flask, gRPC, Celery, arq, taskiq, aiogram).

CONTEXT:
${JSON.stringify(ctx, null, 2)}

IMPORTANT LIMITATION: the sibling integration repos are NOT in this working tree. Work from: (a) planning/audits/2026-07-05-v3-ux-research-report.md section 3.4 (integration shape) and its INT-* / A2 candidates, (b) architecture/integration-kit.md, (c) modern_di/integrations.py (the core seam), (d) deferred.md's A2 "blessed-ready" and INT-6 items. For anything you cannot confirm from these, set integration_confidence="needs-sibling-confirmation".

FOCUS: the @inject asymmetry (7 of 12 integrations require it, 4 do not), one-import setup / blessed-readiness (A2), lifespan wiring boilerplate, the resolve entry-point (resolve_dependency), and whether the core seam forces per-integration re-implementation.

RULES:
- Cite a surface (a core seam in integrations.py / integration-kit.md, or a specific v3-ux finding). Quote evidence.
- GUARDRAIL: check against prior_candidates + deferred (A2, INT-1..6); name matches in prior_ref; only re-raise settled items with new evidence.
- Tag three_oh and integration_confidence for each. guard_scenario="n/a".

Aim for 3-8 findings. Return the structured object with lens="integration-ux".`

const PERF_READ_FINDER_PROMPT = (ctx) => `You are the PERF + READABILITY RE-CONFIRM lens for a modern-di 3.0-scope research pass. This is a LIGHT pass, not a re-audit: performance and readability were both audited and actioned THIS session (see planning/audits/2026-07-19-perf-readability-audit-report.md and PRs #356-358 in recent_commits). Perf is at its documented floor; readability findings were fixed.

CONTEXT:
${JSON.stringify(ctx, null, 2)}

ONLY report a finding if it is one of:
- NEW: a perf or readability issue the 2026-07-19 audit did not cover (read that report's buckets first — do not repeat them).
- REGRESSED: something the recent PRs (#356-358) may have worsened.
- NEWLY-ENABLED: a perf or readability improvement that a 3.0 BREAKING change would unlock (e.g. removing a deprecated param or the self-heal path lets a hot-path branch go away). Tag three_oh="breaking" and name the switch.

RULES:
- Cite real file:line + evidence. Respect the settled perf stances (no exec, child-lazy-alloc-declined, warm-singleton memo-swap dropped) via prior_ref.
- perf findings: set guard_scenario to a G-id. readability: guard_scenario="n/a". integration_confidence="n-a".
- Returning an EMPTY list is the expected default if nothing qualifies.

Aim for 0-5 findings. Return the structured object with lens="perf-readability".`

const verifierPrompt = (lens, finding, ctx) => {
  const f = JSON.stringify(finding, null, 2)
  if (lens === 'read-real-code') {
    return `You are the READ-REAL-CODE verifier for a 3.0-scope research finding. Open the cited surface (file:line, or find the signature/error/doc it quotes) and confirm it exists and behaves as the finding claims. Finders hallucinate; catch it.

Default confirmed=false when uncertain.

FINDING:
${f}

DO: locate the cited surface, read enough context, and confirm the evidence quote is real and the described friction actually exists. If the surface is fabricated, misquoted, or already behaves better than claimed, confirmed=false with what it actually is. Set lens="read-real-code", settled_match="". Return the verdict.`
  }
  if (lens === 'prior-art-conflict') {
    return `You are the PRIOR-ART-CONFLICT verifier — the guardrail against re-surfacing the v3-ux report's own conclusions or already-shipped work.

PRIOR CANDIDATES (v3-ux ledger): ${JSON.stringify(ctx.prior_candidates, null, 2)}
DECISIONS: ${JSON.stringify(ctx.decisions, null, 2)}
DEFERRED: ${JSON.stringify(ctx.deferred_items, null, 2)}
QUEUED SWITCHES (settled, not findings): ${JSON.stringify(ctx.queued_switches, null, 2)}

FINDING:
${f}

DO: decide if the finding duplicates a ledger candidate (shipped/accepted/declined/deferred/rejected), a decision, a deferred item, or a queued switch, WITHOUT genuinely new evidence. If so: confirmed=false, settled_match=<id/slug/title>, quote the ruling. If genuinely fresh (or new evidence a skeptic accepts): confirmed=true, settled_match="". Default confirmed=false when the overlap is real and the "new evidence" is thin. Set lens="prior-art-conflict". Return the verdict.`
  }
  // ux-realism
  return `You are the UX-REALISM / LEVERAGE verifier. Judge whether the finding is a real, evidenced UX problem worth a maintainer's attention — not a preference or a style opinion.

FINDING:
${f}

DO: confirm the friction is anchored in a concrete cited surface (signature, error text, default, doc gap) and that a real user would hit it; and that the leverage tag is defensible, not inflated. For an integration-ux finding flagged needs-sibling-confirmation, confirm it is at least plausible from the core seam / prior research. If it is opinion, unfalsifiable, or trivially low-impact dressed as high leverage, confirmed=false. Else confirmed=true. Default false when uncertain. Set lens="ux-realism", settled_match="". Return the verdict.`
}

const synthPrompt = (survivors, ctx) => `You are the synthesizer for a modern-di 3.0-scope research pass. You receive findings each adversarially verified by 3 lenses (read-real-code, prior-art-conflict, ux-realism). Write ONE report that feeds the 3.0 scope decision.

BASELINE COMMIT: ${ctx.baseline_commit}
QUEUED 3.0 SWITCHES (already settled — list them in the report as context, never as findings): ${JSON.stringify(ctx.queued_switches, null, 2)}

TRIAGE — each finding carries verifier_votes (3) + derived flags.
- already-settled — the prior-art-conflict verdict has a NON-EMPTY settled_match. Route here regardless of other votes; cite the match. (Recorded so they don't resurface.)
- Otherwise a finding must SURVIVE (read-real-code confirmed AND ux-realism confirmed) to be actionable. Drop findings failing read-real-code (hallucination).
- Bucket survivors by leverage/risk:
  - do-first — leverage high, risk low.
  - needs-decision — leverage high AND risk high, OR any finding tagged three_oh="breaking" (a breaking change is always a maintainer decision for the budget).
  - cleanup — leverage medium/low, risk low.
  - skip — leverage low, risk high.

DEDUPLICATE across lenses first.

WRITE the report to planning/audits/2026-07-19-3.0-scope-research-report.md with your Write tool. Structure:

# modern-di 3.0-Scope Research Report — 2026-07-19

**Spec:** planning/changes/2026-07-19.12-3.0-scope-research.md
**Baseline:** ${ctx.baseline_commit}
**Method:** UX-weighted multi-agent workflow (ux-api-dx + integration-ux + light perf/readability re-confirm; 3-lens adversarial verify: read-real-code, prior-art-conflict, ux-realism; majority survive). Gated against the 2026-07-05 v3-ux prior-candidate ledger. No code changes; informs the 3.0 scope brainstorm.

## The five queued switches (settled context, not findings)
(bullet each queued switch)

## Summary

| Bucket | Count |
|---|---|
| do-first | … |
| needs-decision | … |
| cleanup | … |
| skip | … |
| already-settled | … |

### 3.0-relevance cross-tab
| 3.0 relevance | Count |
|---|---|
| breaking (needs budget) | … |
| non-breaking (could ride 3.0) | … |
| post-3.0 | … |

One paragraph: the takeaway for scoping 3.0 — what (if anything) beyond the five switches earns the breaking budget, and the strongest non-breaking adds.

## do-first
### <title>
- Lens: ux-api-dx | integration-ux | perf-readability
- Surface: <file:line / signature / error / doc>
- Leverage / Risk: high / low   ·   Confidence: high   ·   3.0: breaking | non-breaking | post-3.0
- (integration only) Confidence caveat: needs-sibling-confirmation | core-visible

**What.** …

**Evidence.**
\`\`\`
…
\`\`\`

**Direction.** …

(repeat per finding)

## needs-decision
(same; add a **Decision.** line naming the budget/stance/compat call — breaking findings live here)

## cleanup
(same structure)

## skip
(same structure; one-line **Why skip.**)

## integration-ux (confidence-flagged)
(collect the integration-ux survivors here regardless of bucket, each with its confidence caveat, so the reader weighs them knowing the sibling repos were not read)

## already-settled
### <title>
- Matches: <ledger id / decision / deferred>
**Why settled.** Quote the ledger ruling / decision.

After writing, return the structured summary (report_path, counts per bucket, three_oh_counts). If survivors is empty, still write the report with buckets "(no findings)" and return zeros.

SURVIVORS (verified):
${JSON.stringify(survivors, null, 2)}`

// ---------- script body ----------

phase('Discover')
const [ledger, map] = await parallel([
  () => agent(LEDGER_PROMPT, { label: 'discover:ledger', phase: 'Discover', schema: LEDGER_SCHEMA, model: 'haiku' }),
  () => agent(MAP_PROMPT, { label: 'discover:map', phase: 'Discover', schema: MAP_SCHEMA, model: 'haiku' }),
])
if (!ledger || !map) {
  log('discover failed; aborting')
  return { report_path: null, error: 'discover agent returned null' }
}
const context = { ...map, ...ledger }
log(`discover: ${context.file_map.length} files, ${context.prior_candidates.length} prior candidates, ${context.queued_switches.length} queued switches, ${context.decisions.length} decisions @ ${context.baseline_commit}`)

phase('Find')
const lenses = [
  { lens: 'ux-api-dx',       prompt: UX_FINDER_PROMPT(context) },
  { lens: 'integration-ux',  prompt: INTEGRATION_FINDER_PROMPT(context) },
  { lens: 'perf-readability', prompt: PERF_READ_FINDER_PROMPT(context) },
]

const perLensVerified = await pipeline(
  lenses,
  ({ lens, prompt }) =>
    agent(prompt, { label: `find:${lens}`, phase: 'Find', schema: FINDER_RESULT_SCHEMA, model: 'haiku' }),
  (finderResult, original) => {
    const findings = finderResult?.findings ?? []
    log(`verify:${original.lens}: ${findings.length} findings entering verify`)
    return parallel(findings.map((f, i) => () =>
      parallel(['read-real-code', 'prior-art-conflict', 'ux-realism'].map(vl => () =>
        agent(verifierPrompt(vl, f, context), {
          label: `verify:${original.lens}#${i}:${vl}`,
          phase: 'Verify',
          schema: VERDICT_SCHEMA,
          model: 'haiku',
        })
      )).then(votes => {
        const valid = votes.filter(Boolean)
        const priorVote = valid.find(v => v.lens === 'prior-art-conflict')
        const codeVote = valid.find(v => v.lens === 'read-real-code')
        const realVote = valid.find(v => v.lens === 'ux-realism')
        return {
          ...f,
          verifier_votes: valid,
          settled_match: priorVote?.settled_match ?? '',
          real: codeVote?.confirmed ?? false,
          worthwhile: realVote?.confirmed ?? false,
        }
      })
    ))
  }
)

const verifiedFlat = perLensVerified.filter(Boolean).flat().filter(Boolean)
const survivors = verifiedFlat.filter(v => v.settled_match || (v.real && v.worthwhile))
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
log(`synth: 3.0 breaking=${summary.three_oh_counts.breaking} non-breaking=${summary.three_oh_counts.non_breaking} post-3.0=${summary.three_oh_counts.post_3_0}`)

return summary
