import re
from typing import Dict, List, Optional, Tuple

from normalization import parse_amount, validate_numeric_string
from pdf_utils import quality_flag
from validation_engine import classify_gis_page, fuzzy_company_match


PROFILE_PAGE_TYPES = {"Corporate / Profile / Meeting Information"}
CAPITAL_PAGE_TYPES = {"Capital Structure"}
PEOPLE_PAGE_TYPES = {"Directors / Officers"}
STOCKHOLDER_PAGE_TYPES = {"Stockholders' Information"}
CERTIFICATION_PAGE_TYPES = {"Corporate Secretary Attestation / Notarization"}

GIS_HEADING_YEAR_PATTERNS = [
    r"\b(?:amended\s+)?general\s+information\s+sheet\b(?:\s*\(\s*gis\s*\))?[\s\S]{0,80}?\bfor\s*(?:the\s*)?year\s*[:\-]?\s*(20\d{2})\b",
    r"\bgis\s+(?:for\s+)?(?:the\s+)?year\s*[:\-]?\s*(20\d{2})\b",
]
GIS_LABEL_YEAR_PATTERNS = [
    r"\b(?:amended\s+gis\s+year|gis\s+year|reporting\s+year|for\s+the\s+year)\b\s*[:\-]?\s*(20\d{2})\b",
]
DATE_PATTERN = (
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{4}|"
    r"\d{1,2}-[A-Za-z]{3}-\d{2,4}|"
    r"\d{4}-\d{1,2}-\d{1,2}|"
    r"[A-Za-z]+\s+\d{1,2}"
)
AMOUNT_PATTERN = re.compile(
    r"(?:[₱Pp]\s*)?(?:(?:\d{1,3}(?:,\d{3})+)|(?:\d+))(?:\.\d+)?"
    r"|\(\s*(?:[₱Pp]\s*)?(?:(?:\d{1,3}(?:,\d{3})+)|(?:\d+))(?:\.\d+)?\s*\)"
)

TIN_PATTERN = re.compile(r"\bTIN\b|\btax\s+identification\b", re.I)
PHONE_PATTERN = re.compile(r"\b(?:mobile|cellphone|telephone|tel\.?\s*no\.?|phone)\b", re.I)
RESIDENTIAL_PATTERN = re.compile(r"\b(?:residential|home)\s+address\b", re.I)


def _page_text(page: Dict) -> str:
    return str(
        page.get("extracted_text")
        or page.get("text")
        or page.get("original_text")
        or page.get("text_preview")
        or ""
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _page_type(page: Dict) -> str:
    return str(page.get("page_type") or classify_gis_page(_page_text(page)))


def _pages_by_type(pages: List[Dict], page_types: set) -> List[Dict]:
    return [page for page in pages if _page_type(page) in page_types]


def _candidate_pages(pages: List[Dict], page_types: set, fallback_terms: List[str]) -> List[Dict]:
    selected = _pages_by_type(pages, page_types)
    if selected:
        return selected
    patterns = [re.compile(term, re.I) for term in fallback_terms]
    return [page for page in pages if any(pattern.search(_page_text(page)) for pattern in patterns)]


def _evidence(text: str, start: int, end: int, max_chars: int = 220) -> str:
    source = _clean_text(text)
    if not source:
        return ""
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    compact_before = _clean_text(text[:start])
    compact_match = _clean_text(text[start:end])
    compact_after = _clean_text(text[end:])
    snippet = _clean_text(" ".join([compact_before[-70:], compact_match, compact_after[:110]]))
    return snippet[:max_chars].strip()


def _line_evidence(line: str) -> str:
    return _clean_text(line)[:240]


def _confidence(page: Dict, strength: int, complete: bool = True, numeric_safe: Optional[bool] = None) -> Tuple[int, str, str]:
    text = _page_text(page)
    flag = str(page.get("image_quality_flag") or quality_flag(text))
    score = strength
    if flag == "Passed" and len(text.strip()) >= 140:
        score += 20
    elif flag == "Warning" or len(text.strip()) >= 25:
        score += 10
    else:
        score -= 15
    if not complete:
        score -= 20
    if numeric_safe is False:
        score = min(score, 68)
    score = max(20, min(98, score))
    if score >= 85:
        return score, "High", "Ready for Quick Validation"
    if score >= 65:
        return score, "Medium", "Needs Review"
    return score, "Low", "Check Source"


def _item(
    category: str,
    field_name: str,
    display_label: str,
    value_text: str,
    page: Dict,
    evidence: str,
    strength: int = 55,
    normalized_value=None,
    complete: bool = True,
    numeric_safe: Optional[bool] = None,
    metadata: Optional[Dict] = None,
) -> Dict:
    score, label, status = _confidence(page, strength, complete, numeric_safe)
    return {
        "category": category,
        "field_name": field_name,
        "display_label": display_label,
        "value_text": _clean_text(value_text),
        "normalized_value": "" if normalized_value is None else str(normalized_value),
        "source_page": page.get("page_number"),
        "evidence": evidence,
        "confidence_score": score,
        "confidence_label": label,
        "review_status": status,
        "metadata_json": metadata or {},
    }


def _label_value(text: str, labels: List[str], value_pattern: str = r"([^\n\r]{2,160})") -> Optional[Tuple[str, str, int, int]]:
    label_pattern = r"(?:" + "|".join(labels) + r")"
    pattern = re.compile(label_pattern + r"\s*[:\-]?\s*" + value_pattern, re.I)
    for match in pattern.finditer(text):
        value = _clean_text(match.group(1)).strip(" .,:;-")
        if value and not _is_sensitive_label(match.group(0)):
            return value, match.group(0), match.start(), match.end()
    return None


def _is_sensitive_label(text: str) -> bool:
    return bool(TIN_PATTERN.search(text) or PHONE_PATTERN.search(text) or RESIDENTIAL_PATTERN.search(text))


def _normalize_sec(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _extract_sec_registration(text: str) -> Optional[Tuple[str, int, int]]:
    label = re.compile(
        r"\b(?:i?sec)\s+(?:registration|file)\s+(?:number|no\.?)\b\s*[:\-]?",
        re.I,
    )
    for match in label.finditer(text):
        region = text[match.end():match.end() + 80]
        token = re.search(r"\b(?:[A-Za-z]{1,5}\s*-\s*|[A-Za-z]{1,5}(?=\d))?\d{1,12}(?:[- ]?[A-Za-z]*\d+[A-Za-z]*)?\b", region)
        if not token:
            continue
        value = _clean_text(token.group(0)).strip(" .,:;-")
        normalized = _normalize_sec(value)
        if len(normalized) >= 3 and any(character.isdigit() for character in normalized):
            start = match.end() + token.start()
            return value, start, match.end() + token.end()
    return None


def _normalize_company(value: str) -> str:
    value = str(value or "").lower()
    value = value.replace("corporation", "corp").replace("corp.", "corp")
    value = value.replace("incorporated", "inc").replace("inc.", "inc")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def detect_gis_reporting_year(pages: List[Dict]) -> Optional[Dict]:
    profile_pages = _candidate_pages(pages, PROFILE_PAGE_TYPES, [r"general\s+information\s+sheet", r"gis\s+for\s+the\s+year"])
    for page in profile_pages:
        text = _page_text(page)
        for pattern in GIS_HEADING_YEAR_PATTERNS:
            match = re.search(pattern, text, re.I)
            if match:
                return _item(
                    "profile",
                    "gis_reporting_year",
                    "GIS Year",
                    match.group(1),
                    page,
                    _evidence(text, match.start(), match.end()),
                    strength=75,
                    normalized_value=match.group(1),
                )
    for page in profile_pages:
        text = _page_text(page)
        for pattern in GIS_LABEL_YEAR_PATTERNS:
            match = re.search(pattern, text, re.I)
            if match:
                return _item(
                    "profile",
                    "gis_reporting_year",
                    "GIS Year",
                    match.group(1),
                    page,
                    _evidence(text, match.start(), match.end()),
                    strength=68,
                    normalized_value=match.group(1),
                )
    return None


def extract_document_identification(pages: List[Dict]) -> List[Dict]:
    for page in pages:
        text = _page_text(page)
        match = re.search(r"\b(?:amended\s+)?general\s+information\s+sheet\b|\bgis\s+for\s+the\s+year\b", text, re.I)
        if match:
            evidence = _evidence(text, match.start(), match.end())
            is_amended = bool(re.search(r"\bamended\b|\bamendment\b", text[: max(match.end() + 500, 500)], re.I))
            return [
                _item("profile", "document_type", "Document Type", "Amended GIS" if is_amended else "GIS", page, evidence, strength=78),
                _item("profile", "is_amended", "Amended GIS", "Yes" if is_amended else "No", page, evidence, strength=72, normalized_value=str(is_amended).lower()),
            ]
    if pages:
        return [_item("profile", "document_type", "Document Type", "Insufficient Evidence", pages[0], "No strong GIS heading was detected.", strength=35, complete=False)]
    return []


def extract_profile(pages: List[Dict]) -> List[Dict]:
    items = extract_document_identification(pages)
    profile_pages = _candidate_pages(pages, PROFILE_PAGE_TYPES, [r"general\s+information\s+sheet", r"corporate\s+name", r"sec\s+(?:registration|file)"])
    year_item = detect_gis_reporting_year(pages)
    if year_item:
        items.append(year_item)
    field_specs = [
        ("company_name", "Company Name", [r"corporate\s+name", r"name\s+of\s+corporation"], r"([^\n\r]{3,140})", 72),
        ("sec_registration_no", "SEC Registration Number", [r"sec\s+(?:registration|file)\s+(?:no\.?|number)", r"registration\s+number"], r"([A-Z0-9\- ]{3,40})", 72),
        ("fiscal_year_end", "Fiscal Year End", [r"fiscal\s+year\s+end", r"fiscal\s+year"], r"(" + DATE_PATTERN + r"|[A-Za-z]+\s+\d{1,2})", 62),
        ("actual_annual_meeting_date", "Actual Annual Meeting Date", [r"actual\s+date\s+of\s+annual\s+meeting", r"date\s+of\s+actual\s+meeting"], r"(" + DATE_PATTERN + r")", 68),
        ("corporation_type", "Corporation Type", [r"corporation\s+type", r"type\s+of\s+corporation"], r"([^\n\r]{2,60})", 55),
        ("principal_office_address", "Principal Office Address", [r"principal\s+office(?:\s+address)?"], r"([^\n\r]{5,180})", 50),
        ("business_address", "Business Address", [r"business\s+address"], r"([^\n\r]{5,180})", 50),
        ("official_email", "Official Email", [r"official\s+email(?:\s+address)?", r"email\s+address"], r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", 60),
        ("external_auditor", "External Auditor", [r"external\s+auditor", r"independent\s+auditor"], r"([^\n\r]{3,120})", 50),
    ]
    seen = {(item["category"], item["field_name"]) for item in items}
    for page in profile_pages:
        text = _page_text(page)
        found = _extract_sec_registration(text)
        if not found:
            continue
        value, start, end = found
        items.append(_item(
            "profile", "sec_registration_no", "SEC Registration Number", value, page,
            _evidence(text, start, end), strength=72, normalized_value=_normalize_sec(value),
        ))
        seen.add(("profile", "sec_registration_no"))
        break
    for field_name, label, labels, value_pattern, strength in field_specs:
        if ("profile", field_name) in seen:
            continue
        for page in profile_pages:
            text = _page_text(page)
            found = _label_value(text, labels, value_pattern)
            if not found:
                continue
            value, raw, start, end = found
            if field_name in {"principal_office_address", "business_address"} and RESIDENTIAL_PATTERN.search(raw):
                continue
            if field_name == "company_name" and not re.search(r"\b(?:corporation|company|corp\.?|inc\.?|ltd\.?)\b", value, re.I):
                continue
            normalized = _normalize_sec(value) if field_name == "sec_registration_no" else None
            items.append(_item("profile", field_name, label, value, page, _evidence(text, start, end), strength=strength, normalized_value=normalized))
            seen.add(("profile", field_name))
            break
    return items


def _extract_amount_after_label(text: str, labels: List[str]) -> Optional[Tuple[str, int, int, bool, Optional[float]]]:
    label_pattern = r"(?:" + "|".join(labels) + r")"
    pattern = re.compile(label_pattern + r"[^\n\r]{0,90}?((?:[₱Pp]\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\([^\)]*\d[\d,]*(?:\.\d+)?\))", re.I)
    candidates = [match for match in pattern.finditer(text) if text[match.end():match.end() + 1] not in {",", "."}]
    if not candidates:
        return None
    total_candidates = [m for m in candidates if re.search(r"\btotal\b", text[max(0, m.start() - 80):m.end()], re.I)]
    match = total_candidates[0] if total_candidates else candidates[0]
    displayed = match.group(1).strip()
    safe, _ = validate_numeric_string(displayed)
    return displayed, match.start(), match.end(), safe, parse_amount(displayed, "Pesos") if safe else None


def extract_capital(pages: List[Dict]) -> List[Dict]:
    items = []
    capital_pages = _candidate_pages(pages, CAPITAL_PAGE_TYPES, [r"capital\s+structure", r"authorized\s+capital", r"paid[-\s]?up\s+capital"])
    specs = [
        ("authorized_capital", "Authorized Capital Stock", [r"authorized\s+capital\s+stock", r"authorized\s+capital"]),
        ("subscribed_capital", "Subscribed Capital", [r"subscribed\s+capital\s+stock", r"subscribed\s+capital"]),
        ("paid_up_capital", "Paid-Up Capital", [r"paid[-\s]?up\s+capital"]),
    ]
    for field_name, label, labels in specs:
        for page in capital_pages:
            text = _page_text(page)
            found = _extract_amount_after_label(text, labels)
            if not found:
                continue
            value, start, end, safe, normalized = found
            items.append(_item("capital", field_name, label, value, page, _evidence(text, start, end), strength=66, normalized_value=normalized, numeric_safe=safe))
            break
    percent_specs = [
        ("filipino_ownership_percent", "Filipino Ownership %", [r"filipino\s+(?:ownership|equity)"]),
        ("foreign_ownership_percent", "Foreign Ownership %", [r"foreign\s+(?:ownership|equity)"]),
    ]
    for field_name, label, labels in percent_specs:
        for page in capital_pages:
            text = _page_text(page)
            pattern = re.compile(r"(?:" + "|".join(labels) + r")[^\n\r]{0,80}?(\d{1,3}(?:\.\d+)?\s*%)", re.I)
            match = pattern.search(text)
            if match:
                items.append(_item("capital", field_name, label, match.group(1), page, _evidence(text, match.start(), match.end()), strength=58, normalized_value=match.group(1).replace("%", "").strip()))
                break
    for page in capital_pages:
        text = _page_text(page)
        match = re.search(r"\btotal\s+(?:outstanding|subscribed)\s+shares?\b[^\n\r]{0,90}?([\d,]+)", text, re.I)
        if match:
            items.append(_item("capital", "total_subscribed_or_outstanding_shares", "Total Subscribed/Outstanding Shares", match.group(1), page, _evidence(text, match.start(), match.end()), strength=56, normalized_value=match.group(1).replace(",", "")))
            break
    return items


def _looks_like_person_or_entity(name: str) -> bool:
    cleaned = _clean_text(name)
    if len(cleaned) < 4 or len(cleaned) > 120:
        return False
    if re.search(r"\b(?:name|nationality|gender|director|officer|stockholder|tin)\b", cleaned, re.I):
        return False
    return bool(re.search(r"[A-Za-z]{2,}", cleaned))


def _split_table_line(line: str) -> List[str]:
    if "|" in line:
        parts = line.split("|")
    elif "\t" in line:
        parts = line.split("\t")
    else:
        parts = re.split(r"\s{2,}", line)
    return [_clean_text(part) for part in parts if _clean_text(part)]


def extract_people(pages: List[Dict], limit: int = 80) -> List[Dict]:
    items = []
    people_pages = _candidate_pages(pages, PEOPLE_PAGE_TYPES, [r"directors?\s+(?:and|/)\s+officers?", r"officer\s+position"])
    row_number = 0
    for page in people_pages:
        for line in _page_text(page).splitlines():
            if TIN_PATTERN.search(line) and not re.search(r"\b(?:director|officer|chair|president|treasurer|secretary)\b", line, re.I):
                continue
            sanitized_line = re.sub(r"\bTIN\b\s*[:#\-]?\s*[A-Za-z0-9\- ]+", "", line, flags=re.I)
            parts = _split_table_line(sanitized_line)
            if len(parts) < 2:
                continue
            name = parts[0].strip("0123456789. )(")
            if not _looks_like_person_or_entity(name):
                continue
            joined = " ".join(parts[1:])
            nationality = next((part for part in parts[1:] if re.fullmatch(r"[A-Za-z ]{4,30}", part) and re.search(r"filipino|american|chinese|japanese|korean|spanish|british|singaporean|foreign", part, re.I)), "")
            gender_match = re.search(r"\b(male|female|m|f)\b", joined, re.I)
            stockholder = "Yes" if re.search(r"\b(?:stockholder|stockholder\s*yes|\bY\b)\b", joined, re.I) else ""
            board_role = next((part for part in parts[1:] if re.search(r"\b(?:chair|director|trustee|independent|nominee|inc'?r|incorporator)\b", part, re.I)), "")
            officer_position = next((part for part in parts[1:] if re.search(r"\b(?:president|treasurer|secretary|officer|cfo|ceo|coo|vice|svp|avp|manager|counsel|compliance)\b", part, re.I)), "")
            metadata = {
                "person_name": name,
                "nationality": nationality,
                "board_role_or_indicator": board_role,
                "officer_position": officer_position,
                "gender": gender_match.group(1).upper() if gender_match else "",
                "stockholder_indicator": stockholder,
            }
            complete = bool(board_role or officer_position or nationality)
            row_number += 1
            items.append(_item("people", f"person_{row_number}", name, name, page, _line_evidence(sanitized_line), strength=56 if complete else 75, complete=complete, metadata=metadata))
            if len(items) >= limit:
                return items
    return items


def extract_stockholders(pages: List[Dict], limit: int = 20) -> List[Dict]:
    items = []
    stockholder_pages = _candidate_pages(pages, STOCKHOLDER_PAGE_TYPES, [r"stockholders?'?\s+(?:information|list)", r"number\s+of\s+shares"])
    row_number = 0
    for page in stockholder_pages:
        for line in _page_text(page).splitlines():
            if TIN_PATTERN.search(line) or RESIDENTIAL_PATTERN.search(line):
                continue
            parts = _split_table_line(line)
            if len(parts) < 2:
                continue
            name = parts[0].strip("0123456789. )(")
            if not _looks_like_person_or_entity(name):
                continue
            if re.fullmatch(r"others?", name, re.I):
                name = "Others (Aggregate)"
            joined = " ".join(parts[1:])
            share_match = re.search(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{4,}\b", joined)
            percent_match = re.search(r"\b\d{1,3}(?:\.\d+)?\s*%", joined)
            if not share_match and not percent_match:
                continue
            metadata = {
                "stockholder_name": name,
                "share_count": share_match.group(0) if share_match else "",
                "ownership_percent": percent_match.group(0) if percent_match else "",
            }
            row_number += 1
            items.append(_item("stockholders", f"stockholder_{row_number}", name, name, page, _line_evidence(line), strength=60, complete=bool(share_match and percent_match), metadata=metadata))
            if len(items) >= limit:
                return items
    return items


def extract_certification(pages: List[Dict]) -> List[Dict]:
    cert_pages = _candidate_pages(pages, CERTIFICATION_PAGE_TYPES, [r"corporate\s+secretary", r"subscribed\s+and\s+sworn", r"notary\s+public"])
    items = []
    for page in cert_pages[:2]:
        text = _page_text(page)
        attestation = bool(re.search(r"\bcorporate\s+secretary\b|\bcertif(?:y|ication)\b|\battest", text, re.I))
        notarization = bool(re.search(r"\bsubscribed\s+and\s+sworn\b|\bnotary\s+public\b|\bdoc\.?\s*no\.?\b|\bbook\s+no\.?\b|\bseries\s+of\b", text, re.I))
        if attestation:
            match = re.search(r"\bcorporate\s+secretary\b", text, re.I)
            items.append(_item("certification", "attestation_present", "Corporate Secretary Attestation", "Detected", page, _evidence(text, match.start(), match.end()) if match else _clean_text(text)[:180], strength=68))
        if notarization:
            match = re.search(r"\bsubscribed\s+and\s+sworn\b|\bnotary\s+public\b|\bdoc\.?\s*no\.?\b", text, re.I)
            items.append(_item("certification", "notarization_present", "Notarization Evidence", "Detected", page, _evidence(text, match.start(), match.end()) if match else _clean_text(text)[:180], strength=68))
        secretary_match = re.search(r"([A-Z][A-Za-z .,'-]{4,80})\s+(?:Corporate\s+Secretary|Corp(?:orate)?\.\s+Secretary)", text)
        if secretary_match and not _is_sensitive_label(secretary_match.group(1)):
            items.append(_item("certification", "corporate_secretary_name", "Corporate Secretary Name", _clean_text(secretary_match.group(1)), page, _evidence(text, secretary_match.start(), secretary_match.end()), strength=58))
        if items:
            break
    return items


def extract_gis_items(pages: List[Dict], metadata: Optional[Dict] = None) -> List[Dict]:
    items = []
    items.extend(extract_profile(pages))
    items.extend(extract_capital(pages))
    items.extend(extract_people(pages))
    items.extend(extract_stockholders(pages))
    items.extend(extract_certification(pages))
    return items


def find_item(items: List[Dict], category: str, field_name: str) -> Optional[Dict]:
    return next((item for item in items if item.get("category") == category and item.get("field_name") == field_name), None)


def _sec_is_near_match(extracted: str, intake: str) -> bool:
    left = _normalize_sec(extracted)
    right = _normalize_sec(intake)
    if not left or not right or abs(len(left) - len(right)) > 1:
        return False
    differences = sum(a != b for a, b in zip(left, right)) + abs(len(left) - len(right))
    return differences <= 1


def validate_profile_items(items: List[Dict], metadata: Dict) -> List[Dict]:
    validations = []
    company_item = find_item(items, "profile", "company_name")
    intake_company = str(metadata.get("company_name") or "").strip()
    if company_item and intake_company and int(company_item.get("confidence_score") or 0) >= 65:
        extracted = company_item.get("value_text") or ""
        if _normalize_company(extracted) == _normalize_company(intake_company):
            status = "Passed"
            message = f"Extracted GIS company name matches Intake metadata: {extracted}."
        elif fuzzy_company_match(extracted, intake_company):
            status = "Needs Review"
            message = f"Extracted GIS company name appears to be a normalized variant: {extracted}."
        else:
            status = "Failed"
            message = f"Extracted GIS company name '{extracted}' conflicts with Intake company '{intake_company}'."
    else:
        status = "Needs Review"
        message = "No reliable GIS company-name field was extracted for comparison."
    validations.append({"rule_name": "GIS Extracted Company Name", "status": status, "message": message, "suggested_revert_reason": "Wrong company profile" if status == "Failed" else ""})

    sec_item = find_item(items, "profile", "sec_registration_no")
    intake_sec = str(metadata.get("sec_registration_no") or "").strip()
    if sec_item and intake_sec and int(sec_item.get("confidence_score") or 0) >= 65:
        extracted = sec_item.get("value_text") or ""
        if _normalize_sec(extracted) == _normalize_sec(intake_sec):
            status = "Passed"
            message = f"Extracted SEC Registration Number matches Intake metadata: {extracted}."
        elif _sec_is_near_match(extracted, intake_sec):
            status = "Needs Review"
            message = f"Extracted SEC Registration Number '{extracted}' is a near OCR variant of Intake '{intake_sec}'; verify the source page."
        else:
            status = "Failed"
            message = f"Extracted SEC Registration Number '{extracted}' conflicts with Intake '{intake_sec}'."
    else:
        status = "Needs Review"
        message = "No reliable GIS SEC Registration Number field was extracted for comparison."
    validations.append({"rule_name": "GIS Extracted SEC Registration Number", "status": status, "message": message, "suggested_revert_reason": "Wrong company profile" if status == "Failed" else ""})

    year_item = find_item(items, "profile", "gis_reporting_year")
    intake_year = int(metadata.get("period_covered_year") or 0)
    if year_item and intake_year and int(year_item.get("confidence_score") or 0) >= 65:
        extracted_year = int(year_item.get("normalized_value") or year_item.get("value_text") or 0)
        status = "Passed" if extracted_year == intake_year else "Failed"
        message = f"Extracted GIS reporting year: {extracted_year}; Intake Period Year: {intake_year}."
    else:
        status = "Needs Review"
        message = "No high-authority GIS reporting year was extracted for comparison."
    validations.append({"rule_name": "GIS Extracted Reporting Year", "status": status, "message": message, "suggested_revert_reason": "Wrong period covered" if status == "Failed" else ""})
    return validations
