# 0005: Embedding provider

Status: accepted (2026-10-10)

## Context
Default plan: Amazon Titan Text Embeddings V2 on Bedrock (AWS-credit-covered). In Service Quotas the account's
**applied** on-demand quotas for Titan V2 in us-east-2 were 0 requests/minute and 0 tokens/minute (AWS default
6,000 and 300,000), not adjustable, and the account is limited to us-east-2. Every call, including a single call
after waiting, returned ThrottlingException.

## Options
| Option | Pros | Cons |
|---|---|---|
| Upgrade AWS plan / Support case | keeps Bedrock | unknown outcome, changes billing exposure |
| Other region | likely works | not permitted for this account |
| **Voyage `voyage-4` (API)** | 200M free tokens, 1024-dim default, query/document input types, 32K context | external provider, not AWS |
| Gemini embeddings | strong public scores | free-tier limits not confirmed |
| Open-weight model | no per-token fee | needs GPU, excluded (no local models) |

## Decision
Voyage `voyage-4` at 1024 dimensions behind `common/embeddings.py` (`embed_documents`, `embed_query`).
`EMBED_PROVIDER=bedrock` keeps the Titan path available.

## Consequences
`rag.chunks` is keyed by content hash, model and dimensions, so switching providers means a re-index and a new
retrieval baseline. A Titan vs Voyage vs Cohere comparison remains a future experiment (E10 in EXPERIMENTS.md).
