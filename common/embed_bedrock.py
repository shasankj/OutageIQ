"""Amazon Titan Text Embeddings V2 via Bedrock (docs: model-parameters-titan-embed-text).
CURRENTLY BLOCKED: this account has an applied on-demand quota of 0 in us-east-2 (see PROGRESS.md).

Auth: boto3's default chain (AWS_PROFILE / ~/.aws), never keys in code.
Bedrock throttles embeddings by requests per minute, so we retry with exponential backoff.
Phase 2a adds a content-hash cache and batching on top of this.
"""
import json
import os
import random
import time
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

MODEL_ID = "amazon.titan-embed-text-v2:0"
ALLOWED_DIMENSIONS = (256, 512, 1024)
MAX_CHARS = 50_000  # also capped at 8,192 tokens by the service
_RETRYABLE = {"ThrottlingException", "ModelTimeoutException", "ServiceUnavailableException",
              "InternalServerException"}

_client = None


@dataclass
class Embedding:
    vector: list[float]
    input_tokens: int


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-2"))
    return _client


def embed(text: str, dimensions: int = 1024, normalize: bool = True, max_retries: int = 5,
          model_id: str = MODEL_ID) -> Embedding:
    if not text.strip():
        raise ValueError("Titan requires a non-empty string")
    if len(text) > MAX_CHARS:
        raise ValueError(f"text is {len(text)} chars; the limit is {MAX_CHARS}")
    if dimensions not in ALLOWED_DIMENSIONS:
        raise ValueError(f"dimensions must be one of {ALLOWED_DIMENSIONS}")
    body = json.dumps({"inputText": text, "dimensions": dimensions, "normalize": normalize})

    for attempt in range(max_retries + 1):
        try:
            response = _bedrock().invoke_model(
                modelId=model_id, body=body, accept="application/json", contentType="application/json")
            payload = json.loads(response["body"].read())
            return Embedding(payload["embedding"], payload["inputTextTokenCount"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in _RETRYABLE or attempt == max_retries:
                raise
            time.sleep(min(20, 2 ** attempt) * random.uniform(0.5, 1.0))  # backoff with jitter
    raise AssertionError("unreachable")
