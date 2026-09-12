# No DEBUG resolution tracing

**Decision:** no `logging.getLogger("modern_di")` narrating resolution, neither runtime-guarded
nor behind a compile-time gate.

**Why:** the guard is not a boolean. `logger.isEnabledFor(DEBUG)` measures ~19 ns net, about 10x a
module-global bool, and a cached factory needs two of them. Patched into the resolvers and measured
with tracing off, the cost every user pays for a feature they never enable:

| Scenario | delta |
|---|---|
| G2 cached warm hit | +37% |
| G16 by-type resolve | +31% |
| G4 wide, 10 siblings | +28% |
| G3 deep chain | +15% |

A compile-time gate would be free (resolvers are memoized and can be dropped), but turns the
feature into a second public activation API plus a compile mode, which is the conservative feature
set saying no. Diagnostics stay the job of the error messages, which carry the resolution chain at
zero hot-path cost.
