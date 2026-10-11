from agent.validator import validate
from evals.golden import load_golden
from rag.chunking import build_chunks

BEHAVIORS = {"answer", "not_found", "clarify", "refuse"}
KNOWN_SECTIONS = {c.section for c in build_chunks()}


def test_ids_unique_and_count():
    qs = load_golden()
    assert len(qs) == 30 and len({q["id"] for q in qs}) == 30


def test_fields_and_labels_are_valid():
    for q in load_golden():
        assert q["behavior"] in BEHAVIORS and q["difficulty"] in {"easy", "medium", "hard"}, q["id"]
        assert any(g == 2 for g in q["relevant"].values()), q["id"]
        for section, grade in q["relevant"].items():
            assert section in KNOWN_SECTIONS, f"{q['id']}: unknown section {section!r}"
            assert grade in (1, 2)


def test_golden_sql_passes_the_validator():
    for q in load_golden():
        if q["golden_sql"] is not None:
            r = validate(q["golden_sql"])
            assert r.ok, f"{q['id']}: {r.errors}"
        else:
            assert q["behavior"] in {"clarify", "refuse"}, q["id"]


def test_golden_questions_are_held_out_from_the_knowledge_examples():
    from common.knowledge import load_sections
    examples = " ".join(s.body.lower() for s in load_sections() if s.meta.get("type") == "example")
    for q in load_golden():
        assert q["question"].lower().rstrip("?.") not in examples, f"{q['id']} leaks into the examples"
