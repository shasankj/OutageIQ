# Metrics cheat sheet

The full treatment, with formulas, worked examples, how to read each number and which knob to turn, is in
**`docs/02-EVALUATION-TOKENOMICS-AND-MODELS.md`, section 6**.

| Metric | Where used here | Section |
|---|---|---|
| Hit@k, Recall@k, Precision@k, F1@k, MRR, AP/MAP, R-precision | `evals/retrieval_eval.py`, `evals/metrics.py` | 6.1 |
| DCG, IDCG, nDCG@k (graded) | same | 6.2 |
| Context precision/recall, faithfulness, answer relevancy | faithfulness is deterministic in `agent/facts.py` | 6.4 |
| Valid-SQL rate, execution accuracy (strict/lenient), first-try, repair success | `evals/agent_eval.py`, `evals/compare.py` | 6.5 |
| Precision/recall/F1, confusion matrix, macro/micro, ROC/PR (router, refusals) | planned for the router eval | 6.8 |
| pass@k, pass^k | planned (repeat runs) | 6.9 |
| Percent agreement, Cohen's kappa | planned (judge calibration) | 6.10 |
| Confidence intervals, paired tests, bootstrap | planned for experiment reports | 6.11 |
| Latency p50/p95, tokens, cost, cache hit rate | `evals/agent_eval.py`, traces | 6.12 |
