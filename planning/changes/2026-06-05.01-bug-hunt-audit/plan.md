---
status: shipped
date: 2026-06-05
slug: bug-hunt-audit
spec: design.md
---

# Bug-Hunt Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the single Workflow script that, when invoked, runs the four-dimension bug-hunt audit defined in `planning/specs/2026-06-05-bug-hunt-audit-design.md` and produces a triaged report at `planning/audits/2026-06-05-bug-hunt-audit-report.md`.

**Architecture:** One self-contained `.mjs` workflow script with four phases (discover → find → verify → synthesize). Schemas + prompts live inline. Synthesizer agent writes the final markdown report directly via its Write tool. No code changes to `modern_di/` — this plan builds the audit harness, not bug fixes.

**Tech Stack:** Claude Code Workflow tool (JS/ESM script body using `agent()`, `pipeline()`, `parallel()`, `phase()`, `log()`); JSON Schema for structured outputs; Markdown for the final report.

---

## File structure

**Created by this plan:**
- `planning/scripts/bug-hunt-audit.workflow.mjs` — the workflow script (single file, holds meta + schemas + prompts + phase orchestration).

**Created by the workflow at execution time:**
- `planning/audits/2026-06-05-bug-hunt-audit-report.md` — the audit report (written by the synth agent via its Write tool).

**Not touched:** Nothing in `modern_di/`, `tests/`, `benchmarks/`, or `docs/`. The audit reads these but the harness does not modify them.

---

## Background — primitives you must know

The engineer reading this may not have used the Workflow tool. Quick reference:

- `phase(title)` — start a named phase; agents launched after this call are grouped under it in the progress display.
- `agent(prompt, opts?)` — spawn one subagent. Returns its final text by default. With `opts.schema` (a JSON Schema), the subagent is forced to return a validated object. With `opts.agentType` you can switch to e.g. `'general-purpose'` to ensure broad tool access.
- `parallel([thunks])` — run concurrently with a barrier; returns array of results (failed agents → `null`).
- `pipeline(items, stage1, stage2, ...)` — each item flows through stages independently, no barrier; stage callback receives `(prevResult, originalItem, index)`.
- `log(message)` — emit progress visible to the user.
- The script body runs as ESM async code. No filesystem access from script; agents have their own tools.
- Invocation: `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})` from inside Claude Code.

---

## Task 1: Create workflow file skeleton

**Files:**
- Create: `planning/scripts/bug-hunt-audit.workflow.mjs`

- [ ] **Step 1: Create the scripts directory**

```bash
mkdir -p planning/scripts
```

- [ ] **Step 2: Write the file with meta block and an empty body that returns a stub**

Create `planning/scripts/bug-hunt-audit.workflow.mjs` with this exact content:

```js
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

// --- script body ---

log('bug-hunt-audit: skeleton invoked (no agents yet)')
return { skeleton: true }
```

- [ ] **Step 3: Verify the script parses by invoking the Workflow tool**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. Expected: workflow completes immediately with result `{ skeleton: true }`, no agents fired, four phase entries visible in `/workflows`.

If the workflow fails to parse, fix syntax inline before moving on.

- [ ] **Step 4: Commit**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "Add bug-hunt-audit workflow skeleton"
```

---

## Task 2: Define all JSON schemas

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs`

Add the schemas above the `// --- script body ---` marker. Schemas are referenced by `agent()` calls in later tasks, so they must be defined before any phase code runs.

- [ ] **Step 1: Add `CONTEXT_BLOB_SCHEMA`** (output of the discover agent)

Insert above the `// --- script body ---` marker:

```js
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
```

- [ ] **Step 2: Add `RAW_FINDING_SCHEMA`** (one finder produces an array of these)

```js
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
```

- [ ] **Step 3: Add `VERDICT_SCHEMA`** (one verifier returns this)

```js
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
```

- [ ] **Step 4: Add `SYNTH_SUMMARY_SCHEMA`** (final workflow return value)

```js
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
```

- [ ] **Step 5: Verify the script still parses**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. Expected: still returns `{ skeleton: true }`, no errors. (Schemas are unused so far — adding constants must not break parsing.)

- [ ] **Step 6: Commit**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "Add JSON schemas for bug-hunt-audit findings/verdicts"
```

---

## Task 3: Discover phase

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs`

- [ ] **Step 1: Add the discover prompt as a constant**

Insert above the `// --- script body ---` marker, after the schemas:

```js
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
```

- [ ] **Step 2: Wire the discover phase into the script body**

Replace the body of the script (the `log(...)` + stub return) with:

```js
phase('Discover')
const context = await agent(DISCOVER_PROMPT, {
  label: 'discover',
  schema: CONTEXT_BLOB_SCHEMA,
})
log(`discover: ${context.file_map.length} files mapped, ${context.behavior_claims.length} claims extracted`)

return { discover_only: true, context }
```

(The `return` is temporary — we'll remove it as later phases come online.)

- [ ] **Step 3: Run the workflow and inspect the result**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. Expected: one agent fires under the "Discover" phase, completes successfully, returns `{ discover_only: true, context: { file_map: [...], behavior_claims: [...], recent_commits: [...] } }`. The file_map should include ~25-40 files. behavior_claims should be 20-50 entries. recent_commits should have 20 lines.

If the context blob is missing entries or thin, refine the prompt and re-run before committing.

- [ ] **Step 4: Commit**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "bug-hunt-audit: implement Discover phase"
```

---

## Task 4: Four finder agents in parallel

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs`

All four finders share a common preamble (the discover context, anti-hallucination rules, output contract) and a dimension-specific heuristics block. Define the common preamble once, then four dimension prompts.

- [ ] **Step 1: Add the finder common preamble**

Insert above the `// --- script body ---` marker, after the discover prompt:

```js
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
```

- [ ] **Step 2: Add the four dimension heuristics constants**

```js
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
```

- [ ] **Step 3: Wire the Find phase into the script body**

Replace the `return { discover_only: true, context }` line with:

```js
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
```

(Still a temporary `return` — we'll remove it in Task 6 when pipelining into verify.)

- [ ] **Step 4: Run the workflow and inspect**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. Expected: discover agent runs, then four finder agents fire in parallel under "Find" phase, complete, return `{ finders_only: true, raw_count: N, findings: [...] }` where N is typically 20-80. Findings should mention real file paths from `modern_di/` and `tests/`. Spot-check 3-4 findings: does the cited file:line make sense for the claim?

If a finder returns zero findings AND nothing else fails, that is acceptable. If a finder returns obviously hallucinated paths or `file: "unknown"`, refine the rule in the common preamble and re-run before committing.

- [ ] **Step 5: Commit**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "bug-hunt-audit: implement Find phase with four parallel finders"
```

---

## Task 5: Three verifier prompts

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs`

Verifier prompts are defined here but not yet wired into the pipeline. Wiring happens in Task 6.

- [ ] **Step 1: Add the verifier prompt factory**

Insert above the `// --- script body ---` marker, after the heuristics constants:

```js
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
```

- [ ] **Step 2: Verify the script still parses**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. Expected: same `finders_only: true, raw_count: N, findings: [...]` result as Task 4 step 4. (The verifier factory is defined but unused — it must not break parsing.)

- [ ] **Step 3: Commit**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "bug-hunt-audit: add three verifier prompt builders"
```

---

## Task 6: Pipeline wiring — finders → 3 verifiers → majority vote

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs`

Replace the parallel-then-return scheme with a pipeline that begins verify the moment any finder returns. Each finding fans to three verifiers; survivors (≥2/3 confirm) accumulate.

- [ ] **Step 1: Replace the Find/return block with a pipeline**

In the script body, replace this:

```js
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
```

with:

```js
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

return { verify_only: true, total_verified: verifiedFlat.length, survivor_count: survivors.length, survivors }
```

- [ ] **Step 2: Run the workflow end-to-end through Verify**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. This is the first run that fires the full finder + verifier set — expect 30-250 agent calls, several minutes wall-clock.

Expected return:
```js
{
  verify_only: true,
  total_verified: 20-80,       // close to raw_count
  survivor_count: 5-40,        // some pruning from refute-by-default
  survivors: [...]             // each has verifier_votes, survives=true, reclassification
}
```

Spot-check 3 survivors: do their verifier_votes look like 3 distinct lens responses? Does at least 2/3 have confirmed=true? Does the reclassification value make sense?

If survivor_count is unexpectedly low (< 3) or unexpectedly high (> 60), inspect verdicts — likely a prompt issue: verifiers either too strict (defaulting to refuted on everything plausible) or too lenient (confirming hallucinations). Refine the relevant verifier prompt and re-run before committing.

- [ ] **Step 3: Commit**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "bug-hunt-audit: pipeline Find→Verify with majority vote"
```

---

## Task 7: Synthesizer phase — dedup, triage, write report

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs`
- Created by synth agent at execution time: `planning/audits/2026-06-05-bug-hunt-audit-report.md`

The synth agent receives the survivors, deduplicates cross-dimension overlaps, applies the triage rubric, and writes the final report file directly using its Write tool.

- [ ] **Step 1: Add the synth prompt**

Insert above the `// --- script body ---` marker, after the verifier factory:

```js
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
```

- [ ] **Step 2: Wire the synth phase into the script body**

Replace the `return { verify_only: true, ... }` line with:

```js
phase('Synthesize')
const summary = await agent(synthPrompt(survivors), {
  label: 'synth',
  phase: 'Synthesize',
  schema: SYNTH_SUMMARY_SCHEMA,
  agentType: 'general-purpose',  // ensure Write/Read/Bash tool access
})

log(`synth: report written to ${summary.report_path}`)
log(`synth: must=${summary.counts.must_fix_now} should=${summary.counts.should_fix_soon} nice=${summary.counts.nice_to_have} spec=${summary.counts.spec_fix} wont=${summary.counts.wont_fix}`)

return summary
```

- [ ] **Step 3: Run the full workflow end-to-end**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs"})`. This is the full audit run — expect 50-260 agent calls, 5-15 minutes wall-clock.

Expected: workflow returns `{ report_path: "planning/audits/2026-06-05-bug-hunt-audit-report.md", counts: { must_fix_now: N, ... } }`, and the report file exists on disk.

Open the report file and verify:
- All five buckets are present (even if empty)
- The summary table counts match the per-bucket finding counts
- At least one finding has all the schema fields filled in (file, line, evidence, repro, suggested fix)
- spec-fix and wont-fix findings have appropriate framing

If the synth agent fails to write the report, the most likely cause is missing Write access — confirm `agentType: 'general-purpose'` is set on the synth agent call.

If counts look wildly off (e.g. everything in must-fix-now), the triage logic in the prompt likely needs tightening. Refine and re-run.

- [ ] **Step 4: Commit the script and the report**

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs planning/audits/2026-06-05-bug-hunt-audit-report.md
git commit -m "bug-hunt-audit: implement Synthesize phase; commit first audit report"
```

---

## Task 8: Resumability verification and polish

**Files:**
- Modify: `planning/scripts/bug-hunt-audit.workflow.mjs` (only if issues found)

The workflow tool supports `resumeFromRunId` — completed agent calls return cached results. Worth verifying this works for our script so re-running after a stop or interruption is cheap.

- [ ] **Step 1: Note the runId from the prior full run**

From the Task 7 step 3 result, capture the workflow runId (visible in `/workflows` or the tool result). Format: `wf_<hex>`.

- [ ] **Step 2: Test a no-op resume**

Invoke `Workflow({scriptPath: "planning/scripts/bug-hunt-audit.workflow.mjs", resumeFromRunId: "<runId>"})`. Expected: every agent call returns its cached result instantly; total wall-clock under 30 seconds; same final summary as the original run.

If resume re-fires agents, the cache is missing some calls — check that the script body is byte-identical to the run being resumed (no whitespace edits since).

- [ ] **Step 3: Test a partial-edit resume**

Edit only the synth prompt (e.g. change one sentence in the triage instructions). Invoke `Workflow({scriptPath, resumeFromRunId: "<runId>"})` again. Expected: discover, all finders, all verifiers return cached results; only the synth agent re-fires.

This confirms the engineer can iterate on synth/triage cheaply without re-paying the verify cost.

- [ ] **Step 4: Revert the experimental edit**

```bash
git checkout -- planning/scripts/bug-hunt-audit.workflow.mjs
```

- [ ] **Step 5: Done**

No commit needed if no changes survived. If you found and fixed a real bug during resumability testing:

```bash
git add planning/scripts/bug-hunt-audit.workflow.mjs
git commit -m "bug-hunt-audit: fix <description>"
```

---

## Self-review

**Spec coverage check:**
- Goal (triaged backlog across 4 dimensions): covered by Tasks 3-7 producing the final report.
- Success criteria (file:line required; ≥2/3 verify; triage bucket; reproducible from report alone): enforced by schemas in Task 2, verify pipeline in Task 6, synth report structure in Task 7.
- Scope (`modern_di/`, `tests/`, `benchmarks/`, docs only for spec-vs-behavior): encoded in finder heuristics (Task 4) and spec-vs-behavior verifier (Task 5).
- Non-goals (no sibling repos, no perf-only, no style, no fixes): encoded in the common finder preamble (Task 4 step 1) and the absence of any task that modifies `modern_di/`.
- Four dimensions: each has a heuristics constant (Task 4 step 2) and dedicated finder.
- Method (discover → find → verify → synth, pipelined): Task 1 (skeleton), Task 3 (discover), Task 4 (finders, initially parallel), Task 6 (pipeline + verify), Task 7 (synth).
- Finding schema: Task 2 (RAW_FINDING_SCHEMA + post-verify additions in pipeline output).
- Triage rubric: Task 7 synth prompt.
- Deliverables (spec, plan, report at exact paths): all three referenced.
- Risks: covered by the refute-by-default verifier instruction (Tasks 5 and 6) and the read-real-code lens.

**Placeholder scan:** no "TBD" / "TODO" / "add appropriate" / "similar to Task N". Each prompt is written out in full. Each schema is given in full. Each commit message is specific.

**Type/name consistency:** schema property names (`file`, `line`, `severity`, `confidence_finder`, `reclassification`, `verifier_votes`, `survives`) are identical across Tasks 2, 5, 6, 7. Phase names (`Discover`, `Find`, `Verify`, `Synthesize`) match the meta block in Task 1 throughout. Lens names (`reproduce`, `read-real-code`, `spec-vs-behavior`) match between schema, verifier prompt builder, and pipeline. `general-purpose` agentType used consistently for the synth agent.

**Execution cost note:** the full run in Task 7 step 3 is the expensive step (50-260 agents). All earlier tasks are cheap (single-digit agent calls) by design — schemas and prompts are added incrementally, verified by parse-only or shallow-scope runs, so the engineer is not paying for a full audit on every iteration.
