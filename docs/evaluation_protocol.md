# Evaluation protocol

Historical certified project protocol: official tau2-bench v1.0.1 Retail test,
40 tasks × 1 trial, concurrency 1, temperature 0, simulation seed 300,
Kefu decision limit 15, official transition limit 30. Agent, user simulator and
NL scorer used the compatible `openai/deepseek-v4-flash` configuration.
Provider deterministic seed support was not established.

Task Success = count(official overall reward == 1) / 40, result 32/40 = 80%.
Do not reinterpret reference actions as an exact required tool sequence.
The official test split was inspected in prior diagnostic analysis; it is not a
pristine unseen held-out test. This is not an official leaderboard ranking.

`results/protocol.yaml` is historical protocol evidence, not permission to rerun or
overwrite the frozen baseline. No benchmark execution is triggered by the public
CLI: it validates packaged evidence offline. Full trajectories remain internal.

Future development belongs on train/synthetic data with separate protocol/version,
multiple trials and ablation. None has been implemented by this release preparation.
