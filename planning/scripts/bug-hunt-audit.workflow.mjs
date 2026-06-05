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

// --- script body ---

phase('Discover')
const context = await agent(DISCOVER_PROMPT, {
  label: 'discover',
  schema: CONTEXT_BLOB_SCHEMA,
})
log(`discover: ${context.file_map.length} files mapped, ${context.behavior_claims.length} claims extracted`)

return { discover_only: true, context }
