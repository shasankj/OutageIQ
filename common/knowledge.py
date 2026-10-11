"""Parse knowledge/outageiq_knowledge.md into sections with metadata.

A section starts at a '##' or '###' heading and runs to the next heading of either level.
Its metadata comes from an HTML comment on the line(s) after the heading:
    <!-- meta: type=table; tables=outages,tickets -->
Used by tests, scripts/check_knowledge_examples.py and (Phase 2) the indexer.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "outageiq_knowledge.md"
_HEADING = re.compile(r"^(#{2,3})\s+(.*)$")
_META = re.compile(r"<!--\s*meta:\s*(.*?)\s*-->", re.DOTALL)
_SQL_BLOCK = re.compile(r"```sql\n(.*?)```", re.DOTALL)


@dataclass
class Section:
    level: int
    heading: str
    parent: str  # heading of the enclosing '##' section ('' for a top-level one)
    body: str
    meta: dict = field(default_factory=dict)

    @property
    def sql_blocks(self) -> list[str]:
        return [b.strip() for b in _SQL_BLOCK.findall(self.body)]


def _parse_meta(text: str) -> dict:
    m = _META.search(text)
    if not m:
        return {}
    pairs = (p.split("=", 1) for p in m.group(1).split(";") if "=" in p)
    return {k.strip(): v.strip() for k, v in pairs}


def load_sections(path: Path = KNOWLEDGE_PATH) -> list[Section]:
    sections: list[Section] = []
    current_h2 = ""
    heading = None
    lines: list[str] = []

    def flush():
        if heading is not None:
            body = "\n".join(lines).strip()
            level, title = heading
            parent = "" if level == 2 else current_h2
            sections.append(Section(level, title, parent, body, _parse_meta(body)))

    for line in path.read_text().splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            lines = []
            heading = (len(m.group(1)), m.group(2).strip())
            if heading[0] == 2:
                current_h2 = heading[1]
        else:
            lines.append(line)
    flush()
    return sections
