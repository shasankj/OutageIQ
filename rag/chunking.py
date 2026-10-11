"""Entity-based chunking with contextual headers (strategy 'entity_v1').

One chunk per knowledge-file section (a table, a join-path block, a glossary block, one example,
the rules...). The header says where the chunk came from, so a chunk about 'priority' is still
anchored to its table when embedded on its own.
"""
import hashlib
import re
from dataclasses import dataclass

from common.knowledge import load_sections

STRATEGY = "entity_v1"
SOURCE = "knowledge/outageiq_knowledge.md"
_META_COMMENT = re.compile(r"<!--\s*meta:.*?-->\s*", re.DOTALL)


@dataclass
class Chunk:
    strategy: str
    source: str
    section: str
    doc_type: str
    tables: list[str]
    schema_version: int
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def build_chunks() -> list[Chunk]:
    chunks = []
    for s in load_sections():
        if not s.meta.get("type"):
            continue  # container headings such as "3. Tables"
        body = _META_COMMENT.sub("", s.body).strip()
        where = f"{s.parent} > {s.heading}" if s.parent else s.heading
        content = f"[OutageIQ knowledge | {where} | type: {s.meta['type']}]\n# {s.heading}\n\n{body}"
        chunks.append(Chunk(
            strategy=STRATEGY, source=SOURCE, section=s.heading, doc_type=s.meta["type"],
            tables=[t for t in s.meta.get("tables", "").split(",") if t],
            schema_version=int(s.meta.get("version", "1")), content=content))
    return chunks
