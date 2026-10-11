"""Vector retrieval over rag.chunks as outageiq_reader.

CLI:  python -m rag.retriever "Which outages are still open?" [k]
Prints the raw artifact: ranked chunks with cosine similarity.
"""
import sys
from dataclasses import dataclass

from common.db import connect
from common.embeddings import DIMS, embed_query, model_id
from rag.chunking import STRATEGY
from rag.indexer import vector_literal


@dataclass
class Hit:
    section: str
    doc_type: str
    tables: list[str]
    score: float  # cosine similarity: 1.0 identical direction, 0 unrelated
    content: str


def search(question: str, k: int = 5, doc_types: list[str] | None = None) -> list[Hit]:
    q = vector_literal(embed_query(question).vectors[0])
    sql = ("SELECT section, doc_type, tables, 1 - (embedding <=> %s::vector) AS score, content "
           "FROM rag.chunks WHERE strategy = %s AND embed_model = %s AND dims = %s "
           + ("AND doc_type = ANY(%s) " if doc_types else "")
           + "ORDER BY embedding <=> %s::vector LIMIT %s")
    params = [q, STRATEGY, model_id(), DIMS] + ([doc_types] if doc_types else []) + [q, k]
    with connect("reader") as conn:
        return [Hit(*row) for row in conn.execute(sql, params)]


def retrieve_context(question: str, tables_k: int = 4, structure_k: int = 2, examples_k: int = 3) -> list[Hit]:
    """Type-aware retrieval: a fixed budget per chunk role, so short example chunks cannot
    crowd out the table chunks the LLM cannot write correct SQL without.
    Order: always-on rules, tables, relationship/glossary, examples (each by similarity)."""
    q = vector_literal(embed_query(question).vectors[0])
    base = ("SELECT section, doc_type, tables, 1 - (embedding <=> %s::vector) AS score, content "
            "FROM rag.chunks WHERE strategy = %s AND embed_model = %s AND dims = %s AND doc_type = ANY(%s) "
            "ORDER BY embedding <=> %s::vector LIMIT %s")
    slots = [(["rules"], 100), (["table"], tables_k), (["relationship", "glossary"], structure_k),
             (["example"], examples_k)]
    hits: list[Hit] = []
    with connect("reader") as conn:
        for doc_types, n in slots:
            rows = conn.execute(base, [q, STRATEGY, model_id(), DIMS, doc_types, q, n]).fetchall()
            hits.extend(Hit(*row) for row in rows)
    return hits


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "Which outages are still open?"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"Q: {question}\n")
    for rank, h in enumerate(search(question, k), 1):
        print(f"{rank}. {h.score:.3f}  [{h.doc_type}] {h.section}  tables={h.tables}")
