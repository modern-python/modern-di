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

const finderResults = await parallel(
  findersConfig.map(({ dim, heur }) => () =>
    agent(finderPrompt(dim, heur, context), {
      label: `find:${dim}`,
      phase: 'Find',
      schema: FINDER_RESULT_SCHEMA,
    })
  )
)

const rawFindings = finderResults.filter(Boolean).flatMap(r => r.findings)
log(`find: ${rawFindings.length} raw findings across ${finderResults.filter(Boolean).length}/4 finders`)

return { finders_only: true, raw_count: rawFindings.length, findings: rawFindings }
