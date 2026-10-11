"""Ranking metrics from scratch (no libraries). `ranked` is a list of ids, best first.

hit_at_k      did ANY relevant item appear in the top k?                       (0 or 1)
recall_at_k   what fraction of the relevant items appear in the top k?
precision_at_k what fraction of the top k are relevant?
reciprocal_rank 1 / rank of the first relevant item (0 if none); mean over queries = MRR
ndcg_at_k     graded relevance, discounted by log2(rank + 1), divided by the ideal ordering
"""
import math


def hit_at_k(ranked, relevant, k):
    return 1.0 if any(r in relevant for r in ranked[:k]) else 0.0


def recall_at_k(ranked, relevant, k):
    return len(set(ranked[:k]) & set(relevant)) / len(relevant) if relevant else 0.0


def precision_at_k(ranked, relevant, k):
    return sum(1 for r in ranked[:k] if r in relevant) / k


def reciprocal_rank(ranked, relevant):
    for i, r in enumerate(ranked, 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def dcg_at_k(ranked, grades, k):
    return sum(grades.get(r, 0) / math.log2(i + 1) for i, r in enumerate(ranked[:k], 1))


def ndcg_at_k(ranked, grades, k):
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg_at_k(ranked, grades, k) / idcg if idcg else 0.0
