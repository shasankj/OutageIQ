"""Load and sanity-check the golden dataset."""
from pathlib import Path

import yaml

GOLDEN_PATH = Path(__file__).resolve().parent / "golden.yaml"


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())
