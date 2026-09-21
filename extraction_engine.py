import re
from typing import Dict, List

from confidence import calculate_figure_confidence
from normalization import detect_unit_basis, normalize_label, parse_amount, validate_numeric_string

MANDATORY_LABELS = [
    "Total Assets",
    "Total Liabilities",
    "Total Equity",
    "Fund Balance",
    "Cash and Cash Equivalents",
    "Cash",
    "Revenues",
    "Revenue",
    "Gross Income",
    "Gross Revenue",
    "Gross Receipts",
    "Total Revenue",
    "Net Sales",
    "Net Income",
    "Net Loss",
    "Total Comprehensive Income",
    "Operating Cash Flow",
    "Net Cash Provided by Operating Activities",
]

LABEL_PATTERN = re.compile(
    r"(" + "|".join(re.escape(label) for label in sorted(MANDATORY_LABELS, key=len, reverse=True)) + r")",
    re.IGNORECASE,
)

FINANCIAL_POSITION_PAGE_TYPES = {
    "Statement of Financial Position / Balance Sheet",
    "Statement of Financial Position",
    "Balance Sheet",
}

SFP_ROW_LABELS = [
    "Total Assets",
    "Total Liabilities",
    "Total Equity",
    "Cash and Cash Equivalents",
    "Cash",
]

SFP_ROW_PATTERN = re.compile(
    r"^\s*(" + "|".join(re.escape(label) for label in sorted(SFP_ROW_LABELS, key=len, reverse=True)) + r")(?:\s*$|\s+(?=₱|P|-|\(|\d))",
    re.IGNORECASE,
)

CORE_SFP_NORMALIZED_LABELS = {
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash_and_cash_equivalents",
}

INCOME_PAGE_TYPES = {
    "Statement of Comprehensive Income",
    "Statement of Income / Receipts and Expenses",
    "Statement of Income",
    "Income Statement",
    "Statement of Operations",
}

INCOME_ROW_LABELS = [
    "Total Comprehensive Income",
    "Gross Income",
    "Net Income",
    "Net Loss",
    "Gross Revenue",
    "Total Revenue",
    "Revenues",
    "Revenue",
    "Net Sales",
]

INCOME_ROW_PATTERN = re.compile(
    r"^\s*(" + "|".join(re.escape(label) for label in sorted(INCOME_ROW_LABELS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

PRIMARY_SFP_HEADING_PATTERN = re.compile(
    r"\bstatements?\s+of\s+financial\s+position\b|\bbalance\s+sheet\b",
    re.IGNORECASE,
)

NOTES_HEADING_PATTERN = re.compile(
    r"\bnotes\s+to\s+(?:the\s+)?financial\s+statements\b",
    re.IGNORECASE,
)

AMOUNT_PATTERN = re.compile(
    r"(?:[₱Pp]\s*)?-?(?:(?:\d{1,3}(?:,\d{3})+)|(?:\d+))(?:\.\d+)?"
    r"|\(\s*(?:[₱Pp]\s*)?(?:(?:\d{1,3}(?:,\d{3})+)|(?:\d+))(?:\.\d+)?\s*\)"
)


def _page_text(page: Dict) -> str:
    return (
        page.get("extracted_text")
        or page.get("text")
        or page.get("original_text")
        or page.get("text_preview")
        or ""
    )


def _is_financial_position_page(page: Dict) -> bool:
    return str(page.get("page_type") or "") in FINANCIAL_POSITION_PAGE_TYPES


def _top_heading_region(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return "\n".join(lines[:8])[:700]


def _is_primary_financial_position_page(page: Dict, text: str) -> bool:
    if not _is_financial_position_page(page):
        return False
    heading = _top_heading_region(text)
    if NOTES_HEADING_PATTERN.search(heading):
        return False
    return bool(PRIMARY_SFP_HEADING_PATTERN.search(heading))


def _is_year_token(value: str, fiscal_years: List[int]) -> bool:
    text = str(value or "").strip().rstrip(".,;:")
    return bool(re.fullmatch(r"(?:19|20)\d{2}", text) and 1900 <= int(text) <= 2100)


def _source_authority(page: Dict) -> int:
    page_type = str(page.get("page_type") or "")
    if page_type in FINANCIAL_POSITION_PAGE_TYPES or page_type in INCOME_PAGE_TYPES or page_type == "Statement of Cash Flows" or "Changes in Equity" in page_type:
        return 3
    if "Notes" in page_type:
        return 2
    return 1


def _scope_penalty(text: str) -> bool:
    lowered = str(text or "").lower()
    patterns = [
        r"\bjoint\s+venture\b",
        r"\bassociates?\b",
        r"\bsegment\b",
        r"\bsummarized\s+financial\s+information\b",
        r"\bparent\s+company\s+only\b",
        r"\bnot\s+adjusted\s+for\s+the\s+percentage\s+ownership\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def page_scope(text: str) -> str:
    heading = " ".join(line.strip() for line in str(text or "").splitlines()[:8]).lower()
    heading = re.sub(r"\s+", " ", heading)
    if re.search(r"\bparent\s+company\s+statements?\b|\bseparate\s+financial\s+statements?\b|\bcompany[-\s]?only\b", heading):
        return "parent"
    if re.search(r"\bconsolidated\b|\band\s+subsidiaries\b", heading):
        return "consolidated"
    return "unspecified"


def _detected_year_headers(text: str, fiscal_years: List[int]) -> List[int]:
    requested = [int(year) for year in fiscal_years]
    if not requested:
        return []
    header_years = []
    for line in text.splitlines():
        if SFP_ROW_PATTERN.search(line):
            break
        for match in re.finditer(r"\b20\d{2}\b", line):
            year = int(match.group(0))
            if year in requested and year not in header_years:
                header_years.append(year)
        if len(header_years) >= len(requested):
            return header_years
    if header_years:
        return header_years
    for line in text.splitlines():
        matches = []
        for match in re.finditer(r"\b20\d{2}\b", line):
            year = int(match.group(0))
            if year in requested and year not in matches:
                matches.append(year)
        if len(matches) >= min(2, len(requested)):
            return matches
    for line in text.splitlines():
        matches = []
        for match in re.finditer(r"\b20\d{2}\b", line):
            year = int(match.group(0))
            if year in requested and year not in matches:
                matches.append(year)
        if matches:
            return matches
    return []


def _with_confidence(figure: Dict, page: Dict) -> Dict:
    computed = calculate_figure_confidence(figure, page)
    figure.update({
        "status": computed["initial_review_status"],
        "review_status": computed["initial_review_status"],
        "confidence": computed["score"] / 100,
        "computed_confidence_score": computed["score"],
        "confidence_classification": computed["classification"],
        "confidence_breakdown": computed["breakdown"],
    })
    return figure


def _clean_display_amount(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("("):
        return re.sub(r"^\(\s*[₱Pp]\s*", "(", text)
    return re.sub(r"^[₱Pp]\s*", "", text)


def _build_figure(page: Dict, text: str, unit_basis: str, raw_label: str, fiscal_year: int, displayed: str, source_start: int, source_end: int) -> Dict:
    displayed = _clean_display_amount(displayed)
    numeric_candidate = displayed.rstrip(".,;:")
    numeric_safe, numeric_note = validate_numeric_string(numeric_candidate)
    figure = {
        "page_number": page.get("page_number"),
        "statement_type": page.get("page_type", "Other / Unclassified"),
        "raw_label": raw_label,
        "normalized_label": normalize_label(raw_label),
        "fiscal_year": fiscal_year,
        "displayed_value": displayed,
        "normalized_peso_value": parse_amount(numeric_candidate, unit_basis) if numeric_safe else None,
        "unit_basis": unit_basis,
        "source_snippet": text[max(0, source_start - 45):source_end + 45],
        "review_note": numeric_note,
        "source_authority": _source_authority(page),
        "source_scope": page_scope(text),
        "scope_warning": _scope_penalty(text[max(0, source_start - 300):source_end + 300]),
        "_mandatory_labels": MANDATORY_LABELS,
    }
    return _with_confidence(figure, page)


def _extract_sfp_row_figures(page: Dict, fiscal_years: List[int], text: str, unit_basis: str) -> List[Dict]:
    if not _is_primary_financial_position_page(page, text):
        return []
    year_headers = _detected_year_headers(text, fiscal_years)
    if not year_headers:
        return []
    results = []
    lines = text.splitlines(keepends=True)
    row_matches = []
    line_start = 0
    for line in lines:
        line_text = line.rstrip("\r\n")
        label_match = SFP_ROW_PATTERN.search(line_text)
        if label_match:
            row_matches.append((line_start, line_start + label_match.start(), line_start + label_match.end(), label_match.group(1)))
        line_start += len(line)
    for index, (line_start, label_start, label_end, raw_label) in enumerate(row_matches):
        block_end = row_matches[index + 1][1] if index + 1 < len(row_matches) else len(text)
        value_region = text[label_end:block_end]
        amount_matches = []
        for amount_match in AMOUNT_PATTERN.finditer(value_region):
            displayed = amount_match.group(0).strip()
            numeric_safe, _ = validate_numeric_string(displayed.rstrip(".,;:"))
            if numeric_safe:
                amount_matches.append(amount_match)
        while len(amount_matches) > len(year_headers):
            leading = amount_matches[0].group(0).strip()
            if re.fullmatch(r"\d{1,2}", leading):
                amount_matches.pop(0)
            else:
                break
        for amount_index, amount_match in enumerate(amount_matches[:len(year_headers)]):
            displayed = amount_match.group(0).strip()
            fiscal_year = year_headers[amount_index]
            absolute_end = label_end + amount_match.end()
            results.append(_build_figure(
                page,
                text,
                unit_basis,
                raw_label,
                fiscal_year,
                displayed,
                label_start,
                absolute_end,
            ))
    return results


def _extract_income_row_figures(page: Dict, fiscal_years: List[int], text: str, unit_basis: str) -> List[Dict]:
    if str(page.get("page_type") or "") not in INCOME_PAGE_TYPES:
        return []
    year_headers = _detected_year_headers(text, fiscal_years)
    if not year_headers:
        return []
    results = []
    lines = text.splitlines(keepends=True)
    row_matches = []
    line_start = 0
    for line in lines:
        line_text = line.rstrip("\r\n")
        label_match = INCOME_ROW_PATTERN.search(line_text)
        if label_match:
            row_matches.append((line_start, line_start + label_match.start(), line_start + label_match.end(), label_match.group(1)))
        line_start += len(line)
    for index, (line_start, label_start, label_end, raw_label) in enumerate(row_matches):
        block_end = row_matches[index + 1][1] if index + 1 < len(row_matches) else len(text)
        value_region = text[label_end:block_end]
        amount_matches = []
        for amount_match in AMOUNT_PATTERN.finditer(value_region):
            displayed = amount_match.group(0).strip()
            numeric_safe, _ = validate_numeric_string(displayed.rstrip(".,;:"))
            if numeric_safe and not _is_year_token(displayed, fiscal_years):
                amount_matches.append(amount_match)
        while len(amount_matches) > len(year_headers):
            leading = amount_matches[0].group(0).strip().replace("₱", "")
            if re.fullmatch(r"\d{1,2}", leading):
                amount_matches.pop(0)
            else:
                break
        if len(amount_matches) < min(1, len(year_headers)):
            continue
        for amount_index, amount_match in enumerate(amount_matches[:len(year_headers)]):
            displayed = amount_match.group(0).strip()
            fiscal_year = year_headers[amount_index]
            absolute_end = label_end + amount_match.end()
            results.append(_build_figure(
                page,
                text,
                unit_basis,
                raw_label,
                fiscal_year,
                displayed,
                label_start,
                absolute_end,
            ))
    return results


def _extract_regex_figures(page: Dict, fiscal_years: List[int], text: str, unit_basis: str) -> List[Dict]:
    if str(page.get("page_type") or "") == "Other / Unclassified":
        return []
    results = []
    label_matches = list(LABEL_PATTERN.finditer(text))
    page_seen = set()
    for index, label_match in enumerate(label_matches):
        segment_end = label_matches[index + 1].start() if index + 1 < len(label_matches) else len(text)
        segment = text[label_match.end():segment_end][:300]
        label_context = text[max(0, label_match.start() - 40):label_match.end() + 80].lower()
        if re.search(r"\brevenue\s+regulations?\b|\baccounting\s+polic(?:y|ies)\b|\brecognized\s+as\b", label_context):
            continue
        normalized_label = normalize_label(label_match.group(1))
        if (
            str(page.get("page_type") or "") == "Notes to Financial Statements"
            and normalized_label in CORE_SFP_NORMALIZED_LABELS
        ):
            continue
        for year in fiscal_years:
            year_match = re.search(rf"\b{year}\b\s+([^\s]+)", segment)
            row_key = (normalized_label, int(year))
            if year_match and row_key not in page_seen:
                displayed = year_match.group(1)
                numeric_safe, _ = validate_numeric_string(displayed.rstrip(".,;:"))
                if not numeric_safe or _is_year_token(displayed, fiscal_years):
                    continue
                if _scope_penalty(segment):
                    continue
                page_seen.add(row_key)
                source_end = label_match.end() + year_match.end()
                results.append(_build_figure(
                    page,
                    text,
                    unit_basis,
                    label_match.group(1),
                    year,
                    displayed,
                    label_match.start(),
                    source_end,
                ))
    return results


def extract_figures_from_pages(pages: List[Dict], fiscal_years: List[int]) -> List[Dict]:
    results = []
    seen = set()
    for page in pages:
        text = _page_text(page)
        unit_basis = detect_unit_basis(text)
        for figure in _extract_sfp_row_figures(page, fiscal_years, text, unit_basis):
            key = (figure.get("page_number"), figure.get("normalized_label"), int(figure.get("fiscal_year")))
            seen.add(key)
            results.append(figure)
        for figure in _extract_income_row_figures(page, fiscal_years, text, unit_basis):
            key = (figure.get("page_number"), figure.get("normalized_label"), int(figure.get("fiscal_year")))
            if key not in seen:
                seen.add(key)
                results.append(figure)
        for figure in _extract_regex_figures(page, fiscal_years, text, unit_basis):
            key = (figure.get("page_number"), figure.get("normalized_label"), int(figure.get("fiscal_year")))
            if key not in seen:
                seen.add(key)
                results.append(figure)
    return results


NON_ADDITIVE_HEADLINE_LABELS = {
    "revenue",
    "gross_revenue",
    "total_revenue",
    "net_sales",
    "gross_income",
    "net_income",
    "net_loss",
    "total_comprehensive_income",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash_and_cash_equivalents",
}


def figure_preference_key(figure: Dict) -> tuple:
    authority = int(figure.get("source_authority") or 0)
    if not authority:
        statement_type = str(figure.get("statement_type") or "")
        if statement_type in FINANCIAL_POSITION_PAGE_TYPES or statement_type in INCOME_PAGE_TYPES or statement_type == "Statement of Cash Flows" or "Changes in Equity" in statement_type:
            authority = 3
        elif "Notes" in statement_type:
            authority = 2
        else:
            authority = 1
    scope_ok = 0 if figure.get("scope_warning") else 1
    source_scope = str(figure.get("source_scope") or "unspecified")
    scope_rank = {"consolidated": 3, "unspecified": 2, "parent": 1}.get(source_scope, 2)
    confidence = float(figure.get("computed_confidence_score") or figure.get("confidence") or 0)
    value_present = 1 if figure.get("normalized_peso_value") is not None else 0
    page_number = int(figure.get("page_number") or 999999)
    return (scope_rank, authority, scope_ok, value_present, confidence, -page_number)


def select_preferred_figures(figures: List[Dict]) -> List[Dict]:
    preferred = {}
    passthrough = []
    for figure in figures:
        normalized_label = str(figure.get("normalized_label") or "")
        fiscal_year = figure.get("fiscal_year")
        if normalized_label not in NON_ADDITIVE_HEADLINE_LABELS or fiscal_year is None:
            passthrough.append(figure)
            continue
        key = (normalized_label, int(fiscal_year))
        existing = preferred.get(key)
        if existing is None or figure_preference_key(figure) > figure_preference_key(existing):
            preferred[key] = figure
    return sorted([*preferred.values(), *passthrough], key=lambda item: (int(item.get("page_number") or 0), str(item.get("normalized_label") or ""), -int(item.get("fiscal_year") or 0)))


def fiscal_year_candidates(metadata: Dict) -> List[int]:
    years = []
    current = metadata.get("period_covered_year")
    if current:
        years.append(int(current))
    comparative = metadata.get("comparative_years", "")
    if isinstance(comparative, list):
        years.extend(int(year) for year in comparative)
    else:
        years.extend(int(year) for year in re.findall(r"20\d{2}", str(comparative)))
    return sorted(set(years), reverse=True)
