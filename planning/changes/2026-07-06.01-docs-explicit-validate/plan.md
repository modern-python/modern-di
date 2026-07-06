# docs-explicit-validate — implementation plan

**Goal:** No docs/README sample constructs a bare root `Container(...)`.
**Spec:** [`design.md`](./design.md)
**Branch:** `docs/explicit-validate-samples`
**Commit strategy:** single commit.

### Task 1: The sweep

**Files:** every `docs/**/*.md` with a hit, plus `README.md`.

- [ ] **Step 1: Enumerate sites**

  `grep -rn "Container(" docs/ README.md | grep -v "build_child_container" | grep -v "validate="`
  Root constructions only. Record the list.

- [ ] **Step 2: Apply the design's site rules** (validate=True default; True
  for validation-error demos; False for runtime-failure demos; to-3.x "before"
  snippets stay bare).

- [ ] **Step 3: Spot-run one edited sample per docs section** as a throwaway
  script under the session scratchpad; record outputs.

- [ ] **Step 4: Gates** — `just docs-build`, `just lint-ci`, re-run the
  Step 1 grep (only rule-4 sites may remain).

- [ ] **Step 5: Commit** — `docs: pass explicit validate= in all root Container samples`
