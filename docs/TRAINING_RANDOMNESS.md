# Training randomness

## Original v028 limitation

The original basin60 and targeted60 models were trained with MLIP random initialization but without an explicitly recorded RNG seed. Their files and predictions are immutable historical artifacts, so their published numerical metrics remain exactly reproducible from saved outputs, but the training process itself was not deterministic.

## Fixed-seed robustness audit

A post-publication audit froze five paired seeds before any new training:

| index | seed_u64 |
|---:|---:|
| 0 | 4172185641970229070 |
| 1 | 10780126852447763956 |
| 2 | 16937122512019790775 |
| 3 | 12250469658613881511 |
| 4 | 18149779474148714524 |

For each seed, both branches were trained from the exact v028 dataset and untrained template using max-iter 2000, energy weight 1, force weight 0.01 and stress weight 0. There were no retries, warm starts, model selection or new DFT calculations.

## Result

The audit is classified SEED_SENSITIVE.

| seed | basin barrier error, meV | targeted barrier error, meV | basin transition-force RMSE | targeted transition-force RMSE |
|---:|---:|---:|---:|---:|
| 0 | 27.5500 | 6.6306 | 0.08128 | 0.05702 |
| 1 | 31.7132 | 1.3687 | 0.09372 | 0.08736 |
| 2 | 23.0778 | 3.2495 | 0.21292 | 0.11168 |
| 3 | 7.1317 | 9.2945 | 0.04588 | 0.07421 |
| 4 | 11.2393 | 8.2888 | 0.11795 | 0.12675 |

Targeted is better on both primary metrics in 3/5 paired seeds. Seed 3 reverses both metrics. Seed 4 favors targeted on barrier error but basin on transition-force RMSE.

Basin is better on basin12 force RMSE in all 5 paired seeds.

The original v030r numbers are not replaced by these runs. They remain the result for the original locked model pair; the robustness audit changes the strength of the interpretation.
