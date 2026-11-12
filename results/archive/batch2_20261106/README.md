> **Historical.** Batch of 2026-11-06 (210 runs, commit `cb7a589b`). The final results are in [`results/README.md`](../../README.md).

Superseded by docs/results_template.md (PLAN-conformant batch); this file describes the archived first batch.

# Stage 7 results

## Parameters

| W (ticks) | main alpha | deadline at main alpha | stages | work | bytes | hogs (CPUS=1 / CPUS=3) | commit hashes |
|---|---|---|---|---|---|---|---|
| 24.4 | 1.5 | 37 | 4 | 100 | 1024 | 3 / 5 | 043a34b5 |

## Miss rate at the main alpha

| policy | cpus | alpha | deadline | n | misses | miss rate | 95% CI | mean finish | median finish | dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| rr | 1 | 1.5 | 37 | 20 | 20 | 1.00 | [1.00, 1.00] | 49.1 | 47.5 | 0 |
| edf | 1 | 1.5 | 37 | 20 | 20 | 1.00 | [1.00, 1.00] | 55 | 53.0 | 0 |
| edf_donate | 1 | 1.5 | 37 | 20 | 1 | 0.05 | [0.00, 0.15] | 35.1 | 31.0 | 0 |
| rr | 3 | 1.5 | 37 | 20 | 0 | 0.00 | [0.00, 0.00] | 30 | 29.5 | 0 |
| edf | 3 | 1.5 | 37 | 20 | 7 | 0.35 | [0.15, 0.55] | 37 | 36.5 | 0 |
| edf_donate | 3 | 1.5 | 37 | 20 | 1 | 0.05 | [0.00, 0.15] | 34.5 | 34.5 | 0 |

## Miss rate vs alpha (CPUS=1)

| policy | cpus | alpha | deadline | n | misses | miss rate | 95% CI | mean finish | median finish | dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| rr | 1 | 1.0 | 24 | 10 | 10 | 1.00 | [1.00, 1.00] | 47.8 | 47.5 | 0 |
| edf | 1 | 1.0 | 24 | 10 | 10 | 1.00 | [1.00, 1.00] | 47.8 | 49.0 | 0 |
| edf_donate | 1 | 1.0 | 24 | 10 | 10 | 1.00 | [1.00, 1.00] | 25.6 | 25.5 | 0 |
| rr | 1 | 1.25 | 31 | 10 | 10 | 1.00 | [1.00, 1.00] | 47.1 | 45.0 | 0 |
| edf | 1 | 1.25 | 31 | 10 | 10 | 1.00 | [1.00, 1.00] | 46.4 | 45.5 | 0 |
| edf_donate | 1 | 1.25 | 31 | 10 | 0 | 0.00 | [0.00, 0.00] | 25.6 | 26.0 | 0 |
| rr | 1 | 1.5 | 37 | 20 | 20 | 1.00 | [1.00, 1.00] | 49.1 | 47.5 | 0 |
| edf | 1 | 1.5 | 37 | 20 | 20 | 1.00 | [1.00, 1.00] | 55 | 53.0 | 0 |
| edf_donate | 1 | 1.5 | 37 | 20 | 1 | 0.05 | [0.00, 0.15] | 35.1 | 31.0 | 0 |
| rr | 1 | 2.0 | 49 | 10 | 4 | 0.40 | [0.10, 0.70] | 49 | 49.0 | 0 |
| edf | 1 | 2.0 | 49 | 10 | 1 | 0.10 | [0.00, 0.30] | 46.2 | 45.5 | 0 |
| edf_donate | 1 | 2.0 | 49 | 10 | 0 | 0.00 | [0.00, 0.00] | 26 | 26.0 | 0 |
| rr | 1 | 2.5 | 61 | 10 | 1 | 0.10 | [0.00, 0.30] | 53.3 | 52.5 | 0 |
| edf | 1 | 2.5 | 61 | 10 | 1 | 0.10 | [0.00, 0.30] | 55 | 53.5 | 0 |
| edf_donate | 1 | 2.5 | 61 | 10 | 0 | 0.00 | [0.00, 0.00] | 30.7 | 30.5 | 0 |
| rr | 1 | 3.0 | 73 | 10 | 0 | 0.00 | [0.00, 0.00] | 59.7 | 58.5 | 0 |
| edf | 1 | 3.0 | 73 | 10 | 4 | 0.40 | [0.10, 0.70] | 70.7 | 71.5 | 0 |
| edf_donate | 1 | 3.0 | 73 | 10 | 0 | 0.00 | [0.00, 0.00] | 29.9 | 30.0 | 0 |

## Fisher exact test: edf vs edf_donate

| cpus | alpha | edf miss/met | edf_donate miss/met | p (two-sided) | method |
|---|---|---|---|---|---|
| 1 | 1.5 | 20/0 | 1/19 | 3.047e-10 | manual (hypergeometric, two-sided) |
| 3 | 1.5 | 7/13 | 1/19 | 0.0436 | manual (hypergeometric, two-sided) |

Note: n is small (largest n per cell here: 20), so the test has little power; a large p-value does not show the policies are equivalent.

## Data quality

- Non-success rows dropped: 0
- Rows whose miss column disagrees with finish > deadline: 0
- Success rows without integer finish/deadline (not analysed): 0
- Duplicate (policy, cpus, alpha, run) keys: 0

## Explanation

In the four-stage workload only the final stage carries a deadline; the three upstream stages have none. On one CPU with three hogs, rr and edf therefore give the upstream stages no advantage over the hogs. The T-57 trace shows the hogs and stages 1 to 3 taking equal turns, so the pipeline as a whole receives roughly half of the processor, and all 20 runs under each policy finished after the 37-tick deadline (means 49.1 and 55 ticks). Under edf_donate the final stage, while blocked reading its pipe, donates its deadline to the stage that writes into that pipe, and the donation propagates up the chain. The upstream stages then outrank the hogs. The T-58 trace shows only pipeline stages running, each preceded by a DONATE marker, until the workflow completes, and 19 of 20 runs met the deadline (median 31 ticks). The Fisher exact test gives p = 3.0e-10 for edf against edf_donate.

The alpha sweep shows the same mechanism as the deadline is relaxed. At alpha 1.0 the deadline (24 ticks) is below even the unloaded runtime of 24.4 ticks, and every policy misses. From alpha 1.25 edf_donate meets every deadline, because its finish time stays close to the unloaded runtime. rr and edf only begin to meet deadlines at about alpha 2.0, roughly twice the unloaded runtime, which is close to the time they need when sharing the CPU with the hogs.

On three CPUs, nine processes share three processors, so each upstream stage receives CPU time without needing a donated deadline, and the advantage of donation largely disappears. Here rr met every deadline, edf missed 7 of 20 runs and edf_donate missed 1 of 20 (p = 0.044). This partly contradicts prediction 2, which expected the three policies to finish close together. Why edf performs worse than rr is not established by this data. One untested hypothesis is that edf's least-recently-run tie-break among processes without a deadline disadvantages pipeline stages, which block and resume often, relative to hogs, which never block.

All misses are computed on the host as finish > deadline. The kernel's own counter is cumulative per boot and starts its deadline clock later than the workload does, so it is recorded but not used (L-31).

## Anomalies

One edf_donate run at alpha 1.5 on CPUS=1 (run 4) finished at 99 ticks, the only miss in that cell. Its log shows a normal boot and a single RESULT line. A separate traced edf_donate run that missed (finish 58, `gantt-T58-miss.png`) shows donation stopping at the deadline-miss event, after which the hogs run between the stages. The likely explanation, not traced for run 4, is that once the kernel marks a miss the final stage's effective deadline becomes NO_DEADLINE, donation ends, and the pipeline falls back to sharing the CPU with the hogs, which makes a late run very late (L-27).

The single edf_donate miss on CPUS=3 (run 18) finished at 38 ticks against a deadline of 37. The kernel reported no miss for this run because its deadline clock starts later than the host's, which illustrates why the host rule is used.

At alpha 3.0, edf missed 4 of 10 runs with a mean finish of 70.7 ticks, although it missed only 1 of 10 at alpha 2.0 and 2.5. An order check that ran alpha 3.0 before alpha 1.0 gave edf finish times of 45 to 46 ticks at alpha 3.0, the same as at alpha 1.0. The effect is therefore attributed to drift late in the sweep, which ran the alpha values in increasing order, not to the deadline. rr finish times also rose at alpha 2.5 and 3.0 (means 53.3 and 59.7) even though rr never uses the deadline when scheduling; this remains unexplained and is treated as emulator timing noise (L-26).

The trace ring holds 256 events per CPU, and the edf_donate traces wrapped, so their first events are lost. The T-58 figure uses the second of two trace dumps from one run, extracted as the last 256 trace lines; the original log is kept unchanged (L-30). No data was dropped or altered.