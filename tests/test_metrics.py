"""Expected values are worked by hand. Ranked list: A B C D E. Relevant: B (grade 2), D (grade 1).

  hit@3        B is at rank 2                          -> 1
  recall@3     top3 = {A,B,C}, found B of {B,D}        -> 1/2
  precision@3  1 relevant of 3                         -> 1/3
  recall@5     found B and D                           -> 1
  precision@5  2 relevant of 5                         -> 2/5
  RR           first relevant at rank 2                -> 1/2
  DCG@5        2/log2(3) + 1/log2(5) = 1.2619 + 0.4307 = 1.6925
  IDCG@5       2/log2(2) + 1/log2(3) = 2 + 0.6309      = 2.6309
  nDCG@5       1.6925 / 2.6309                         = 0.6433
"""
import pytest

from evals.metrics import dcg_at_k, hit_at_k, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank

RANKED = ["A", "B", "C", "D", "E"]
GRADES = {"B": 2, "D": 1}
RELEVANT = set(GRADES)


def test_hit():
    assert hit_at_k(RANKED, RELEVANT, 1) == 0 and hit_at_k(RANKED, RELEVANT, 3) == 1


def test_recall_and_precision():
    assert recall_at_k(RANKED, RELEVANT, 3) == pytest.approx(0.5)
    assert recall_at_k(RANKED, RELEVANT, 5) == 1
    assert precision_at_k(RANKED, RELEVANT, 3) == pytest.approx(1 / 3)
    assert precision_at_k(RANKED, RELEVANT, 5) == pytest.approx(0.4)


def test_reciprocal_rank():
    assert reciprocal_rank(RANKED, RELEVANT) == pytest.approx(0.5)
    assert reciprocal_rank(["X", "Y"], RELEVANT) == 0


def test_ndcg():
    assert dcg_at_k(RANKED, GRADES, 5) == pytest.approx(1.6925, abs=1e-3)
    assert ndcg_at_k(RANKED, GRADES, 5) == pytest.approx(0.6433, abs=1e-3)
    assert ndcg_at_k(["B", "D"], GRADES, 5) == pytest.approx(1.0)  # ideal order scores 1


def test_ndcg_rewards_putting_the_better_item_first():
    assert ndcg_at_k(["B", "D"], GRADES, 2) > ndcg_at_k(["D", "B"], GRADES, 2)
