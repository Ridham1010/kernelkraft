# Stage 7 predictions

Committed 2026-11-04, before the full measurement batch.
Kernel commit: 305a13f (stage7-fix: NO_DEADLINE ordering in dl_before).

## Disclosure
These predictions are informed by small pilots (n = 2 per cell) run on
2026-11-04: logs/stage7-pilot (before the fix), logs/stage7-fix and
logs/stage7-pilot-postfix (after). The deadline rule and main alpha were
chosen from those pilots. The full batch is a fresh measurement on the
same commit; no pilot row is counted in the results.

## Setup
- Workload: wfgen 4 100 1024 <deadline> <hogs>; hogs = 3 (CPUS=1), 5 (CPUS=3).
- QEMU 10.1 with -machine pc-i440fx-yakkety (required for >1 CPU, L-24).
- W = 24.4 ticks (CPUS=1, zero hogs, 5 runs, SD 2.41).
- Deadline rule: deadline = round(alpha * W). Main alpha = 1.5 (deadline 37).
- Sweep: alpha = 1.0, 1.25, 1.5, 2.0, 2.5, 3.0 on CPUS=1, 10 runs per cell.
- Miss rule: miss = 1 if finish > deadline (host-computed, same for all
  policies). The kernel's counter is kept separately as miss_kernel because
  it is cumulative per boot and its deadline starts when the final stage
  registers, not at workflow launch.

## Predictions
1. CPUS=1, alpha 1.5, 20 runs per policy: rr and edf miss in at least
   18/20 runs each; edf_donate misses in at most 2/20. Reason: only the
   final stage has a deadline, so without donation stages 1 to 3 compete
   equally with 3 hogs on one CPU; donation passes the final stage's
   deadline upstream so the whole pipeline runs ahead of the hogs.
2. CPUS=3, alpha 1.5: the effect is much weaker. All three policies finish
   near the deadline and the edf vs edf_donate difference will not be
   statistically significant. Reason: 9 processes on 3 CPUs leaves enough
   capacity that upstream stages make progress without donation.
3. Alpha sweep (CPUS=1): all policies miss at alpha 1.0. edf_donate drops to
   near-zero misses by alpha 1.5; rr and edf stay high until about alpha 2.0
   and reach near-zero by alpha 2.5.
4. Gantt, edf: stages 1 to 3 interleave with the hogs while the final stage
   sits blocked on its pipe.
5. Gantt, edf_donate: DONATE events appear just before stages 1 to 3 run,
   and they run ahead of the hogs.
6. Adaptive agent with a tight deadline: the rr pilot misses, the planner
   switches to edf_donate, and the rerun meets the deadline.
## Revision 2 (2026-11-06), committed before the second batch

The first batch was run with a workload that did not match PLAN.md (bytes 1024
below 4 x PIPESIZE, wfgen miss taken from the cumulative kernel counter, clock
started before the hogs, a different alpha set). It is archived in
results/archive/batch1_20261104/. These predictions are for the PLAN-conformant batch.

Disclosure: informed by the archived first batch and by a pilot on 2026-11-06
(results/archive/batch2_20261106/pilot_rev.csv, logs/stage7rev-pilot/, 2 runs per cell at alpha 1.5).
No pilot row is counted in the results.

Setup: wfgen 4 100 2048 <deadline> <hogs>; hogs 3 (CPUS=1), 5 (CPUS=3);
machine flag -machine pc-i440fx-yakkety. W = 48.2 ticks (CPUS=1, zero hogs,
5 runs, SD 2.59, logs/stage7rev-calibration/). deadline = round(alpha * W),
half-up: alpha 1.2, 1.5, 2.0, 3.0 give 58, 72, 96, 145. Main alpha 1.5.
Miss = finish > deadline, now computed by wfgen itself.

1. CPUS=1, alpha 1.5, 20 runs: rr and edf miss in at least 18/20 each;
   edf_donate misses in at most 2/20.
2. CPUS=3, alpha 1.5: all three policies miss in at most 2/20, and the
   edf vs edf_donate difference is not significant. Reason: 9 processes on
   3 CPUs give the upstream stages enough CPU without donation.
3. Sweep (CPUS=1, 10 runs per cell): edf_donate misses at most 1/10 at every
   alpha from 1.2; rr and edf miss in most runs at 1.2 and 1.5, in some runs
   at 2.0, and in none at 3.0.
4. Gantt, edf: stages 1 to 3 share the CPU with the hogs while the final
   stage waits on its pipe.
5. Gantt, edf_donate: DONATE events appear just before stages 1 to 3 run,
   and the hogs run only after the pipeline finishes.
6. Adaptive agent at alpha 1.5: the rr pilot misses, the planner switches to
   edf_donate, and the rerun meets the deadline.
