export const meta = {
  name: 'bug-hunt-audit',
  description: 'Four-dimension (UX/security/tests/logic) bug-hunt audit of modern-di with adversarial verify and triaged report.',
  whenToUse: 'Run when you want a fresh triaged backlog of bugs and quality risks across the modern-di repo.',
  phases: [
    { title: 'Discover', detail: 'map files, extract behavior claims' },
    { title: 'Find',     detail: 'four parallel dimension finders' },
    { title: 'Verify',   detail: 'three lenses per finding, majority vote' },
    { title: 'Synthesize', detail: 'dedup, triage, write report' },
  ],
}

const CONTEXT_BLOB_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['file_map', 'behavior_claims', 'recent_commits'],
  properties: {
    file_map: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['path', 'lines', 'role'],
        properties: {
          path:  { type: 'string' },
          lines: { type: 'integer' },
          role:  { type: 'string', description: 'one-line summary of what this file is responsible for' },
        },
      },
    },
    behavior_claims: {
      type: 'array',
      description: 'Claims made in CLAUDE.md / README.md / docstrings about how the library behaves, with source.',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['claim', 'source'],
        properties: {
          claim:  { type: 'string' },
          source: { type: 'string', description: 'e.g. "CLAUDE.md: Scope hierarchy" or "modern_di/container.py docstring"' },
        },
      },
    },
    recent_commits: {
      type: 'array',
      description: 'Recent commit subjects from git log, useful as priors for where churn is.',
      items: { type: 'string' },
    },
  },
}

const RAW_FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['dimension', 'title', 'file', 'line', 'description', 'evidence', 'repro', 'suggested_fix', 'severity', 'confidence_finder'],
  properties: {
    dimension:        { enum: ['ux', 'security', 'tests', 'logic'] },
    title:            { type: 'string', description: 'short noun phrase' },
    file:             { type: 'string', description: 'relative path' },
    line:             { type: 'string', description: 'integer or "start-end" range, as string' },
    description:      { type: 'string', description: '1-3 sentences on what is wrong' },
    evidence:         { type: 'string', description: 'exact code snippet or doc quote indicted' },
    repro:            { type: 'string', description: 'minimal scenario; code for code-bugs, prose for docs/UX' },
    suggested_fix:    { type: 'string', description: 'one-line direction, not a patch' },
    severity:         { enum: ['high', 'medium', 'low'] },
    confidence_finder:{ enum: ['high', 'medium', 'low'] },
  },
}

const FINDER_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['dimension', 'findings'],
  properties: {
    dimension: { enum: ['ux', 'security', 'tests', 'logic'] },
    findings:  { type: 'array', items: RAW_FINDING_SCHEMA },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'confirmed', 'reasoning', 'reclassification'],
  properties: {
    lens:             { enum: ['reproduce', 'read-real-code', 'spec-vs-behavior'] },
    confirmed:        { type: 'boolean', description: 'true if the lens confirms the finding; default to false when uncertain' },
    reasoning:        { type: 'string', description: '1-3 sentences. For reproduce: the constructed repro or why it could not be. For read-real-code: what the cited code actually does. For spec-vs-behavior: how the docs and code line up.' },
    reclassification: { enum: ['bug-in-code', 'bug-in-spec', 'intended-behavior', 'unknown'], description: 'only spec-vs-behavior lens uses non-unknown values; other lenses set "unknown"' },
  },
}

const SYNTH_SUMMARY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['report_path', 'counts'],
  properties: {
    report_path: { type: 'string', description: 'absolute or repo-relative path to the written report' },
    counts: {
      type: 'object',
      additionalProperties: false,
      required: ['must_fix_now', 'should_fix_soon', 'nice_to_have', 'spec_fix', 'wont_fix'],
      properties: {
        must_fix_now:    { type: 'integer' },
        should_fix_soon: { type: 'integer' },
        nice_to_have:    { type: 'integer' },
        spec_fix:        { type: 'integer' },
        wont_fix:        { type: 'integer' },
      },
    },
  },
}

const DISCOVER_PROMPT = `You are the discover agent for a bug-hunt audit of the modern-di repository (a zero-dependency Python DI library). Produce a single structured context blob that downstream finder agents will use to ground their work.

Do exactly the following, then return the structured output:

1. Walk the repo from its root. Build a file_map covering:
   - every file under modern_di/ (source)
   - every file under tests/ (test suite)
   - every file under benchmarks/
   - top-level docs: README.md, CLAUDE.md
   - planning/specs/2026-06-05-bug-hunt-audit-design.md (the audit spec — relevant context)
   Skip .venv, .pytest_cache, .ruff_cache, .git, .benchmarks, .idea, __pycache__.
   For each file: relative path, line count, and a one-line role describing its responsibility.

2. Extract behavior_claims from README.md and CLAUDE.md and the docstrings of the main public modules (modern_di/__init__.py, modern_di/container.py, modern_di/scope.py, modern_di/group.py). A claim is a concrete statement about how the library behaves — e.g. "Scope is an IntEnum with five levels APP < SESSION < REQUEST < ACTION < STEP" or "ContextProvider is for runtime values injected at container creation". For each claim record the exact source (file + section/identifier). 20-50 claims is the right order of magnitude — be selective; only claims a finder could compare against code.

3. Grab the last 20 commits from \`git log --oneline -20\` and put the subject lines in recent_commits.

Do not analyze, do not look for bugs, do not opine. Just produce the context blob. Other agents do the analysis.`

function finderPrompt(dimension, heuristics, context) {
  return `You are the ${dimension}-dimension finder for a bug-hunt audit of the modern-di repository (zero-dependency Python DI library).

CONTEXT BLOB (file map and behavior claims, provided by the discover agent):
${JSON.stringify(context, null, 2)}

YOUR JOB:
Find concrete, defensible findings in the ${dimension} dimension. For each finding:
- name the exact file and line (or line range) — required, no exceptions
- quote the exact code or doc text as "evidence" — required
- describe what is wrong in 1-3 sentences
- give a minimal reproduction (code for code-bugs, prose for docs/UX issues)
- propose a one-line fix direction (not a patch)
- assign severity (high/medium/low) and your own confidence (high/medium/low)

RULES:
- No speculation. If you cannot quote a specific file:line that demonstrates the issue, do not include it.
- Read the actual file before claiming. The context blob is a map, not the source. Use your file-reading tools to open the cited file before writing a finding.
- Do not flag style or lint issues. ruff and ty already enforce those in CI.
- Do not propose performance improvements unless they cross into correctness (unbounded growth, hangs, pathological complexity that becomes DoS).
- Findings about sibling repos (modern-di-pytest, FastAPI / FastStream / LiteStar / Typer integrations) are OUT OF SCOPE. Stay in this repo only.

DIMENSION-SPECIFIC HEURISTICS:
${heuristics}

OUTPUT:
Return the structured object. Aim for 5-20 findings; quality over quantity. Returning an empty findings list is acceptable if the dimension truly has nothing actionable.`
}

const UX_HEURISTICS = `Audit developer experience (not end-user UI — this is a library).
- Error message quality. Open modern_di/errors.py and modern_di/exceptions.py. Cross-reference every error template against its raise sites. Does each error name the offending type, provider, and scope, or just describe a category?
- API friction. Required-but-unintuitive kwargs. Footguns: skip_creator_parsing semantics, validate=True cost claims, cache_settings=CacheSettings() as the singleton-by-other-name pattern, kwargs={} bypassing type-based resolution.
- Surprising defaults. What happens with no groups=, no context=, default scope, default cache_settings?
- Doc-vs-behavior divergence. README and CLAUDE.md claims (see behavior_claims in the context blob) vs. real signatures, exports, scope rules. A doc that says "X" while the code does "Y" is a UX finding.`

const SECURITY_HEURISTICS = `Audit security. Small surface for a zero-dep DI library, but real.
- types_parser evaluation paths. Open modern_di/types_parser.py. Are there any eval, exec, __import__ calls when resolving forward refs or string annotations? What happens with adversarial annotation strings (e.g. Annotated[str, "malicious_payload"])?
- Override registry escape hatches. Can container.override() bypass scope guards? Can a child container's override leak to siblings via the shared registry?
- Unbounded recursion / cache growth. Cycle-detection guarantees in container.validate() and resolution paths. Child-container leak on long-lived parents (does parent hold refs to children?). ContextRegistry / CacheRegistry size bounds.
- Unsafe __reduce__ / pickling paths on providers, registries, or Container. Look for any __reduce__, __getstate__, __setstate__ implementations.`

const TESTS_HEURISTICS = `Audit the test suite as a target — these are bugs IN tests, not bugs FOUND BY tests.
- Assertions that do not test the claim. e.g. assert result is not None when the docstring or test name promises structure or value verification.
- Branches with coverage but no behavioral assertion. The recent "full cov require" / "Use typing.List[int] in non-class bound_type test for 3.10 coverage" commits suggest coverage was tightened — easy to game by adding code execution without assertions. Look for tests that call into code but only assert "no exception raised" when a return value or side effect is the real contract.
- Missing edges. Scope mismatch errors. Cycle detection. Async finalizer in sync close. Override reset semantics. Deep child-container chains. PEP 604 unions in types_parser.
- Fixtures that paper over bugs. e.g. function-scoped fresh container hides cross-test cache bleed that would otherwise surface.
- Undocumented xfail / skip / flake markers — anything without a clear "Why:" comment is a finding.`

const LOGIC_HEURISTICS = `Audit correctness.
- Scope rules. CLAUDE.md says: a provider can only be resolved from a container of the same or deeper scope. Verify the guard fires on every resolution path (Factory, ContextProvider, container_provider, Alias). Trace find_container(scope) on the parent chain.
- Cache lifecycle. Child cache vs parent cache isolation. Behavior on close() mid-resolution. Finalizer order (LIFO vs insertion order). Sync close() with an async finalizer — the recent "Raise on async finalizer in close_sync" commit suggests this path now raises; verify it actually does on every code path that calls close_sync.
- Override propagation. Shared overrides_registry semantics across the container tree. reset behavior. Interaction with caching (cached value present before override registered — does override take effect?).
- types_parser correctness. PEP 604 unions (X | Y), Optional, Annotated, TYPE_CHECKING strings, forward refs, generics, *args / **kwargs, default-valued params, Self.
- Container tree edges. build_child_container called on a closed parent? on the same parent concurrently? with a shallower scope than parent? With validate=True after cycles introduced post-creation?`

function verifierPrompt(lens, finding) {
  const findingJson = JSON.stringify(finding, null, 2)

  if (lens === 'reproduce') {
    return `You are the REPRODUCE verifier for a bug-hunt audit finding.

Your job: try to construct the minimum scenario that would actually trigger the claimed bug. If you can build a repro, the finding is confirmed. If you cannot — for any reason: the claim is too vague, the cited code does not exhibit the described behavior, the repro requires unrealistic conditions, the code path is unreachable — the finding is REFUTED.

IMPORTANT: Default to "confirmed=false" when uncertain. False positives waste user attention more than false negatives.

FINDING:
${findingJson}

DO:
1. Open the cited file and read the surrounding context.
2. Construct (in your head or on paper) the smallest scenario that would trigger the bug: setup code, the trigger call, the observable wrong behavior.
3. If the scenario holds together, set confirmed=true and put the repro sketch in reasoning.
4. If it does not hold together, set confirmed=false and explain why in reasoning.

Set lens="reproduce" and reclassification="unknown" (this lens does not reclassify).

Return the structured verdict.`
  }

  if (lens === 'read-real-code') {
    return `You are the READ-REAL-CODE verifier for a bug-hunt audit finding.

Your job: open the cited file at the cited line and confirm the code actually does what the finding claims. Many finder agents hallucinate; this lens catches that.

IMPORTANT: Default to "confirmed=false" when uncertain. False positives waste user attention more than false negatives.

FINDING:
${findingJson}

DO:
1. Open the file at the cited path. Read the cited line plus enough surrounding context (10-30 lines) to understand control flow.
2. Compare what the code actually does to what the finding's description and evidence claim.
3. If the code matches the claim (the bug really is in this code at this location), set confirmed=true.
4. If the code does not match — the cited line is something else, the claim describes behavior the code does not exhibit, the evidence quote is fabricated or paraphrased badly — set confirmed=false. Quote what the code actually does in reasoning.

Set lens="read-real-code" and reclassification="unknown" (this lens does not reclassify).

Return the structured verdict.`
  }

  // spec-vs-behavior
  return `You are the SPEC-VS-BEHAVIOR verifier for a bug-hunt audit finding.

Your job: cross-check the finding against the project's specifications (CLAUDE.md, README.md, relevant docstrings). Decide whether this is a bug in the code, a bug in the spec, or actually intended behavior that the finder misjudged.

IMPORTANT: Default to "confirmed=false" when uncertain. False positives waste user attention more than false negatives.

FINDING:
${findingJson}

DO:
1. Re-read the relevant section of CLAUDE.md (e.g. "Scope hierarchy", "Resolution flow", "Registries").
2. Re-read the relevant docstrings.
3. Decide:
   - If the code violates a documented spec OR violates an obvious correctness contract not contradicted by spec: confirmed=true, reclassification="bug-in-code".
   - If the spec says X but code does Y and the code's Y is the obviously correct behavior: confirmed=true, reclassification="bug-in-spec".
   - If the spec explicitly endorses the behavior the finder flagged (e.g. "resolution is sync-only", "conservative feature set"): confirmed=false, reclassification="intended-behavior". Quote the spec line in reasoning.
   - If uncertain: confirmed=false, reclassification="unknown".

Set lens="spec-vs-behavior".

Return the structured verdict.`
}

function synthPrompt(survivors) {
  return `You are the synthesizer for a bug-hunt audit of the modern-di repository. You receive the surviving findings (each adversarially verified by 3 lenses, majority-confirmed). Your job:

1. DEDUPLICATE across dimensions. A "weak assertion" finding from tests and a "missed edge" from logic are often the same root issue. Merge them: keep the more specific title, union the evidence, list both source dimensions.

2. TRIAGE every surviving finding into exactly one bucket:
   - must-fix-now — correctness (logic dimension) or security, severity "high", all 3 verifier votes confirmed (verifier_votes.filter(v => v.confirmed).length === 3).
   - should-fix-soon — severity "high" with 2/3 verifier confirmation, OR severity "medium" with 3/3 confirmation AND dimension is logic or security.
   - nice-to-have — UX rough edges, low-severity logic findings, test weaknesses not currently masking known bugs.
   - spec-fix — reclassification is "bug-in-spec" (regardless of severity). Code is correct; docs are wrong.
   - wont-fix — reclassification is "intended-behavior". Record so they don't resurface next audit.
   Findings outside these definitions: drop to nice-to-have.

3. WRITE the report to planning/audits/2026-06-05-bug-hunt-audit-report.md using your Write tool. Use this exact structure:

\`\`\`markdown
# Bug-Hunt Audit Report — 2026-06-05

**Spec:** planning/specs/2026-06-05-bug-hunt-audit-design.md
**Plan:** planning/plans/2026-06-05-bug-hunt-audit-plan.md
**Survivors:** N findings post-verify, M after dedup

## Summary

| Bucket | Count |
|---|---|
| must-fix-now | … |
| should-fix-soon | … |
| nice-to-have | … |
| spec-fix | … |
| wont-fix | … |

## must-fix-now

### <Finding title>
- Dimension(s): logic
- File: modern_di/container.py:120-128
- Severity: high
- Verifier confirmations: 3/3

**Description.** …

**Evidence.**
\\\`\\\`\\\`python
…
\\\`\\\`\\\`

**Reproduction.**
\\\`\\\`\\\`python
…
\\\`\\\`\\\`

**Suggested fix.** …

(repeat per finding)

## should-fix-soon
(same structure)

## nice-to-have
(same structure)

## spec-fix
(same structure, but "Suggested fix" describes the doc/spec edit)

## wont-fix
(same structure, plus a final line "Rationale:" quoting the spec/CLAUDE.md line that endorses this behavior)
\`\`\`

4. After writing the report, return the structured summary (report_path = "planning/audits/2026-06-05-bug-hunt-audit-report.md", counts per bucket).

SURVIVORS (already verified):
${JSON.stringify(survivors, null, 2)}

If survivors is empty, still write the report file with each bucket marked "(no findings)" and return zero counts.`
}

// --- script body ---

phase('Discover')
const context = await agent(DISCOVER_PROMPT, {
  label: 'discover',
  schema: CONTEXT_BLOB_SCHEMA,
})
log(`discover: ${context.file_map.length} files mapped, ${context.behavior_claims.length} claims extracted`)

phase('Find')
const findersConfig = [
  { dim: 'ux',       heur: UX_HEURISTICS },
  { dim: 'security', heur: SECURITY_HEURISTICS },
  { dim: 'tests',    heur: TESTS_HEURISTICS },
  { dim: 'logic',    heur: LOGIC_HEURISTICS },
]

// Pipeline: each dimension flows through Find (1 finder) → Verify (3 verifiers per finding, majority vote).
// No barrier between Find and Verify — dimension A's findings start verifying while dimension B is still finding.
const perDimensionVerified = await pipeline(
  findersConfig,
  // Stage 1: Find
  ({ dim, heur }) =>
    agent(finderPrompt(dim, heur, context), {
      label: `find:${dim}`,
      phase: 'Find',
      schema: FINDER_RESULT_SCHEMA,
    }),
  // Stage 2: Verify every finding in this dimension (3 lenses each, majority vote)
  (finderResult, original) => {
    const findings = finderResult?.findings ?? []
    log(`verify:${original.dim}: ${findings.length} findings entering verify`)
    return parallel(findings.map((f, i) => () =>
      parallel(['reproduce', 'read-real-code', 'spec-vs-behavior'].map(lens => () =>
        agent(verifierPrompt(lens, f), {
          label: `verify:${original.dim}#${i}:${lens}`,
          phase: 'Verify',
          schema: VERDICT_SCHEMA,
        })
      ))
      .then(votes => {
        const valid = votes.filter(Boolean)
        const confirms = valid.filter(v => v.confirmed).length
        const survives = confirms >= 2
        // Use spec-vs-behavior verdict if present, else "unknown"
        const specVote = valid.find(v => v.lens === 'spec-vs-behavior')
        const reclassification = specVote?.reclassification ?? 'unknown'
        return {
          ...f,
          verifier_votes: valid,
          survives,
          reclassification,
        }
      })
    ))
  }
)

const verifiedFlat = perDimensionVerified.filter(Boolean).flat().filter(Boolean)
const survivors = verifiedFlat.filter(v => v.survives)
log(`verify: ${verifiedFlat.length} verified, ${survivors.length} survived majority vote`)

phase('Synthesize')
const summary = await agent(synthPrompt(survivors), {
  label: 'synth',
  phase: 'Synthesize',
  schema: SYNTH_SUMMARY_SCHEMA,
  agentType: 'general-purpose',
})

log(`synth: report written to ${summary.report_path}`)
log(`synth: must=${summary.counts.must_fix_now} should=${summary.counts.should_fix_soon} nice=${summary.counts.nice_to_have} spec=${summary.counts.spec_fix} wont=${summary.counts.wont_fix}`)

return summary
