"""Embedding facade: one interface, two providers (EMBED_PROVIDER = voyage | bedrock).

Everything else (indexer, retriever, evals) imports only this module, so swapping the
embedding model is a config change plus a re-index. Documents and queries are embedded through
different functions because retrieval models can embed them differently (Voyage's input_type).
Dimensions are fixed at 1024 to match rag.chunks.embedding vector(1024).
"""
import json
import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DIMS = 1024
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-4")
VOYAGE_BATCH = int(os.environ.get("VOYAGE_BATCH", "8"))  # texts per request; small in case of low TPM limits
VOYAGE_RETRIES = 8
BEDROCK_MODEL = "amazon.titan-embed-text-v2:0"
PRICE_PER_MILLION_TOKENS = {VOYAGE_MODEL: 0.06, BEDROCK_MODEL: 0.02}  # USD list price; Voyage has 200M free tokens


# --- Voyage pacing -----------------------------------------------------------------------------
# Accounts without a payment method have a very low request limit. All threads share one pacer so
# they queue behind a cooldown instead of retrying in a storm. After the first rate-limit error we
# space calls ~21 s apart (a 3 requests/minute limit) unless VOYAGE_MIN_INTERVAL_S says otherwise.
_pace_lock = threading.Lock()
_next_allowed = 0.0
_interval = float(os.environ.get("VOYAGE_MIN_INTERVAL_S", "0"))
_interval_pinned = "VOYAGE_MIN_INTERVAL_S" in os.environ


def _wait_turn():
    global _next_allowed
    with _pace_lock:
        now = time.monotonic()
        wait = max(0.0, _next_allowed - now)
        _next_allowed = max(now, _next_allowed) + _interval
    if wait:
        time.sleep(wait)


def _rate_limited(cooldown: float):
    global _next_allowed, _interval
    with _pace_lock:
        if not _interval_pinned:
            _interval = max(_interval, 21.0)
        _next_allowed = max(_next_allowed, time.monotonic() + cooldown)


# --- persistent query-embedding cache (questions repeat: evals, retries, demos) ------------------
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "query_embedding_cache.jsonl"
_cache: dict[str, list[float]] | None = None
_cache_lock = threading.Lock()


def _cache_get(key: str):
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = {}
            if CACHE_PATH.exists():
                for line in CACHE_PATH.read_text().splitlines():
                    rec = json.loads(line)
                    _cache[rec["k"]] = rec["v"]
        return _cache.get(key)


def _cache_put(key: str, vector: list[float]):
    with _cache_lock:
        _cache[key] = vector
        CACHE_PATH.parent.mkdir(exist_ok=True)
        with CACHE_PATH.open("a") as f:
            f.write(json.dumps({"k": key, "v": vector}) + "\n")


@dataclass
class Embeddings:
    vectors: list[list[float]]
    tokens: int


def provider() -> str:
    return os.environ.get("EMBED_PROVIDER", "voyage")


def model_id() -> str:
    return VOYAGE_MODEL if provider() == "voyage" else BEDROCK_MODEL


def price_per_million() -> float:
    return PRICE_PER_MILLION_TOKENS[model_id()]


def _voyage(texts: list[str], input_type: str) -> Embeddings:
    import voyageai

    if not os.environ.get("VOYAGE_API_KEY"):
        raise RuntimeError("Missing VOYAGE_API_KEY in .env")
    client = voyageai.Client(max_retries=0, timeout=30)  # we own the retry policy; never wait forever
    retryable = (voyageai.error.RateLimitError, voyageai.error.ServiceUnavailableError,
                 voyageai.error.ServerError, voyageai.error.APIConnectionError)
    vectors, tokens = [], 0
    for i in range(0, len(texts), VOYAGE_BATCH):
        batch = texts[i:i + VOYAGE_BATCH]
        for attempt in range(VOYAGE_RETRIES + 1):
            _wait_turn()
            try:
                r = client.embed(batch, model=VOYAGE_MODEL, input_type=input_type, output_dimension=DIMS)
                vectors.extend(r.embeddings)
                tokens += r.total_tokens
                break
            except retryable as e:
                if attempt == VOYAGE_RETRIES:
                    raise
                wait = min(60, 3 * 2 ** attempt) * random.uniform(0.5, 1.0)
                print(f"[voyage] {type(e).__name__}: retry {attempt + 1}/{VOYAGE_RETRIES} in {wait:.0f}s",
                      file=sys.stderr, flush=True)
                _rate_limited(wait)
    return Embeddings(vectors, tokens)


def _bedrock(texts: list[str]) -> Embeddings:
    from common.embed_bedrock import embed

    results = [embed(t, dimensions=DIMS) for t in texts]
    return Embeddings([r.vector for r in results], sum(r.input_tokens for r in results))


def embed_documents(texts: list[str]) -> Embeddings:
    return _voyage(texts, "document") if provider() == "voyage" else _bedrock(texts)


def embed_query(text: str) -> Embeddings:
    use_cache = os.environ.get("EMBED_CACHE", "1") != "0"
    key = f"{model_id()}|{DIMS}|{text}"
    if use_cache and (hit := _cache_get(key)) is not None:
        return Embeddings([hit], 0)  # cached: no API call, no tokens
    result = _voyage([text], "query") if provider() == "voyage" else _bedrock([text])
    if use_cache:
        _cache_put(key, result.vectors[0])
    return result
