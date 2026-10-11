"""Embed the knowledge chunks and store them in rag.chunks as outageiq_indexer.

Run: python -m rag.indexer          (re-runnable: chunks already embedded are skipped by hash)
"""
from common.db import connect
from common.embeddings import DIMS, embed_documents, model_id, price_per_million
from rag.chunking import build_chunks


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


def main() -> int:
    chunks = build_chunks()
    new_tokens = 0
    with connect("indexer") as conn:
        existing = {h for (h,) in conn.execute(
            "SELECT content_hash FROM rag.chunks WHERE strategy = %s AND embed_model = %s AND dims = %s",
            (chunks[0].strategy, model_id(), DIMS))}
        print(f"{'section':<46} {'type':<13} {'chars':>6} {'tokens':>6}  status")
        for c in chunks:
            if c.content_hash in existing:
                print(f"{c.section[:45]:<46} {c.doc_type:<13} {len(c.content):>6} {'':>6}  cached")
                continue
            e = embed_documents([c.content])
            new_tokens += e.tokens
            conn.execute(
                "INSERT INTO rag.chunks (strategy, source, section, doc_type, tables, schema_version, content,"
                " content_hash, embed_model, dims, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                (c.strategy, c.source, c.section, c.doc_type, c.tables, c.schema_version, c.content,
                 c.content_hash, model_id(), DIMS, vector_literal(e.vectors[0])))
            conn.commit()
            print(f"{c.section[:45]:<46} {c.doc_type:<13} {len(c.content):>6} {e.tokens:>6}  embedded")
        # Remove chunks whose content no longer exists in the knowledge file (an edited section would
        # otherwise leave its old version behind and the retriever would serve both).
        pruned = conn.execute(
            "DELETE FROM rag.chunks WHERE strategy = %s AND embed_model = %s AND dims = %s "
            "AND content_hash <> ALL(%s) RETURNING section",
            (chunks[0].strategy, model_id(), DIMS, [c.content_hash for c in chunks])).fetchall()
        conn.commit()
        for (section,) in pruned:
            print(f"{section[:45]:<46} {'':<13} {'':>6} {'':>6}  pruned (superseded)")
        (total,) = conn.execute("SELECT count(*) FROM rag.chunks").fetchone()
    cost = new_tokens * price_per_million() / 1_000_000
    print(f"\n{len(chunks)} chunks; {new_tokens} new tokens embedded, cost ${cost:.6f} "
          f"list price (Voyage free tier covers 200M tokens); rag.chunks now has {total} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
