from rag.chunking import STRATEGY, build_chunks
from common.knowledge import load_sections


def test_one_chunk_per_typed_section():
    typed = [s for s in load_sections() if s.meta.get("type")]
    assert len(build_chunks()) == len(typed)


def test_chunks_have_context_header_and_no_meta_comment():
    for c in build_chunks():
        assert c.content.startswith("[OutageIQ knowledge |"), c.section
        assert "<!--" not in c.content, c.section
        assert c.strategy == STRATEGY


def test_table_chunks_carry_their_table_names():
    by_section = {c.section: c for c in build_chunks()}
    assert by_section["Table ops.outages"].tables == ["outages"]
    assert "tickets" in by_section["Table ops.ticket_assignments"].tables


def test_hash_is_stable_and_unique():
    chunks = build_chunks()
    assert [c.content_hash for c in chunks] == [c.content_hash for c in build_chunks()]
    assert len({c.content_hash for c in chunks}) == len(chunks)


def test_every_chunk_is_well_under_the_embedding_limit():
    assert max(len(c.content) for c in build_chunks()) < 10_000  # limit is 50,000 chars
