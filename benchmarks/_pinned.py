"""Fixed round/iteration pairs for the sub-2-microsecond guard scenarios.

pytest-benchmark calibrates each scenario, and the short ones land on ``iterations=1``. Their
medians are then quantized to one ``time.perf_counter`` tick — ~41 ns on an Apple M4, which is
23% of the smallest scenario's value. A 10-30 ns move is unreadable at that resolution, and the
optimizations these scenarios exist to protect are now worth 20-33% each.

Pinning puts every round above ~80 us, so the timer pair is under 0.1% of the measured value.
Scenarios at or above ~10 us keep calibration — the tick is already under 0.5% of those — as do
the ones needing per-round setup, which cannot take ``iterations`` above 1 without measuring a
warm repeat instead of the cold case they exist for.

The reported statistic changes with pinning: a median of per-round *means* rather than of single
calls. That is the same statistic the comparative tier reports, and it is why the stored CI
baseline is reset when these land.
"""

#: Rounds per scenario, matching the comparative tier.
ROUNDS = 200

#: Iterations, chosen so one round spans ~80-150 us at each scenario's measured per-call cost.
ITER_UNDER_300NS = 500
ITER_UNDER_1US = 200
ITER_UNDER_2US = 100
