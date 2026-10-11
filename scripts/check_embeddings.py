"""First embedding call through the facade. Run: python -m scripts.check_embeddings"""
import math

from common.embeddings import DIMS, embed_documents, embed_query, model_id, provider


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (norm(a) * norm(b))


def main() -> int:
    print(f"provider={provider()} model={model_id()}")
    q = embed_query("Which outages are still open?")
    docs = embed_documents([
        "To find open outages use outages.is_open, which is true when end_time IS NULL.",
        "Ticket numbers look like INC-55821 and are unique.",
        "The quick brown fox jumps over the lazy dog.",
    ])
    ok = len(q.vectors[0]) == DIMS
    print(f"[{'PASS' if ok else 'FAIL'}] dimensions = {len(q.vectors[0])} (expect {DIMS})")
    n = norm(q.vectors[0])
    print(f"[{'PASS' if abs(n - 1) < 1e-3 else 'INFO'}] vector length = {n:.4f} (1.0 means normalized)")
    scores = [cosine(q.vectors[0], d) for d in docs.vectors]
    for label, s in zip(["open-outage doc", "ticket-number doc", "fox sentence"], scores):
        print(f"[INFO] cosine(question, {label:<17}) = {s:.3f}")
    ranked = scores[0] > max(scores[1:])
    print(f"[{'PASS' if ranked else 'FAIL'}] the relevant doc ranks first")
    same = embed_documents(["Which outages are still open?"]).vectors[0]
    print(f"[INFO] same text as query vs as document: cosine = {cosine(q.vectors[0], same):.3f} "
          f"(below 1.0 means the model embeds the two roles differently)")
    print(f"[INFO] tokens used: {q.tokens + docs.tokens}")
    return 0 if ok and ranked else 1


if __name__ == "__main__":
    raise SystemExit(main())
