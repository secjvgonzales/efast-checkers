import re
from typing import Dict, Optional

from normalization import clean_label, load_label_mapping, parse_amount, validate_numeric_string
from pdf_utils import quality_flag


CONFIDENCE_WEIGHTS = {
    "Page Quality": 20,
    "Label Match": 25,
    "Fiscal Year": 20,
    "Numeric Parse": 20,
    "Unit Basis": 10,
    "Source Evidence": 5,
}

INITIAL_REVIEW_STATUSES = {
    "High": "Ready for Quick Validation",
    "Medium": "Needs Review",
    "Low": "Check Source",
}

EXACT_SUPPORTED_LABELS = {
    "Total Assets",
    "Total Liabilities",
    "Total Equity",
    "Fund Balance",
    "Cash and Cash Equivalents",
    "Revenue",
    "Gross Revenue",
    "Gross Receipts",
    "Total Revenue",
    "Net Sales",
    "Net Income",
    "Net Loss",
    "Operating Cash Flow",
    "Net Cash Provided by Operating Activities",
}


def _page_quality_points(figure: Dict, page: Optional[Dict]) -> int:
    if not page:
        return 0
    text = str(
        page.get("extracted_text")
        or page.get("text")
        or page.get("original_text")
        or page.get("text_preview")
        or ""
    ).strip()
    if not text and not page.get("text_length"):
        return 0
    flag = str(page.get("image_quality_flag") or quality_flag(text))
    try:
        text_length = int(page.get("text_length") or len(text))
    except (TypeError, ValueError):
        text_length = len(text)
    if flag == "Passed" and text_length >= 140:
        return 20
    if flag == "Warning" or text_length >= 25:
        return 12
    return 5


def _label_match_points(figure: Dict) -> int:
    raw_label = str(figure.get("raw_label") or "").strip()
    normalized_label = str(figure.get("normalized_label") or "").strip()
    if not raw_label or not normalized_label:
        return 0

    mapping = load_label_mapping()
    raw_clean = clean_label(raw_label)
    exact_supported = {
        clean_label(label)
        for labels in mapping.values()
        for label in labels
    }
    mandatory_labels = {
        clean_label(label)
        for label in (figure.get("_mandatory_labels") or EXACT_SUPPORTED_LABELS)
    }
    if raw_clean in mandatory_labels and normalized_label:
        return 25
    if raw_clean in exact_supported:
        return 20

    mapped_aliases = [
        clean_label(label)
        for labels in mapping.values()
        for label in labels
    ]
    if any(alias in raw_clean or raw_clean in alias for alias in mapped_aliases):
        return 12
    return 0


def _fiscal_year_points(figure: Dict) -> int:
    year = figure.get("fiscal_year")
    snippet = str(figure.get("source_snippet") or "")
    if not year:
        return 0
    if re.search(rf"\b{int(year)}\b\s+\S+", snippet):
        return 20
    if re.search(rf"\b{int(year)}\b", snippet):
        return 12
    return 5


def _numeric_parse_points(figure: Dict) -> int:
    displayed = str(figure.get("displayed_value") or "").strip()
    if not displayed:
        return 0
    safe_display, _ = validate_numeric_string(displayed)
    if safe_display and figure.get("normalized_peso_value") is not None:
        return 20

    cleaned = displayed.rstrip(".,;:")
    safe_cleaned, _ = validate_numeric_string(cleaned)
    if safe_cleaned and parse_amount(cleaned, str(figure.get("unit_basis") or "Pesos")) is not None:
        return 15
    return 0


def _displayed_value_is_year_token(figure: Dict) -> bool:
    displayed = str(figure.get("displayed_value") or "").strip().replace("₱", "").replace("P", "").replace("p", "").replace(",", "").strip(" .;:")
    if not re.fullmatch(r"(?:19|20)\d{2}", displayed):
        return False
    year = figure.get("fiscal_year")
    if year and int(displayed) == int(year):
        return True
    return 1900 <= int(displayed) <= 2100


def _source_authority_points(figure: Dict) -> int:
    authority = int(figure.get("source_authority") or 0)
    statement_type = str(figure.get("statement_type") or "")
    if authority >= 3 or statement_type in {
        "Statement of Financial Position / Balance Sheet",
        "Statement of Financial Position",
        "Balance Sheet",
        "Statement of Comprehensive Income",
        "Statement of Income / Receipts and Expenses",
        "Statement of Income",
        "Income Statement",
        "Statement of Operations",
    }:
        return 5
    if authority == 2 or "Notes" in statement_type:
        return 2
    return 0


def _unit_basis_points(figure: Dict, page: Optional[Dict]) -> int:
    unit_basis = str(figure.get("unit_basis") or "").strip()
    if not unit_basis:
        return 0
    page_text = " ".join(
        str(value or "")
        for value in (
            (page or {}).get("text"),
            (page or {}).get("extracted_text"),
            (page or {}).get("original_text"),
            (page or {}).get("text_preview"),
            figure.get("source_snippet"),
        )
    ).lower()
    explicit_unit = re.search(
        r"\b(?:amounts?\s+in|in)\s+(?:philippine\s+)?"
        r"(?:pesos?|thousands?|millions?|billions?)\b",
        page_text,
    )
    if explicit_unit:
        return 10
    return 3


def _source_evidence_points(figure: Dict) -> int:
    snippet = str(figure.get("source_snippet") or "").strip()
    if not snippet:
        return 0
    raw_label = str(figure.get("raw_label") or "").strip().lower()
    year = str(figure.get("fiscal_year") or "")
    value = str(figure.get("displayed_value") or "").strip()
    if raw_label and raw_label in snippet.lower() and year and year in snippet and value and value in snippet:
        return 5
    return 2


def _classification(score: int) -> str:
    if score >= 90:
        return "High"
    if score >= 75:
        return "Medium"
    return "Low"


def calculate_figure_confidence(figure: Dict, page: Optional[Dict] = None) -> Dict:
    """
    Calculate explainable confidence for one extracted figure.

    The stored prototype confidence field remains a 0–1 compatibility value;
    this helper returns the reviewer-facing score as 0–100.
    """
    evidence = {
        "Page Quality": _page_quality_points(figure, page),
        "Label Match": _label_match_points(figure),
        "Fiscal Year": _fiscal_year_points(figure),
        "Numeric Parse": _numeric_parse_points(figure),
        "Unit Basis": _unit_basis_points(figure, page),
        "Source Evidence": _source_evidence_points(figure) + _source_authority_points(figure),
    }
    raw_score = sum(evidence.values())
    caps = []
    numeric_parse = evidence["Numeric Parse"]
    if numeric_parse == 0:
        raw_score = min(raw_score, 49)
        caps.append("Suspicious or unsafe numeric formatting")
    if evidence["Page Quality"] <= 5:
        raw_score = min(raw_score, 69)
        caps.append("Failed or very poor source-page readability")
    if _displayed_value_is_year_token(figure):
        raw_score = min(raw_score, 49)
        caps.append("Displayed value looks like a fiscal-year header, not a monetary amount")
    if figure.get("scope_warning"):
        raw_score = min(raw_score, 59)
        caps.append("Source context appears scoped to a joint venture, segment, subsidiary, or other non-headline disclosure")
    if int(figure.get("source_authority") or 0) <= 1 and str(figure.get("statement_type") or "") == "Other / Unclassified":
        raw_score = min(raw_score, 74)
        caps.append("Low-authority or unclassified source page")

    score = max(0, min(100, int(raw_score)))
    classification = _classification(score)
    review_status = INITIAL_REVIEW_STATUSES[classification]
    if numeric_parse == 0 or _displayed_value_is_year_token(figure):
        review_status = "Check Source"

    return {
        "score": score,
        "classification": classification,
        "initial_review_status": review_status,
        "breakdown": evidence,
        "raw_score": sum(evidence.values()),
        "caps": caps,
    }
