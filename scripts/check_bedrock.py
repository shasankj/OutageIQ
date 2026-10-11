"""First Bedrock call: proves auth, region, model access, normalization and IAM scope.

Run: python -m scripts.check_bedrock      Cost: a few dozen tokens (a fraction of a cent).
"""
import math

from botocore.exceptions import ClientError

from common.embed_bedrock import embed


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (norm(a) * norm(b))


def main() -> int:
    ok = True
    try:
        e = embed("What are the details of outage 1234?")
        print(f"[PASS] embedded: {len(e.vector)} dims, {e.input_tokens} input tokens")
        print(f"       first 5 values: {[round(x, 4) for x in e.vector[:5]]}")
        print(f"[{'PASS' if abs(norm(e.vector) - 1) < 1e-3 else 'FAIL'}] normalize=True gives length {norm(e.vector):.4f} (expect 1.0)")
        raw = embed("What are the details of outage 1234?", normalize=False)
        print(f"[INFO] normalize=False gives length {norm(raw.vector):.4f}")
        small = embed("What are the details of outage 1234?", dimensions=256)
        print(f"[PASS] 256-dim variant: {len(small.vector)} dims")
    except ClientError as err:
        print(f"[FAIL] {err.response['Error']['Code']}: {err.response['Error']['Message']}")
        return 1

    # Semantic similarity sanity check: related text should score higher than unrelated text.
    q = embed("Which outages are still open?").vector
    related = embed("To find open outages use outages.is_open, which is true when end_time IS NULL.").vector
    unrelated = embed("Ticket numbers look like INC-55821 and are unique.").vector
    unrelated2 = embed("The quick brown fox jumps over the lazy dog.").vector
    s1, s2, s3 = cosine(q, related), cosine(q, unrelated), cosine(q, unrelated2)
    print(f"[INFO] cosine(question, open-outage doc) = {s1:.3f}")
    print(f"[INFO] cosine(question, ticket-number doc) = {s2:.3f}")
    print(f"[INFO] cosine(question, fox sentence)     = {s3:.3f}")
    ok &= s1 > max(s2, s3)
    print(f"[{'PASS' if s1 > max(s2, s3) else 'FAIL'}] the relevant doc ranks first")

    # IAM scope: our policy only allows Titan V2, so another model must be denied.
    try:
        embed("scope test", model_id="amazon.titan-embed-text-v1", dimensions=1024)
        print("[FAIL] another model was callable: the IAM policy is broader than intended")
        ok = False
    except (ClientError, ValueError) as err:
        code = err.response["Error"]["Code"] if isinstance(err, ClientError) else "ValueError"
        status = "PASS" if code == "AccessDeniedException" else "INFO"
        print(f"[{status}] other model call rejected: {code}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
