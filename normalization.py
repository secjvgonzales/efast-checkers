import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import LABEL_MAPPING_PATH


def load_label_mapping(path: Path = LABEL_MAPPING_PATH) -> Dict[str, List[str]]:
    return json.loads(path.read_text())


def clean_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def normalize_label(raw_label: str, mapping: Optional[Dict[str, List[str]]] = None) -> str:
    mapping = mapping or load_label_mapping()
    cleaned = clean_label(raw_label)
    for normalized, labels in mapping.items():
        for label in labels:
            if clean_label(label) == cleaned or clean_label(label) in cleaned:
                return normalized
    return clean_label(raw_label).replace(" ", "_")


_SAFE_NUMERIC_PATTERN = re.compile(
    r"^\s*(?:"
    r"-?(?:[₱Pp]\s*)?(?:(?:\d+)|(?:\d{1,3}(?:,\d{3})+))(?:\.\d+)?"
    r"|"
    r"\(\s*(?:[₱Pp]\s*)?(?:(?:\d+)|(?:\d{1,3}(?:,\d{3})+))(?:\.\d+)?\s*\)"
    r")\s*$"
)


def validate_numeric_string(value: str) -> Tuple[bool, str]:
    """Return whether a recognized financial value is safe to normalize."""
    text = str(value or "").strip()
    if not text or not _SAFE_NUMERIC_PATTERN.fullmatch(text):
        return False, "Ambiguous numeric formatting detected."
    return True, ""


def parse_amount(displayed_value: str, unit_basis: str = "Pesos") -> Optional[float]:
    safe, _ = validate_numeric_string(displayed_value)
    if not safe:
        return None
    text = str(displayed_value).replace("₱", "").replace("P", "").replace("p", "").replace(",", "").strip()
    negative = "(" in text and ")" in text
    text = text.replace("(", "").replace(")", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    amount = float(match.group(0))
    if negative:
        amount = -amount
    basis = unit_basis.lower()
    if "thousand" in basis:
        amount *= 1000
    if "million" in basis:
        amount *= 1000000
    return amount


def detect_unit_basis(text: str) -> str:
    lowered = text.lower()
    if (
        re.search(r"\b(?:amounts?\s+)?in\s+millions?\b", lowered)
        or re.search(r"\bmillions?\s+philippine\s+pesos\b", lowered)
    ):
        return "Millions"
    if (
        re.search(r"\b(?:amounts?\s+)?in\s+thousands?\b", lowered)
        or re.search(r"\bthousands?\s+philippine\s+pesos\b", lowered)
    ):
        return "Thousands"
    return "Pesos"
