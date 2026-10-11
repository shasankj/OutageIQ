# Tokenomics, models, testing and metrics

> **Provenance legend.** *Measured* = produced by a run in this repository (indexing output, the retrieval
> baseline, the live traces in `data/traces/`). *List price* = a vendor's published price, not a measurement.
> *Estimate* = arithmetic on the above. *Snapshot* = an industry fact that changes fast; verify before use.
> **PENDING** = needs an evaluation run that has not happened yet; no number is invented for it.
> Written 2026-10-10. Vendor and benchmark facts were checked against the vendors' docs and recent secondary
> sources on that date; where sources disagreed, this document says so.

**Contents**
1. Tokenomics
2. Embedding models: what they are, the landscape, how to choose
3. LLMs: the landscape and how to choose
4. How we make sure the agent is accurate
5. How we test
6. Metrics: every one, with the math
7. Results so far, and the experiment plan
8. Caching in agentic systems: where, when, how, and what can go wrong
Appendix A. Glossary of every technical term

---

# 1. Tokenomics

## 1.1 What a token is and why it is the unit of cost
An LLM reads and writes **tokens**: pieces of text (roughly 4 characters of English, a short word, or part of
a long one). You pay per token, the context window is measured in tokens, and latency grows with tokens.
Three kinds matter:

| Kind | Meaning | Billed at |
|---|---|---|
| **Input tokens** | Everything you send: system prompt, retrieved reference, question, history, previous attempts | input price |
| **Output tokens** | What the model writes, **including thinking tokens** when adaptive thinking is on | output price (about 5x input) |
| **Cache read / write** | Input served from (or stored in) provider prompt cache | read about 0.1x input; write about 1.25x (provider terms vary) |

Because output costs about five times input and thinking counts as output, *reasoning effort* is a cost knob,
not just a quality knob.

## 1.2 Price tables

### LLMs (Anthropic first-party API, *list price*, per million tokens)
| Model | Input | Output | Context | Note |
|---|---|---|---|---|
| `claude-haiku-5-5` | $0.10 | $0.50 | 1M | Prices are for prompts up to 100K tokens; higher beyond |
| `claude-sonnet-5-5` | $2.00 | $10.00 | 1M | Cache reads $0.20 |
| `claude-opus-5-5` | $4.00 | $20.00 | 1M | Cache reads $0.20 |
| `claude-fable-5-1` | $10.00 | $50.00 | 1M | Most capable; different API behaviour |
| `claude-haiku-4-5` (previous gen) | $1.00 | $5.00 | 200K | Still served |

**Used here:** Sonnet 5.5 for SQL and the judge; Haiku 5.5 for routing and prose.

### Embedding models (*list price*, per million input tokens; no output tokens)
| Model | Price | Source quality |
|---|---|---|
| Voyage `voyage-4` | $0.06 (first 200M tokens free per account) | Voyage pricing page |
| Voyage `voyage-4-lite` / `voyage-4-large` | $0.02 / $0.12 | Voyage pricing page |
| Amazon Titan Text Embeddings V2 | $0.02 | AWS launch post; some trackers list 10x, confirm on the Bedrock pricing page |
| OpenAI `text-embedding-3-large` | about $0.13 (batch about half) | third-party aggregators |
| Cohere Embed v4 | about $0.12 text | third-party aggregators |
| Google `gemini-embedding-001` | $0.15 (batch 50% off) | Google announcement |

## 1.3 Where the tokens go in one OutageIQ question

*Measured*, from the live traces:

| Run | LLM calls | Input tok | Output tok | Cost | Latency |
|---|---|---|---|---|---|
| Details of outage 1234 (1 attempt, judge ok) | 4 | 8,288 | 746 | $0.0189 | 14.9 s |
| "Sites affected today" (2 attempts) | 5 | 13,499 | 828 | $0.0325 | 12.4 s |
| Same question, second run | 5 | 13,418 | 710 | $0.0311 | 11.3 s |
| "Sites affected today + site details" (3 attempts) | 5 | 20,604 | 1,764 | $0.0573 | 18.4 s |
| "These 9 site details" (3 attempts) | 6 | 21,015 | 2,767 | $0.0580 | 23.3 s |
| Same combined question, later | 5 | 15,515 | 1,603 | $0.0376 | 15.1 s |
| Clarification (router only) | 1 | about 740 | about 60 | $0.0001 | about 1.5 s |

Mean over the six SQL-answering runs: **about $0.039 per question**, **11 to 23 s**, 4 to 6 LLM calls.

Where the input tokens go (*estimate* from prompt structure): the SQL prompt carries 11 retrieved chunks, about
5,000 to 6,000 tokens, and is sent again on every repair, with the failed attempts appended. That is why a
three-attempt run costs about 3x a one-attempt run: **retries multiply the dominant cost, the reference
context.** The router, judge and answer calls are each small.

Latency breakdown (*measured*, typical): route 1.3 to 2.6 s, retrieve 0.5 to 2.7 s (query embedding plus
vector search), generate 2 to 6 s, validate under 0.1 s, execute 0.35 to 0.45 s, judge 1 to 3.4 s, answer
1.5 to 2.9 s. The LLM calls dominate; the database is not the bottleneck.

## 1.4 One-off costs

| Item | Tokens / calls | Cost | Share of $125 AWS credits |
|---|---|---|---|
| Indexing the knowledge base once (*measured* tokens, *list price*) | 7,372 tokens, 34 chunks | $0.00044 at $0.06/M (and free under Voyage's 200M tokens) | 0 (not an AWS charge) |
| Retrieval eval (30 query embeddings) | about 600 tokens | negligible | 0 |
| Full agent eval v1, 30 questions (*measured*) | mean 8,206 in / 313 out per question | **$0.479 total ($0.016 per question)**; my pre-run estimate was about $1.2 | 0 (Anthropic bills outside AWS credits) |
| AWS Free plan credits | n/a | $125 remaining, 174 days | the AWS-side work (RDS already exists) |

Planning rule: **report cost as dollars and as a share of the remaining budget**, and say which budget (AWS
credits do not cover the Anthropic API or Voyage).

## 1.5 RAG versus "put the whole schema in the prompt"

*Measured*: the 10 table chunks total 2,660 tokens, about **266 tokens per table**. The whole knowledge file is
about 7,400 tokens.

| Tables in schema | Whole-schema tokens (*estimate*) | Input cost per question at $2/M (*estimate*) | Typed retrieval (11 chunks) |
|---|---|---|---|
| 10 (here) | 2.7K for tables, 7.4K with everything | $0.005 to $0.015 | about 5.5K tokens, about $0.011 |
| 100 | 27K | $0.053 | about 5.5K, about $0.011 |
| 2,000 | 532K | **$1.06 per question**, near the 1M window | about 5.5K, about $0.011 |

Conclusion for **this** schema: it is small enough that the baseline "everything in the prompt" would likely
work, and retrieval would not pay for itself on cost. The case for retrieval is **scale** (cost and attention
dilution grow with tables; retrieved context stays constant) and **precision** (less irrelevant text). Be
ready to say this honestly in an interview; the Phase 1 baseline (all docs in the prompt vs retrieval) is the
experiment that turns the claim into a number. **PENDING.**

## 1.6 Cost levers, in order of value
1. **Do not pay for what you can compute.** Durations, time-zone conversion, formatting and the grounding check
   are code: free and exact.
2. **Right-size the model per role.** A cascade: Haiku (about 20x cheaper than Sonnet on input) for routing and
   prose; Sonnet where accuracy lives. Try the strongest model at lower effort before building a cascade; a
   cascade also forfeits cache reuse across models.
3. **Effort setting** (`low` / `medium` / `high`): thinking tokens are output tokens. Measure per route.
4. **Fewer, better retrieved tokens.** Typed budget (11 chunks) instead of everything; tune `tables_k`,
   `examples_k` by ablation.
5. **Cap retries and cost** (`max_retries=3`, `max_cost_usd_per_question=0.50`): bounds the worst case.
6. **Provider prompt caching.** Caches an identical *prefix* (about 10% price on reads). Here the prefix
   (system prompt) is small and the retrieved reference differs per question, so the win is modest; it would
   matter if we put all schema docs in a static prefix (the baseline design).
7. **Batch API** (about 50% off, asynchronous): ideal for running the offline eval suite.
8. **Semantic cache** (question to SQL, never the answer, because data changes): large savings on repeated
   questions, but a wrong hit returns confidently wrong SQL. Gate by similarity threshold and measure the
   accuracy impact with the eval suite before enabling. **Not built.**
9. **Judge on/off.** The judge costs about 1 to 3.4 s and a Sonnet call per question; the ablation tells you
   whether its catches are worth it.

Always judge cost **per completed, correct task**, not per request: a cheaper request that needs more retries
is not cheaper.

---

# 2. Embedding models

## 2.1 What an embedding is
A model maps text to a vector (here 1024 numbers) so that **texts with similar meaning land close together**.
Trained with contrastive learning: pull matching (query, passage) pairs together, push non-matching apart.
Retrieval then reduces to nearest-neighbour search. Embeddings capture *topical* similarity, not exact
strings: great for "which outages are open" matching a doc about `is_open`, weak for exact identifiers such as
`INC-55821` (the case for adding keyword search).

## 2.2 Similarity: the math

For vectors `a`, `b` of dimension `d`:

```
dot(a, b)    = sum_i a_i * b_i
|a|          = sqrt(sum_i a_i^2)
cosine(a, b) = dot(a, b) / (|a| * |b|)            range -1 to 1 (text embeddings: mostly 0 to 1)
L2(a, b)     = sqrt(sum_i (a_i - b_i)^2)
```

**Normalization.** If `|a| = |b| = 1`:
`cosine(a, b) = dot(a, b)` and `L2(a, b)^2 = 2 - 2 * cosine(a, b)`. So all three metrics **rank neighbours
identically**. Voyage vectors here are normalized (*measured* length 1.0000), and Titan V2 normalizes by
default. If vectors are not normalized, dot product also rewards long vectors, which is usually unwanted.

Worked example: `a = (1, 0)`, `b = (0.6, 0.8)` (both unit length): dot = 0.6, cosine = 0.6, L2 = sqrt(0.16 + 0.64) = 0.894,
and `2 - 2 * 0.6 = 0.8 = L2^2`. ✓

pgvector operators: `<=>` cosine **distance** (`1 - cosine`), `<->` L2 distance, `<#>` **negative** inner
product (so that smaller is closer). This project stores a similarity as `1 - (embedding <=> query)`.

## 2.3 Properties to compare

| Property | Why it matters | Ours |
|---|---|---|
| **Max input length** | Longest chunk you can embed; long-context models allow big chunks | Voyage 32K; our chunks are 94 to 563 tokens |
| **Dimensions** | Storage and search cost scale with it; many models allow truncation (Matryoshka-style) | 1024; 256/512/2048 also supported |
| **Asymmetric input types** | Queries and documents embedded differently improves retrieval | Voyage `input_type` query vs document: same sentence, cosine 0.683 between roles (*measured*) |
| **Domain fit** | General models can miss domain terms (telecom codes like OOS, SC, TIS, MO) | Fixed by writing definitions into the docs |
| **Languages / modality** | Multilingual, images, code | English text only needed |
| **Hosting** | API (no ops) vs open weights (control, data residency, GPU cost) | API |
| **Price and free tier** | Indexing is one-off; query embeddings are per request | effectively free here |
| **Rate limits / quotas** | Can block you (our Bedrock quota was 0) | none hit with Voyage |
| **Stability / versioning** | Changing a model forces a re-embed and a new eval baseline | key includes model name |
| **License / residency / retention** | Compliance | n/a (synthetic data) |

## 2.4 The landscape (*snapshot*, verify before relying on any row)

| Model | Hosting | Dimensions | Max input | Price (list / reported) | Notes |
|---|---|---|---|---|---|
| **Voyage 4 family** (`voyage-4`, `-lite`, `-large`) | API | 256 / 512 / 1024 (default) / 2048 | 32,000 tokens | $0.06 / $0.02 / $0.12 per M; 200M free tokens | Retrieval-focused; `input_type`; the family is described as cross-compatible; quality claims are mostly vendor-reported |
| **Amazon Titan Text Embeddings V2** | AWS Bedrock | 1024 (default), 512, 256 | 8,192 tokens or 50,000 chars | $0.02 per M (AWS launch post) | `normalize` flag; English-optimized, 100+ languages in preview; throttled by requests per minute |
| **OpenAI `text-embedding-3-large` / `-small`** | API | 3072 default for large, shortenable via `dimensions` | about 8,191 tokens | about $0.13 per M for large (aggregators) | Widely supported by tooling |
| **Cohere Embed v4** | API, Bedrock, Azure | sources disagree on default (1,024 or 1,536) | about 128K tokens | about $0.12 per M text (aggregators) | Multimodal (text and images); long context |
| **Google `gemini-embedding-001` / `-2`** | API | 3072 default, 128 to 3072 allowed; recommended 768 / 1536 / 3072 | 2,048 tokens (001); 8,192 (2) | $0.15 per M for 001 (Google); batch 50% off | Frequently cited at or near the top of public English MTEB; `-2` is multimodal and drops `task_type` for prompt prefixes |
| **Qwen3-Embedding** (0.6B / 4B / 8B) | **Open weights** (self-host) | model-dependent | long | no per-token fee; you pay GPU | 8B model reported as #1 on MTEB multilingual (70.58) at a June 2025 snapshot; 8B needs substantial VRAM |
| Other open families (BGE, E5, GTE, Nomic, Jina) | Open weights / some APIs | varies | varies | varies | Good for self-hosting and fine-tuning; not evaluated here |

Reading the table: a model "winning MTEB" does not make it the right choice. Secondary sources summarised as:
"a model that leads MTEB by 2 points can lose to a lower-ranked model by 5 points on legal contracts, code or
medical notes", and one practical test on a private corpus (about 120 queries, directional only) found the
public leader edged out by a different API model. Vendor-reported numbers (Voyage, Cohere) are not on the
public board.

## 2.5 How to select an embedding model: the procedure

1. **Write down constraints first:** data residency and compliance, cloud (Bedrock only vs any API), budget,
   latency target, language, modality, context length needed, whether you may call external APIs.
2. **Shortlist 3 to 4** models that pass the constraints, one of them cheap and one self-hostable if relevant.
3. **Build a labeled eval from your own queries and documents** (here: the 30-question golden set with graded
   relevant chunks). Public leaderboards only shortlist.
4. **Hold everything else constant:** same chunks, same k, same index type, same prompt downstream.
5. **Measure** Hit@k, Recall@k, MRR, nDCG@k (section 6) *and* cost, latency, index size.
6. **Sweep dimensions** (for example 256, 512, 1024): storage and search cost fall with dimension; accuracy
   usually falls slowly, so find the knee.
7. **Check stability and operations:** rate limits, quotas, version pinning, deprecation, outage fallback.
8. **Decide with a Pareto view** (accuracy vs cost vs latency), write an ADR with what would change the
   decision, and re-run the comparison when the corpus changes shape (new document types, 100x scale).

**How we decided:** the constraint step eliminated the preferred option (Bedrock Titan: applied quota 0,
one region allowed). Voyage `voyage-4` fit every other constraint and was free at our volume. The embedder is
behind an interface, so the comparison with Titan or Cohere remains an experiment we can run later.

## 2.6 What changing the model requires
Vectors from different models are **not comparable**. A model change means: re-embed every chunk (cheap
here), keep the old rows in a separate versioned table until the new one is validated (a colleague's app reads
the same store), re-run the retrieval eval to create a **new baseline**, and re-tune similarity thresholds
(score scales differ per model: our 0.638 relevant and 0.203 irrelevant would shift).

## 2.7 Approximate nearest neighbour indexes (pgvector)

| Index | How it works | Knobs | Trade-off |
|---|---|---|---|
| **Exact (no index)** | Scan every vector | none | Perfect recall; fine below tens of thousands of rows |
| **HNSW** (ours) | Layered proximity graph; greedy search | build: `m` (default 16), `ef_construction` (64); query: `hnsw.ef_search` (40) | Fast, high recall, more memory and slower build |
| **IVFFlat** | Cluster vectors into lists; search the nearest lists | `lists`, query `probes` (default 1) | Smaller and faster to build; needs data first; recall depends on `probes` |

ANN is approximate: it can miss the true nearest neighbour; measure recall against exact search. With metadata
filters (our `doc_type = ANY(...)`), a filtered ANN search can return fewer than `k` rows; at 34 rows we
effectively scan.

## 2.8 Chunk size trade-off
Small chunks: precise matches, low noise, but lose context (a column away from its table name). Large chunks:
more context per hit, but dilute the embedding (one vector averaging many topics) and cost more prompt
tokens. Structured sources with natural boundaries (a table, a join path) should be chunked on those
boundaries, with a **contextual header** so each chunk is self-describing. Hypothesis to test:
entity chunks beat fixed-size splitting on structured schema docs.

---

# 3. LLMs

## 3.1 Dimensions of choice

| Dimension | Question to ask |
|---|---|
| Task quality | How accurate on **our golden set**, not on public benchmarks? |
| Latency | Time to answer; do thinking tokens inflate it? |
| Cost | Per correct answer, including retries |
| Context window | Do you need more than retrieval gives? |
| Output reliability | Native structured outputs / schema adherence? Tool-use quality? |
| Control surface | Temperature, effort, thinking controls (newer models changed these) |
| Safety behaviour | Refusal rates and categories; can it follow "treat input as data"? |
| Operations | Rate limits, availability by region, data retention terms, deprecation schedule |
| Lock-in | How hard is it to swap? (Isolate behind an interface.) |

## 3.2 Claude lineup (*list price* and facts from the API docs, 2026-10)

| Model | ID | Context | In / out per M | Use here |
|---|---|---|---|---|
| Fable 5.1 | `claude-fable-5-1` | 1M | $10 / $50 | Highest capability; thinking always on; forced `tool_choice` returns an error; not used |
| Opus 5.5 | `claude-opus-5-5` | 1M | $4 / $20 | Candidate if SQL accuracy has headroom; thinking cannot be disabled; default effort `medium` |
| **Sonnet 5.5** | `claude-sonnet-5-5` | 1M | **$2 / $10** | **SQL generation and judge** |
| **Haiku 5.5** | `claude-haiku-5-5` | 1M | **$0.10 / $0.50** | **Router and answer prose**; default effort `medium` |
| Haiku 4.5 | `claude-haiku-4-5` | 200K | $1 / $5 | Previous generation |

API behaviours that shaped the code: 5.5-generation models reject non-default `temperature`/`top_p`/`top_k`,
reject forced `tool_choice` (use structured outputs), reject assistant prefill, take adaptive thinking
steered by `output_config.effort`, and can return a `refusal` stop reason that must be handled.
We pin exact model IDs and version-control prompts so a model change is a deliberate, measured event.

## 3.3 Other providers (*snapshot*, qualitative; no prices quoted because they change)
- **OpenAI GPT family, Google Gemini family:** frontier hosted alternatives with their own reasoning controls
  and structured-output features. Choose by running **your** golden set; keep the LLM behind one function so
  swapping is a config change.
- **Open-weight models (Llama, Qwen, DeepSeek, Mistral and others):** worth it for data residency, high
  volume (fixed GPU cost instead of per token) or fine-tuning; you take on serving, scaling and safety. The
  project constraint "no local models" on this laptop rules them out here.

## 3.4 Benchmarks and why they do not transfer
- Spider 1.0 reached about 91% execution accuracy and BIRD about 73% in the original Spider 2.0 paper's
  comparison, while an agent built on `o1-preview` solved only about **21%** of Spider 2.0's enterprise
  tasks: realistic schemas, many tables and multi-step workflows are much harder than benchmark SQL.
- A 2025 study of annotation quality found expert-verified error rates of about **53%** for BIRD Mini-Dev and
  **63%** for Spider 2.0-Snow gold labels, and that correcting them reordered leaderboards (relative scores
  shifted from about -7% to +31%). Many top BIRD entries also use oracle "evidence" hints, so headline numbers
  are not comparable to no-hint use.
- Lesson: use public benchmarks to *shortlist*, then decide on a **golden set built from your own schema and
  questions**, with golden SQL you have executed and read (we run `scripts/check_golden.py` for exactly this).

## 3.5 How to choose an LLM (procedure)
1. Fix the interface (`parse(model, system, user, schema, effort)`), so models are swappable.
2. Run the golden set across 2 to 3 candidates and two effort levels per role.
3. Tabulate accuracy (execution accuracy, answer correctness), cost per question, p50/p95 latency, retry rate.
4. Plot the Pareto frontier; choose per role (cheap router, strong SQL writer).
5. Check significance (section 6.11): with 30 questions only large differences are visible.
6. Re-run on every model or prompt change; keep the previous result as the baseline.

---

# 4. How we make sure the agent is accurate

"Accurate" is several different claims. Each has its own control and its own measurement.

| Failure to prevent | Control built | Test / metric |
|---|---|---|
| The LLM never saw the right table | Typed retrieval budget, always-on rules, repair-time re-retrieval | Recall@k, Hit@k, MRR, nDCG on labeled chunks |
| Docs are vague or wrong | Hand-written knowledge file; every example SQL **executed** before embedding | `check_knowledge_examples`, coverage tests |
| SQL is invalid | sqlglot parse + schema-aware column check (`Unknown column: end_date`) before the DB | valid-SQL rate; validator unit tests |
| SQL fails at run time | Typed error from the DB, fed into the repair prompt; max retries | repair success rate; scripted fake-LLM tests |
| SQL runs but is wrong | Empty-result guard (entity exists), LLM judge, golden comparison | **execution accuracy** (strict and lenient) |
| An INNER JOIN drops the row | Documented join rules; guard probes entity existence | golden questions g09, g21, g22, g24, g27 |
| Time zone or "today" errors | UTC storage, Eastern conversion rules, explicit "current time" note | golden time-range questions g13, g14, g17 |
| Answer states a value not in the data | Facts built in code; prose grounded; template fallback | grounded rate; faithfulness unit tests |
| Duration of an ongoing outage invented | Code computes durations; open outages say "ongoing" | golden g19, g20 |
| Destructive or injected request | Router refusal, validator, read-only role | refusal accuracy; adversarial tests; live permission checks |
| Infinite or drifting loops | Retry cap, same-SQL detection, cost cap | scripted loop tests |
| Silent regression after a change | Golden dataset + eval harness (CI gate planned) | tracked in `docs/EXPERIMENTS.md` |
| Overfitting to the test set | Golden questions held out from the retrieval corpus (a test enforces it) | held-out test |
| Real users find new failures | Thumbs feedback and traces, reviewed into new golden items | feedback rate, thumbs-down review |

**Status (measured, v1 eval on 30 held-out questions):** behaviour 30/30; execution accuracy (lenient) 26/27 = 0.963
(95% interval 0.82 to 0.99); answer correctness 26/27; grounded 30/30; first-try 28/30; 2 repairs, both correct;
$0.016 per question. The interval is wide because n is small, the one miss is a comparator false negative, and the
ablations that say *which control earned its keep* (judge, retries, retrieval design) are still **PENDING**.

---

# 5. How we test

## 5.1 The testing pyramid applied (94 offline tests, all passing)

| Layer | What it proves | Where | Tests |
|---|---|---|---|
| **Unit** | Pure logic: validator, chunker, facts formatting, metrics, comparators, generator invariants | `test_validator` 26, `test_chunking` 5, `test_facts_and_compare` 9, `test_metrics` 5, `test_generate` 9, `test_embedding_cache` 4 | 58 |
| **Knowledge and dataset quality** | Every table and column documented; examples read-only; golden labels valid; golden questions held out | `test_knowledge` 4, `test_golden` 4 | 8 |
| **Scripted-LLM (fake LLM) agent tests** | Repair path, retry limit, loop detection, cost cap, refusals, empty-result handling, grounding fallback, history plumbing, all deterministic | `test_agent_graph` 17 | 17 |
| **Contract** | MCP tool names, input schemas and error shape over a **real stdio subprocess**; API SSE framing and validation | `test_mcp_contract` 8, `test_api` 3 | 11 |
| **Live checks (run by the owner)** | TLS enforced; roles cannot write; embeddings work; every example SQL executes; golden SQL returns what is intended | `scripts/check_*` | n/a |
| **End-to-end evals** | Real LLM, real database: accuracy, cost, latency | `evals/agent_eval.py`, `evals/retrieval_eval.py` | v1 run done; see 7.1 |

## 5.2 Techniques for testing a non-deterministic system
- **Scripted fake LLM.** A class with the same `parse(...)` signature that returns queued objects ("bad SQL
  first, good SQL second") and records every prompt. This proves the *loop logic* deterministically and for
  free: that the repair prompt contains the failed SQL and the error, that the unknown-column path
  re-retrieves, that the same SQL twice stops the loop.
- **Mock the edges, not the logic.** Mock the LLM and the tool layer (`SQLTools`); never mock the validator,
  facts code or graph wiring, which are the code under test.
- **Contract tests at process boundaries.** The MCP server is tested through the real protocol with a fake
  *backend*, so the schema and error vocabulary the agent relies on cannot drift silently.
- **Property and adversarial tests.** The validator is hit with DML, DDL, stacked statements, comment tricks,
  `SELECT INTO`, `FOR UPDATE`, catalog schemas, `pg_sleep`, file functions, sequence functions.
- **Tolerant assertions for real-LLM tests.** Assert key facts present, not exact wording. The newest model
  generation does not expose temperature, so determinism comes from structure (schemas, fixed facts), repeated
  runs and tolerance.
- **Snapshot-style checks on prompts** are possible (prompt text is versioned); not yet added.

## 5.3 Real bugs the tests caught (and lessons)
| Bug | Caught by | Lesson |
|---|---|---|
| A second ticket could be resolved before it was created | generator invariant test, before loading | Mirror database constraints in tests |
| "Reader cannot CREATE" failed with a *read-only transaction* error, not a privilege error | the live permission check | `SET default_transaction_read_only` applies to the next transaction; it is a guardrail, not the boundary |
| The `vector` type "did not exist" for non-owner roles | live retriever run | Missing `USAGE` on a schema shows up as a missing object |
| Validator missed `nextval()` (a state-changing SELECT) | design review of defence layers | Do not rely on one layer; add the function to the denylist and test it |
| Ids printed as "1,234" | the first live trace | Formatting rules depend on column meaning, not only type |

## 5.4 What tests cannot tell you
Unit and fake-LLM tests prove the *machinery*. They say nothing about whether Sonnet writes correct SQL for
your questions. That is what the golden dataset and the metrics in the next section are for.

---

# 6. Metrics: what each one means, with the math

## 6.0 How to read the notation (start here)

**`@k`** means "look only at the first `k` results". Retrieval returns a ranked list (best first); `k` is how far
down you look. **`k = 3`** is a strict view (only the top three), **`k = 11`** is the whole list our agent hands
to the LLM.

**Why 11 here.** The typed retrieval returns 2 always-on rules + 4 tables + 2 join/glossary + 3 examples = **11 chunks**.
So **k = 11 is "everything the LLM is actually given"**, and it is the fair size at which to compare plain
retrieval with typed retrieval (give both the same number of chunks).

**Reading `Recall@11 = 0.983`.** Every question has a short list of chunks the LLM *must* have (usually 1 to 3 table
chunks, called the **required** or **relevant** set). For one question, Recall@11 = (required chunks found in the 11
results) ÷ (required chunks). The reported number is the average over the 30 questions. Here: 29 questions found all
their required chunks (1.0 each) and one found half of them (0.5; the missing one is `Table ops.users`, because
"Priya Shah" does not name that table), so `(29 + 0.5) / 30 = 0.983`.

**Reading `Hit@11 = 1.0`.** For each question: did *at least one* required chunk appear? 1.0 means yes for all 30.
Hit is lenient; Recall is the stricter, more useful number when a query needs several tables.

**`Precision@11 = 0.173`** looks low and is not a problem: only 1 to 3 chunks are required, so even a perfect
retriever would score about 2/11 ≈ 0.18. Do not optimize it.

**`nDCG@11`** rewards putting the most important chunks *high* in the list, not only somewhere in it
(section 6.2). **`MRR`** looks only at the rank of the *first* required chunk (section 6.1). Typed lists put the
always-on rules first, so their MRR and their `@3` / `@5` columns are not comparable with plain retrieval; compare
only at `@11`.

**The golden set** (30 questions, ids `g01` to `g30`): hand-written test questions with known-correct answers and
labelled relevant chunks, kept *out of* the knowledge base so we never test on what the system has memorized.
`g08` simply means "golden question number 8".

## 6.1 Retrieval metrics, binary relevance

`ranked` = result list, best first. `Rel` = set of relevant items. `k` = how many results you look at.

```
Hit@k        = 1 if any item of Rel is in the top k, else 0                       (mean over queries)
Recall@k     = |top-k ∩ Rel| / |Rel|
Precision@k  = |top-k ∩ Rel| / k
F1@k         = 2 * P@k * R@k / (P@k + R@k)
RR           = 1 / rank of the first relevant item   (0 if none);   MRR = mean of RR over queries
AP           = (1/|Rel|) * sum over relevant items at rank r of  Precision@r;   MAP = mean AP over queries
R-precision  = Precision at rank R, where R = |Rel|
```

**Worked example.** `ranked = [A, B, C, D, E]`, `Rel = {B, D}`.

| k | top-k | found | Hit | Recall | Precision | F1 |
|---|---|---|---|---|---|---|
| 1 | A | none | 0 | 0 | 0 | 0 |
| 2 | A B | B | 1 | 1/2 = 0.5 | 1/2 = 0.5 | 0.5 |
| 3 | A B C | B | 1 | 0.5 | 1/3 = 0.333 | 2(0.333)(0.5)/(0.833) = 0.4 |
| 5 | A B C D E | B, D | 1 | 1 | 2/5 = 0.4 | 2(0.4)(1)/(1.4) = 0.571 |

- RR: first relevant (B) at rank 2, so RR = 1/2.
- AP: B at rank 2 gives precision 1/2; D at rank 4 gives precision 2/4. AP = (0.5 + 0.5) / 2 = **0.5**.
- R-precision: R = 2, top 2 = A B has 1 relevant, so **0.5**.

**Hit vs Recall:** Hit asks "did we find *anything*"; Recall asks "how much of what we need". For schema
retrieval a SQL query often needs **two or three** tables, so Hit can be 1.0 while Recall is 0.5: the LLM got
one table and must guess the join. **Recall matters most for schema retrieval**, because a missing required
table makes correct SQL impossible, while an extra table is only noise.
**MRR vs MAP vs nDCG:** MRR scores only the *first* relevant result; MAP uses all relevant results with
binary relevance; nDCG uses all results with *graded* relevance and discounts by rank.

## 6.2 Graded relevance: DCG and nDCG

Our labels: required table = 2, helpful chunk = 1, other = 0.

```
DCG@k  = sum_{i=1..k}  gain_i / log2(i + 1)         (linear gain = the grade)
IDCG@k = DCG of the ideal ordering (grades sorted high to low)
nDCG@k = DCG@k / IDCG@k                              range 0 to 1
```
(Some libraries use gain `2^grade - 1`; the choice changes the numbers, so state which one you use.)

**Worked example** (same list, grades `B = 2`, `D = 1`):
`DCG@5 = 2/log2(3) + 1/log2(5) = 1.2619 + 0.4307 = 1.6925`.
`IDCG@5 = 2/log2(2) + 1/log2(3) = 2 + 0.6309 = 2.6309`. `nDCG@5 = 1.6925 / 2.6309 = 0.643`.
(These exact values are unit tests in `tests/test_metrics.py`.)

**Whiteboard problem.** Ranked list `[C, A, B]` with grades `C = 1`, `A = 3`, `B = 2`, `k = 3`:
`DCG = 1/1 + 3/log2(3) + 2/log2(4) = 1 + 1.8928 + 1 = 3.8928`;
ideal order `[A, B, C]`: `IDCG = 3/1 + 2/log2(3) + 1/log2(4) = 3 + 1.2619 + 0.5 = 4.7619`;
**nDCG@3 = 0.8175.**

## 6.3 Reading our retrieval baseline (*measured*, plain top-k, 30 questions)

| | k=3 | k=5 | k=8 |
|---|---|---|---|
| Hit@k | 0.600 | 0.800 | 0.900 |
| Recall@k | 0.517 | 0.700 | 0.817 |
| Precision@k | 0.244 | 0.213 | 0.171 |
| nDCG@k | 0.422 | 0.503 | 0.556 |

MRR = 0.485. **Reading exercise.** Diagnosis: *Recall is the bottleneck* (0.70 at k=5): 12 of 30 questions miss
a required table. *Precision is low by construction*: only 1 to 3 chunks are relevant per question, so at k=5
precision cannot exceed about 0.4, and it is the wrong target for schema retrieval. *MRR 0.485* means the first
required chunk is typically around rank 2. Root cause (from the `top5` lists): short example chunks outrank
long table chunks. Fix tried: reserve slots per chunk type (`typed`). Next knobs if it is still low: hybrid
keyword search for identifiers, a reranker, schema-graph expansion, larger `tables_k`.
**What the metric hides:** it scores chunks, not whether the final SQL is right; a "miss" on a helpful chunk
may not matter, a "hit" on the wrong table can still mislead. Hence end-to-end metrics below.

## 6.3b Typed vs plain retrieval at equal context size (*measured*)

| | Hit@11 | Recall@11 |
|---|---|---|
| Plain top-k | 0.967 | 0.933 |
| Typed budget (2 rules, 4 tables, 2 structure, 3 examples) | 1.000 | 0.983 |

(Clean re-run after pruning a stale duplicate chunk. nDCG@11: plain 0.604, typed 0.581: typed wins Hit and Recall but loses a little nDCG, because the always-on rules chunks occupy the first ranks and are rarely labelled relevant.)

Misses in the first five slots fall from 12 to 2 (both for the `users` table). **Why this is a weak experiment:**
k = 11 is a third of a 34-chunk corpus, so any method scores high; the typed k=3/5 columns and MRR (0.279) are
not comparable because always-on rules are listed first; and 2 of the 12 plain misses were the always-on rules
chunk, which typed retrieval handles by construction. A discriminating test needs a larger corpus or a smaller
budget (for example `tables_k = 2`).

## 6.4 RAG metrics (context, faithfulness, relevance)
Libraries such as RAGAS define these; definitions differ across versions, so check the installed version.

| Metric | Question | Formula (typical) | Needs ground truth? |
|---|---|---|---|
| **Context precision** | Are the relevant chunks ranked near the top? | `sum_k (Precision@k * v_k) / (relevant items in top K)`, `v_k = 1` if item `k` is relevant. Equals AP for binary labels (our example: 0.5) | Yes (relevance) |
| **Context recall** | Does the retrieved context contain what the reference answer needs? | `(reference-answer statements supported by the context) / (statements in the reference)` | Yes (reference answer) |
| **Context relevance** | What share of the context is on-topic? | LLM-judged fraction of relevant sentences | No |
| **Faithfulness / groundedness** | Is every claim in the answer supported by the context/rows? | `(claims supported) / (total claims)`, e.g. 4 of 5 = 0.8 | No |
| **Answer relevancy** | Does the answer address the question? | mean cosine similarity between the question and questions regenerated from the answer | No |
| **Answer correctness** | Is the answer right? | blend of factual overlap with the reference and semantic similarity | Yes |
| **Noise sensitivity** | How often does irrelevant retrieved context cause a wrong claim? | share of incorrect claims attributable to noise | Yes |

**Our implementations.** Faithfulness is **deterministic and strict**: every number and code in the answer must
appear in the retrieved rows (`faithfulness_violations`); this is stronger than an LLM judge for numeric
claims and costs nothing. Answer correctness: every value of the golden result must appear, formatted as a
user sees it (`golden_values_in_answer`), and the result set must match. "Faithfulness high but correctness
low" means the answer is honest about the *wrong rows*: the SQL was wrong, so look at retrieval and SQL, not at
the prose.

## 6.5 Text-to-SQL metrics

| Metric | Definition | Pitfall |
|---|---|---|
| **Valid-SQL rate** | share of generated queries that parse and execute | A valid query can be wrong |
| **Execution accuracy (EX)** | generated result set equals golden result set | Two empty results "match" by accident (so zero-row questions are labeled) |
| **EX strict** (ours) | same rows, same column order, order-insensitive | Rejects extra identifying columns |
| **EX lenient** (ours) | some subset of the generated columns reproduces the golden rows, ignoring aliases and order | Most faithful to "the user got the right data" |
| **Exact match** | SQL text equal to golden | **Poor**: many different queries are equally correct |
| **Component match** | SELECT / FROM / WHERE / GROUP BY clauses compared separately | Partial credit but still syntactic |
| **First-try success** | correct with no repair | measures the generator, separate from the loop |
| **Repair success rate** | of questions that needed a repair, the share that ended correct | shows the loop's value |
| **Retries per question** | mean repairs | cost driver |

**Our v1 numbers** (n = 27 data questions): lenient 26/27 = 0.963, strict 12/27 = 0.444. They differ because
the SQL writer is told to return identifying columns next to the answer; strict compares shape, lenient compares
data. The single lenient miss (g21) is a representation difference: a LEFT JOIN row of NULLs versus a golden
`COUNT(*) = 0`. This is the standard weakness of execution accuracy: semantically equal answers can differ in
shape, so read failures, do not only count them.

How our EX compares results: values are normalized (numbers rounded to 2 decimals, ISO timestamps compared as
instants), row multisets are compared (order-insensitive), and for lenient matching we search for a mapping from
golden columns to generated columns whose value multisets agree, then compare the projected rows.
Golden results are produced by the **same backend** the agent uses, so serialization cannot cause false
mismatches.

## 6.6 Answer and judge metrics
- **Key-fact presence** (deterministic, ours) is preferred wherever the facts are checkable.
- **LLM-as-judge** for what cannot be checked deterministically (completeness, tone). Known biases:
  *position* (prefers the first option), *verbosity* (prefers longer answers), *self-preference* (prefers
  its own family's style). Mitigate: randomize order, use a rubric, use a different model family as judge when
  possible, and **calibrate against human labels** (below).
- **Refusal accuracy** is a classification problem (section 6.8).

## 6.7 Metrics for free text (and why they are weak here)
Exact match and token-level F1 reward overlap with a reference string. ROUGE/BLEU count n-gram overlap and
penalize correct paraphrases; they were built for translation and summarisation of fixed references.
Embedding similarity or BERTScore capture meaning better but cannot detect a *wrong number*. For data answers
prefer deterministic fact checks.

## 6.8 Classification metrics (router, refusal detection)

```
Precision = TP / (TP + FP)        Recall = TP / (TP + FN)        F1 = 2PR / (P + R)
Accuracy  = (TP + TN) / all
```
**Worked example (imbalanced):** 100 questions, 20 should be refused, 80 normal. The router refuses 17 of the 20
(TP = 17, FN = 3) and wrongly refuses 4 normal ones (FP = 4, TN = 76).
Precision = 17/21 = 0.810; Recall = 17/20 = 0.85; F1 = 0.829; **Accuracy = 93/100 = 0.93**, while a router that
*never* refuses scores 0.80: accuracy hides imbalance, so report precision and recall. In this product a
false refusal (FP) annoys users and a missed refusal (FN) is a safety issue; the costs are asymmetric, which
sets the threshold.

**Macro vs micro averaging** (3 classes). Class A: TP 8, FP 2, FN 2 (P = R = F1 = 0.8). Class B: TP 1, FP 1,
FN 4 (P = 0.5, R = 0.2, F1 = 0.286). *Macro F1* = mean of per-class F1 = (0.8 + 0.286)/2 = **0.543** (each class
counts equally). *Micro* pools counts: TP 9, FP 3, FN 6, P = 0.75, R = 0.6, F1 = **0.667** (big classes dominate).
*Weighted* averages per-class scores by class frequency.
**Confusion matrix** shows which classes get confused (for example `clarify` vs `answer`).
**Thresholds:** a model that outputs a score needs a cutoff; sweeping it gives the **precision-recall curve**
(better for rare positives) and the **ROC curve** (true-positive rate vs false-positive rate). **AUC** is the
probability that a random positive scores above a random negative (0.5 = chance).

## 6.9 Agent metrics
- **Task success rate:** share of questions answered correctly end to end.
- **Tool-call accuracy / trajectory quality:** did it call the right tool with valid arguments; were the steps
  sensible (our trace records every node).
- **Steps and cost per task:** retries, LLM calls, tokens, dollars.
- **pass@k and pass^k.** Run each question `n` times; `c` of them succeed.
  `pass@k = 1 - C(n-c, k) / C(n, k)` (probability at least one of `k` tries is correct; measures *capability*).
  `pass^k ≈ (c/n)^k` (probability *all* `k` tries are correct; measures *reliability*).
  Example `n = 10`, `c = 6`, `k = 3`: pass@3 = 1 - C(4,3)/C(10,3) = 1 - 4/120 = **0.967**; pass^3 = 0.6^3 = **0.216**.
  A demo-quality system has high pass@k; a production system needs high pass^k.

## 6.10 Judge reliability: agreement and Cohen's kappa
Percent agreement is inflated by chance. **Cohen's kappa** corrects it:
`kappa = (p_o - p_e) / (1 - p_e)`, `p_o` = observed agreement, `p_e` = agreement expected by chance from each
rater's marginal rates.
Example: 100 items; both say yes 40, both no 40, A yes/B no 10, A no/B yes 10. `p_o = 0.80`. Each rater says
yes 50%, so `p_e = 0.5*0.5 + 0.5*0.5 = 0.50`. **kappa = (0.80 - 0.50)/(1 - 0.50) = 0.60** ("moderate to
substantial"; as a rough guide, below 0.4 is weak, above 0.8 is strong). Plan: have a human label about 30
answers, compare with the LLM judge, and only trust the judge where kappa is acceptable. **Not done yet.**

## 6.11 Statistics for evals (is a difference real?)

**Confidence interval for an accuracy.** With `p̂` correct out of `n`, the **Wilson interval** is
`center = (p̂ + z²/2n) / (1 + z²/n)`, `half = z * sqrt(p̂(1-p̂)/n + z²/4n²) / (1 + z²/n)`, `z = 1.96` for 95%.
Example: 24 of 30 correct (`p̂ = 0.8`): center 0.766, half 0.139, interval **[0.63, 0.91]**. A score of 80% on
30 questions is compatible with anything from 63% to 91%.

**Comparing two systems on the same questions** (paired). Count `b` = A right and B wrong, `c` = A wrong and B
right; ties carry no information. Under "no difference" the discordant pairs split 50/50, so use an exact
binomial (sign) test: two-sided `p = 2 * P(X ≤ min(b, c))` with `X ~ Binomial(b + c, 0.5)`. Example `b = 6`, `c = 1`:
`p = 2 * (1 + 7)/128 = 0.125`, not significant. Consequence: **on 30 questions, a system must win at least 6
discordant questions and lose none to reach p < 0.05** (`b = 6, c = 0`: `p = 2/64 = 0.031`). Small improvements
are invisible; this is why the golden set must grow and why we repeat runs.

**Run-to-run variance.** Models without a temperature setting still vary; run each configuration several times
and report mean and spread (or bootstrap: resample questions with replacement many times and take the 2.5th and
97.5th percentiles of the metric).

**Held-out data and overfitting.** Tuning prompts and `k` against the same 30 questions overfits them. Keep a
held-out slice untouched until the end, and keep golden questions out of the retrieval corpus (a test enforces
that no golden question appears in the knowledge examples). Golden sets go stale when the schema, the
questions users ask, or the data change: review them when any do, and add thumbs-down cases from production.

**Sample size, roughly.** To detect a 5-point difference between two *independent* groups at 80% power and 5%
significance needs about `2(1.96 + 0.84)² p(1-p) / δ²` ≈ 1,000 per group at `p = 0.8`; pairing helps a lot, but
the lesson stands: tens of questions detect only large effects.

## 6.12 Operational metrics
- **Latency percentiles.** p50 is the median; p95 is the value below which 95% of requests fall (nearest-rank:
  the `ceil(0.95 n)`-th smallest; for 30 requests, the 29th). Report p50 and p95 (and p99 for services); means
  hide tail latency. *Measured so far:* 11 to 23 s per SQL answer, about 1.5 s for clarifications.
- **Tokens and cost per question**, split by role, so the retry multiplier is visible.
- **Tool error rate** (MCP failures by `error_kind`).
- **Cache hit rate** `= hits / (hits + misses)`, reported together with the **accuracy impact** (a semantic
  cache with a loose threshold can raise hit rate while lowering accuracy).

## 6.13 Metric to knob map

| Symptom | Likely cause | First knob |
|---|---|---|
| Low Recall@k | Right chunk not retrieved; examples crowd tables | Typed budget, hybrid search, larger `tables_k`, metadata filter |
| Good recall, low EX | LLM misuses correct context | Better docs and gotchas, stronger model, effort, judge |
| High first-try, low repair success | Errors are semantic, not syntactic | Judge, examples for the failing category |
| High valid-SQL, low EX | Wrong-but-runnable SQL | Result checks, judge, join guidance |
| High faithfulness, low correctness | Honest answer over wrong rows | Fix SQL/retrieval, not prose |
| Low refusal recall | Router prompt, injection patterns | Router examples, validator backstop |
| High cost, flat accuracy | Retry multiplier, oversized context, strong model on easy roles | Cap retries, shrink context, cascade |
| Good offline, bad online | Golden set unrepresentative | Add production failures to the golden set |

---

# 7. Results so far and the experiment plan

## 7.1 Recorded results

| Item | Value | Status |
|---|---|---|
| Retrieval, plain top-k, k=3/5/8 | see 6.3 (Recall@5 0.70, MRR 0.485) | *measured* |
| Retrieval, typed vs plain at k=11 | Hit 0.967 → 1.000, Recall 0.933 → 0.983 at k = 11 (not discriminative at 34 chunks; clean re-run after pruning; nDCG@11 0.581 vs 0.604) | *measured* |
| Full agent eval v1 on 30 questions | behaviour 1.000; EX lenient 0.963, strict 0.444; answer correctness 0.963; grounded 1.000; first-try 0.933; 2 repairs (both correct); mean retries 0.067; 8,206 in / 313 out tokens; $0.016 per question ($0.479 total); latency p50 71 s / p95 218 s **inflated by Voyage rate limiting, not service latency** | *measured* |
| Live traces | outage 1234 correct and grounded; follow-up and "today" issues found and fixed | *measured*, anecdotal (n = 6) |
| Offline tests | 94 passing | *measured* |
| Indexing | 34 chunks, 7,372 tokens, about $0.0004 list price | *measured* |

## 7.2 Planned ablations (one variable at a time; record each in `docs/EXPERIMENTS.md`)
1. Retrieval: plain top-k vs typed budget (k=11).
2. `semantic_check` on vs off (does the judge help or hurt?).
3. `max_retries` 0, 1, 2, 3 (what does the loop add?).
4. `SQL_MODEL`: Haiku 5.5 vs Sonnet 5.5 vs Opus 5.5; `SQL_EFFORT` low / medium / high.
5. `examples_k` 0, 1, 3, 5 and `tables_k` 2, 4, 6.
6. Baseline "everything in the prompt" vs retrieval (accuracy, tokens, cost).
7. Embedding dimensions 256 / 512 / 1024 (Voyage), and the query-vs-document `input_type` effect.
8. Chunking: entity vs fixed-size vs recursive (build the two baselines).
9. Add hybrid search (keyword + vector) and measure the identifier questions (g08, g12, g21).
10. Prompt versions (`p1` vs a revised `p2`).

Each experiment records: what changed, metrics before/after with a confidence interval, cost, latency, and a
conclusion; no change counts as "better" without numbers.

---

# 8. Caching in agentic systems

## 8.1 Why caching an agent is not caching a website
A web cache stores a response that is *the same for everyone and stays valid*. An agent's outputs break all three
assumptions:

| Web caching | Agent caching |
|---|---|
| Same URL, same answer | Same words can mean different things (a date, an id, "today", "that outage") |
| Wrong staleness is a minor annoyance | A **wrong hit is a confidently wrong answer**, indistinguishable from a right one |
| Key = the request | Key must also include the *knowledge version, prompt version, model, permissions, and time anchor* |
| Cost = bandwidth | Cost = **tokens** and **seconds of LLM time**, so the payoff is large, and so is the risk |
| Responses are static | Underlying **data changes**, so cache the *method* (SQL), not the *result* |

Rule of thumb: cache what is **expensive, deterministic given its inputs, and safe to reuse**; recompute whatever
depends on **fresh data, user identity, or the current time**.

## 8.2 The layers of an agent, from cheapest and safest to riskiest

| # | Layer | What is stored | Key | Safe? | Status here |
|---|---|---|---|---|---|
| 1 | **Embedding cache (documents)** | vector of a chunk | hash of chunk text + model + dimensions | Very safe: pure function | **Built** (`rag.chunks` content-hash key) |
| 2 | **Embedding cache (queries)** | vector of a question | model + dimensions + exact text | Very safe | **Built** (`data/query_embedding_cache.jsonl`) |
| 3 | **Retrieval cache** | the list of chunks for a question | normalized question + knowledge version | Safe if invalidated on re-index | Not built |
| 4 | **Provider prompt cache** (prefix cache) | the model's processed prefix of a prompt | automatic, by exact prefix | Safe: does not change output | Not built |
| 5 | **Tool-result cache** (MCP) | rows returned by a query | exact SQL + data version, short TTL | Safe only for read-only, idempotent tools, with TTL | Not built |
| 6 | **Semantic cache** | question → verified SQL | embedding similarity + guards + versions | **Risky**: wrong hits | Not built |
| 7 | **Template / parameterized cache** | SQL with slots (`{month}`, `{outage_id}`) | intent + slot types | Safer than raw semantic cache | Not built |
| 8 | **Final-answer cache** | the prose answer | question | **Do not**: data changes, user-specific | Deliberately not planned |
| 9 | **Run-local memo** | repeated tool calls inside one run | exact call | Safe | Partly (existence probes are cheap) |

### Measured evidence for layer 2
The retrieval eval over 30 questions took **596 s** the first time (28 uncached Voyage calls, paced about 21 s
apart by the rate-limit pacer) and **9 s** the second time (every query served from the cache). Same results,
a 66x speedup, and zero API calls.

## 8.3 Provider prompt caching, in depth (layer 4)

**Mechanism.** The provider stores the processed form of the *beginning* of your prompt. If a later request starts
with exactly the same bytes, that prefix is read from cache instead of reprocessed. It is a **prefix match**: one
changed byte anywhere in the prefix invalidates everything after it. The render order is tools, then system, then
messages.

**Economics (Anthropic first-party; provider terms vary).** Cache *reads* cost about 0.1x the normal input price,
cache *writes* about 1.25x (5-minute lifetime; a 1-hour lifetime costs more to write). Verify with
`usage.cache_read_input_tokens` and `cache_creation_input_tokens`; zero reads across repeated identical prefixes
means a hidden invalidator (a timestamp or UUID in the system prompt, unsorted JSON, a changing tool list). A
minimum prefix size applies (model-dependent, roughly 512 to 4,096 tokens): shorter prefixes silently do not cache.

**Design rule: stable first, volatile last.**
```
[tools] [system prompt] [static reference] ......cache breakpoint...... [question] [attempts] [new instruction]
```

**Where it helps this agent.** The repair loop re-sends the *same* 5,000 to 6,000 token reference on every retry
(section 1.3: a 3-attempt run costs about 3x a 1-attempt run). With a breakpoint after the reference and question,
retries read that prefix at about a tenth of the price. Estimate at Sonnet's list price: a 6,000-token prefix costs
about $0.012 uncached and about $0.0012 when read from cache, saving roughly $0.011 per retry. **Expected benefit
here is small**, because only 2 of 30 questions needed a repair (7%), and it is bigger for (a) multi-turn
conversations that resend history, and (b) the "whole schema in the prompt" design, where one large static prefix
is shared by *every* question.

**Pitfalls.** Cache is per model (a model cascade forfeits sharing between models); changing the system prompt,
tools, or thinking/effort settings can invalidate it; the cache is per workspace/account; and a cache hit changes
cost and latency but **never output**, which is why it is the safest agent cache.

## 8.4 Semantic caching, in depth (layer 6)

**Idea.** Embed the new question; if it is similar enough to a past question, reuse that question's **SQL** (never
its answer), skipping retrieval and the expensive SQL-generation call.

**How it fails.** Similar is not equal. Embeddings capture topic, not exact values:
- "critical outages in **August**" vs "critical outages in **September**": nearly identical vectors, different SQL.
- "outage **1234**" vs "outage **1243**": same shape, different entity.
- "affected **today**" asked on two different days.
A wrong hit returns confidently wrong results, with no error to trigger a repair.

**Metrics.** Cache **hit rate** = hits / lookups. **Wrong-hit rate** = incorrect hits / hits. **Cache precision** = 1 -
wrong-hit rate. You choose a similarity **threshold** τ: raising τ lowers hit rate and wrong hits; lowering it
raises both. Pick τ on the golden set, where you can *measure* wrong hits, and report hit rate **together with**
accuracy impact. (Illustrative: if τ gives a 40% hit rate but 3% of hits are wrong, then 1.2% of all questions are
wrong because of the cache; decide whether that is acceptable.)

**Mitigations, in increasing strength:**
1. **Guards on literals.** Extract numbers, dates, ids, codes, names from both questions; require them to be
   equal, or to be substituted into a template, before accepting a hit.
2. **Two-stage hit.** Semantic candidate first, then a cheap verifier (a small LLM or a rule) decides "same intent
   and same parameters?".
3. **Parameterized templates (layer 7).** Cache the *shape*: `SELECT … WHERE outage_id = :id`. Slots are filled from
   the question by code. High hit rate and no value-mixing errors.
4. **Cache only verified entries.** Store SQL only when it passed validation, executed, was accepted by the judge,
   and ideally got a thumbs-up; never cache a failure or an empty result unverified. This prevents **cache
   poisoning**, where one bad answer is served repeatedly.
5. **Scope the key.** Include knowledge version, prompt version, model, schema version, user permission scope
   (so a cached query never leaks across roles), and the time anchor for relative-date questions.

## 8.5 Result and tool caching (layer 5)
Caching the **rows** of an exact SQL is safe only with a short **TTL** (time to live) matched to how fast the data
changes (seconds to minutes for live operations data, longer for slowly changing dimensions), and only for
read-only, idempotent tools. Never cache tool calls with side effects. In this project the data is a frozen
snapshot, so TTL could be long; in a live system it must not be.

## 8.6 Invalidation: the hard part
| Strategy | How | Use for |
|---|---|---|
| **Version in the key** | `knowledge_hash`, `prompt_version`, `schema_version` are part of every key; a change makes old entries unreachable | Retrieval, semantic and template caches (best default) |
| **TTL** | Entries expire after a time | Tool/result caches |
| **Event-driven** | A migration or re-index publishes an invalidation | Schema and knowledge changes |
| **Write-through / refresh-ahead** | Update the cache when the source changes, or refresh before expiry | Hot entries |
| **Stale-while-revalidate** | Serve the old value while recomputing | Latency-critical, tolerance for brief staleness |
| **Stampede control** | Collapse concurrent misses on the same key into one computation | Hot popular questions |
| **Negative caching** | Cache "not found" for a short time only | Existence probes; keep TTL tiny, since a new record may appear |

Our content-hash scheme for chunks is the cleanest example: the key *is* the content, so an edited section simply
has a new key, and the pruning step removes the superseded one.

## 8.7 Agent-specific caching ideas beyond the classic layers
- **Run-local memoization:** inside one run, never repeat an identical tool call (the existence probe).
- **Trajectory / skill caching:** save a *successful* sequence (question pattern → SQL template → checks) and reuse
  it as a few-shot example or a template; this is how "agent memory" improves over time. Gate by feedback.
- **Conversation summarization as compression:** replace old turns with a short summary to keep prompts small
  (a context-management technique, not a cache, but it protects the cached prefix from growing).
- **Provider KV cache:** inside the model server, attention keys/values for a prefix are reused; prompt caching
  exposes this as a product feature. You influence it only by keeping prefixes stable.
- **Multi-agent systems:** share a read-through cache of tool results between agents and key it by the *tool and
  arguments*, not by the agent, with the same TTL and permission rules.

## 8.8 What to measure
| Metric | Meaning |
|---|---|
| Hit rate per layer | How often each layer saves work |
| **Wrong-hit rate** (semantic layers) | The accuracy cost; must be near zero for SQL |
| Tokens and dollars saved | `cache_read_input_tokens` x price difference; avoided SQL-generation calls |
| Latency saved | p50 and p95 with and without |
| Staleness incidents | Answers served after the underlying data or knowledge changed |
| Accuracy delta | Re-run the golden set with the cache on vs off (an ablation, like any other change) |

## 8.9 What I would build next, in order, for this project
1. **Provider prompt caching** with a breakpoint after the reference: no accuracy risk, saves retry cost.
2. **Retrieval cache** keyed by question + knowledge hash: removes the 0.5 to 2.7 s retrieve step on repeats.
3. **Parameterized SQL templates** for the most common intents (open outages, outage by id, ticket by number): safe, big win.
4. A **semantic cache** only after (3), gated by literal guards and measured wrong-hit rate on the golden set.
Never cache final answers; always version keys; always run the golden set with the cache on before enabling it.

---

# Appendix A. Glossary of every technical term

Plain-language definitions, with where each appears in this project.

## A.1 Search and retrieval
| Term | Meaning |
|---|---|
| **Corpus** | The collection being searched. Here: the 34 chunks of the knowledge file. |
| **Chunk** | One searchable piece of the corpus (a table description, a join-path block, one example). |
| **Embedding / vector** | A list of numbers (1024 here) representing a text's meaning; similar meanings are close together. |
| **Dimension** | The length of that list. More dimensions can hold more nuance and cost more to store and search. |
| **Normalization** | Scaling a vector to length 1 so that cosine and dot product agree. |
| **Cosine similarity** | How aligned two vectors are (1 = same direction). pgvector's `<=>` is cosine *distance* (= 1 - similarity). |
| **Query vs document embedding** | Some models embed a question and a passage differently (`input_type`); Voyage does. |
| **Top-k / k** | The first `k` results of a ranked list. "k = 5" means look at five. |
| **`@k` notation** | A metric computed within the top `k` results, e.g. Recall@5. |
| **Ranked list** | Results ordered best first. |
| **Relevant / required / helpful** | A chunk the LLM needs (grade 2) or that merely helps (grade 1), per our labels. |
| **Relevance labels / grades** | Hand-assigned judgments of which chunks matter for each golden question. |
| **Retriever** | The component that returns chunks for a question. |
| **Typed retrieval (budget)** | Retrieving each chunk *type* separately with a fixed slot count (2 rules, 4 tables, 2 structure, 3 examples). |
| **Always-on chunk** | A chunk included for every question (the rules); treated as instructions, not search results. |
| **Dynamic few-shot** | Choosing the example queries shown to the LLM by similarity to the current question. |
| **Hybrid search** | Combining vector search with keyword search (BM25). |
| **BM25** | A classic keyword-ranking formula that scores exact-word matches. |
| **Reranker** | A second model that re-orders the top candidates more precisely. |
| **Reciprocal rank fusion (RRF)** | A simple way to merge two ranked lists: score = sum of 1/(c + rank). |
| **Metadata filter** | Restricting search by stored attributes (`doc_type`, `tables`). |
| **Schema-graph expansion** | Adding tables connected by foreign keys to the retrieved set. |
| **ANN (approximate nearest neighbour)** | Fast, slightly inexact vector search. |
| **HNSW / IVFFlat** | Two ANN index types in pgvector (graph vs clusters). |
| **pgvector** | The Postgres extension that stores vectors and does similarity search. |
| **Chunking strategy** | How a document is cut into chunks (fixed-size, recursive, structure-aware, semantic, entity-based, parent-child, multi-vector). |
| **Contextual header** | A line prepended to a chunk naming its origin so it stays meaningful alone. |
| **Content hash** | A fingerprint of text; the cache key for an embedding. |
| **Stale chunk** | An old version of a chunk left in the index after its source changed. |

## A.2 Evaluation
| Term | Meaning |
|---|---|
| **Golden dataset / set** | Test questions with known-correct answers (`g01` to `g30`). |
| **Held-out** | Kept out of the knowledge base and out of tuning, so it measures generalization. |
| **Baseline** | The simplest thing, measured first, that every later change must beat. |
| **Ablation** | Changing one thing and measuring the effect, to learn what earns its cost. |
| **Hit@k** | Did any required chunk appear in the top k? |
| **Recall@k** | What fraction of the required chunks appeared in the top k? |
| **Precision@k** | What fraction of the top k were relevant? |
| **MRR** | Mean of 1 / rank of the first relevant result. |
| **MAP / AP** | Average precision at each relevant rank, averaged over queries. |
| **DCG / IDCG / nDCG** | Discounted cumulative gain, its ideal value, and their ratio (0 to 1). |
| **Gain / discount** | Gain = a result's grade; discount = dividing by log2(rank + 1) so lower ranks count less. |
| **Execution accuracy (EX)** | Generated SQL returns the same result as the golden SQL. |
| **Strict vs lenient EX** | Strict compares column-for-column; lenient allows extra columns and ignores aliases. |
| **Valid-SQL rate** | Share of queries that parse and run. |
| **First-try success** | Correct without any repair. |
| **Repair success rate** | Of questions that needed a repair, the share that ended correct. |
| **Faithfulness / groundedness** | Every claim in the answer is supported by the retrieved rows. |
| **Hallucination** | A stated fact the data does not support. |
| **LLM-as-judge** | Using a model to grade an output. |
| **Cohen's kappa** | Agreement between two raters corrected for chance. |
| **Confidence interval (Wilson)** | The range of true accuracy compatible with the measured one. |
| **p50 / p95** | The median and the 95th-percentile latency. |
| **False negative (in an eval)** | A correct answer wrongly marked wrong by the checker (g21). |

## A.3 LLMs and prompting
| Term | Meaning |
|---|---|
| **Token** | A piece of text (about 4 English characters); the unit of cost and context. |
| **Input / output / thinking tokens** | What you send / what the model writes / its internal reasoning (billed as output). |
| **Context window** | The most tokens a model can take in at once. |
| **System prompt** | Standing instructions placed before the conversation. |
| **Structured output** | A response forced to match a JSON schema (Pydantic model). |
| **Effort** | A setting that controls how much the model thinks (`low` to `max`). |
| **Adaptive thinking** | The model decides how much to reason per request. |
| **Temperature** | Randomness control; not available on the newest models. |
| **Refusal** | A model declining to answer; surfaced as a stop reason. |
| **Prompt injection** | Text in the input that tries to override your instructions. |
| **Few-shot examples** | Example question→answer pairs shown in the prompt. |
| **Router** | A cheap first call that classifies the question (answer / clarify / refuse). |
| **Judge** | A second model call that reviews a result. |
| **Interpretation** | The one-sentence statement of how the SQL writer understood the question. |
| **Model cascade** | A cheap model for easy roles, a strong model for hard ones. |
| **Prompt caching** | The provider reusing the processed prefix of a prompt (section 8.3). |

## A.4 Agents, tools and infrastructure
| Term | Meaning |
|---|---|
| **Agent vs chain** | A chain runs fixed steps; an agent chooses its next step from what just happened. |
| **LangGraph** | A library for agents as state machines (nodes, edges, shared state). |
| **Node / edge / conditional edge** | A step / a connection / a connection chosen by a function of the state. |
| **State / reducer** | The data passed between nodes / the rule for merging updates (e.g. append to a list). |
| **Checkpointing** | Saving state so a run can resume. |
| **Recursion limit** | A hard cap on graph steps; a backstop against infinite loops. |
| **Repair loop / execution-guided repair** | Feeding the real error or result back to the model to fix its query. |
| **Failure kind** | A category of failure (`unknown_column`, `syntax`, …) that selects the response. |
| **Loop detection** | Stopping when the same SQL is produced twice. |
| **MCP (Model Context Protocol)** | A standard for exposing tools to AI applications. |
| **MCP server / client / tool** | The process offering tools / the caller / one capability (`run_query`). |
| **stdio transport** | MCP over a subprocess's standard input and output. |
| **SSE (server-sent events)** | A stream of events from server to browser over HTTP. |
| **Trace** | The recorded step-by-step history of one request. |
| **Defence in depth** | Several independent safeguards, so one failing does not fail the system. |
| **Guardrail vs boundary** | A guardrail can be bypassed by the caller; a boundary cannot (the database role). |
| **Least privilege** | Each component gets only the access it needs. |
| **Read-only role** | A database role with only `SELECT`. |
| **TLS** | Encryption of the connection to the database. |
| **EXPLAIN / cost gate** | Asking the planner for a query's estimated cost and refusing expensive ones. |
| **Statement timeout** | A server-side limit on query duration. |
| **Idempotent** | Safe to repeat with the same result (a read). |
| **TTL** | Time to live: how long a cached entry is valid. |
| **Cache hit / miss / hit rate** | Served from cache / not found / hits divided by lookups. |
| **Cache poisoning** | A bad entry stored and then served repeatedly. |
| **Rate limit / backoff / pacer** | A provider cap on requests / waiting longer after each failure / spacing calls to stay under the cap. |
| **Quota (applied vs default)** | The limit actually set on your account vs the vendor's standard limit. |
| **Snapshot (data)** | A frozen copy of the data at a moment; ours is 2026-10-01 00:00 UTC. |
| **Synthetic data** | Invented data with realistic structure, containing no real records. |
