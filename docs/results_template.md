# Stage 7 results

## Parameters

| W (ticks) | main alpha | deadline at main alpha | stages | work | bytes | hogs (CPUS=1 / CPUS=3) | commit hashes |
|---|---|---|---|---|---|---|---|
| 48.2 | 1.5 | 72 | 4 | 100 | 2048 | 3 / 5 | cb7a589b |

## Miss rate at the main alpha

| policy | cpus | alpha | deadline | n | misses | miss rate | 95% CI | mean finish | median finish | dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| rr | 1 | 1.5 | 72 | 20 | 20 | 1.00 | [1.00, 1.00] | 87.0 | 88.0 | 0 |
| edf | 1 | 1.5 | 72 | 20 | 20 | 1.00 | [1.00, 1.00] | 87.4 | 86.5 | 0 |
| edf_donate | 1 | 1.5 | 72 | 20 | 0 | 0.00 | [0.00, 0.00] | 49.1 | 48.0 | 0 |
| rr | 3 | 1.5 | 72 | 20 | 0 | 0.00 | [0.00, 0.00] | 53.6 | 52.0 | 0 |
| edf | 3 | 1.5 | 72 | 20 | 0 | 0.00 | [0.00, 0.00] | 60.2 | 59.0 | 0 |
| edf_donate | 3 | 1.5 | 72 | 20 | 0 | 0.00 | [0.00, 0.00] | 57.4 | 58.0 | 0 |

## Miss rate vs alpha (CPUS=1)

| policy | cpus | alpha | deadline | n | misses | miss rate | 95% CI | mean finish | median finish | dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| rr | 1 | 1.2 | 58 | 10 | 10 | 1.00 | [1.00, 1.00] | 88.9 | 89.0 | 0 |
| edf | 1 | 1.2 | 58 | 10 | 10 | 1.00 | [1.00, 1.00] | 88.6 | 88.5 | 0 |
| edf_donate | 1 | 1.2 | 58 | 10 | 0 | 0.00 | [0.00, 0.00] | 47.9 | 48.0 | 0 |
| rr | 1 | 1.5 | 72 | 20 | 20 | 1.00 | [1.00, 1.00] | 87.0 | 88.0 | 0 |
| edf | 1 | 1.5 | 72 | 20 | 20 | 1.00 | [1.00, 1.00] | 87.4 | 86.5 | 0 |
| edf_donate | 1 | 1.5 | 72 | 20 | 0 | 0.00 | [0.00, 0.00] | 49.1 | 48.0 | 0 |
| rr | 1 | 2.0 | 96 | 10 | 0 | 0.00 | [0.00, 0.00] | 89 | 89.0 | 0 |
| edf | 1 | 2.0 | 96 | 10 | 1 | 0.10 | [0.00, 0.30] | 87.8 | 85.5 | 0 |
| edf_donate | 1 | 2.0 | 96 | 10 | 0 | 0.00 | [0.00, 0.00] | 50.3 | 51.0 | 0 |
| rr | 1 | 3.0 | 145 | 10 | 0 | 0.00 | [0.00, 0.00] | 93.1 | 92.0 | 0 |
| edf | 1 | 3.0 | 145 | 10 | 0 | 0.00 | [0.00, 0.00] | 88.6 | 89.5 | 0 |
| edf_donate | 1 | 3.0 | 145 | 10 | 0 | 0.00 | [0.00, 0.00] | 48.4 | 48.5 | 0 |

## Fisher exact test: edf vs edf_donate

| cpus | alpha | edf miss/met | edf_donate miss/met | p (two-sided) | method |
|---|---|---|---|---|---|
| 1 | 1.5 | 20/0 | 0/20 | 1.451e-11 | manual (hypergeometric, two-sided) |
| 3 | 1.5 | 0/20 | 0/20 | 1 | manual (hypergeometric, two-sided) |

Note: n is small (largest n per cell here: 20), so the test has little power; a large p-value does not show the policies are equivalent.

## Data quality

- Non-ok rows dropped: 0
- Rows whose miss column disagrees with finish > deadline: 0
- ok rows without integer finish/deadline (not analysed): 0
- Duplicate (policy, cpus, alpha, run) keys: 0

## Explanation

In the four-stage workload only the final stage carries a deadline. On one CPU with three hogs, rr gives every runnable process an equal turn, and edf has nothing to prefer among the upstream stages and the hogs because none of them has a deadline. The T-57 trace shows the hogs and stages 1 to 3 taking equal turns. The pipeline therefore needs about 87 ticks under both policies, and all 20 runs miss the 72-tick deadline. Under edf_donate the final stage, blocked on its pipe, lends its deadline to the stage that writes into that pipe, and the donation propagates up the chain, so the stages outrank the hogs. In the T-58 trace only pipeline stages run until the workflow completes and the hogs run afterwards. The pipeline finishes in about 48 ticks, essentially the unloaded time W = 48.2, and no run misses (Fisher p = 1.5e-11). The sweep shows the same separation: edf_donate meets every deadline from alpha 1.2, while rr and edf miss every run at alpha 1.2 and 1.5 and meet the deadline from alpha 2.0, apart from one edf run. PLAN's estimate T_RR = (h+1)W = 193 ticks overstates the measured 87 because the stages overlap: while one stage waits on a pipe, the others share the CPU with the hogs, so the pipeline as a whole receives more than 1/(h+1) of it. With three CPUs, nine processes share three processors, every policy finishes inside the deadline (means 53.65 to 60.25), and donation has no measurable effect at this deadline.

## Anomalies

No run failed and no run missed under donation. The rr mean finish at alpha 3.0 (93.1 ticks) is slightly above its value at the other alphas (87.0 to 89.0); rr does not read the deadline, so this is treated as emulator timing noise and no miss count changes. One edf run on CPUS=3 finished exactly at the 72-tick deadline and counts as met, because a miss is finish > deadline. Both Gantt traces filled the 256-entry trace ring, so their earliest events are missing. The archived first batch used a different workload and is not directly comparable.
