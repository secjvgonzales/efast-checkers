import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Dict, List

from config import TEXT_PREVIEW_MAX_CHARS
from pdf_utils import quality_flag

AFS_COMPONENT_DEFINITIONS = [
    {
        "name": "Statement of Management's Responsibility",
        "page_types": {"statement of management's responsibility"},
        "strong": [
            r"statement\s+of\s+management(?:'|’)?s?\s+responsibility",
            r"management(?:'|’)?s?\s+responsibility\s+for\s+financial\s+statements",
        ],
        "weak": [r"\bresponsibility\b"],
    },
    {
        "name": "Independent Auditor's Report",
        "page_types": {"independent auditor's report"},
        "strong": [
            r"independent\s+auditor(?:'|’)?s?\s+report",
            r"auditor(?:'|’)?s?\s+report",
            r"we\s+have\s+audited",
        ],
        "weak": [r"\bauditor\b"],
    },
    {
        "name": "Statement of Financial Position / Balance Sheet",
        "page_types": {"statement of financial position / balance sheet", "statement of financial position", "balance sheet"},
        "strong": [
            r"statement(?:s)?\s+of\s+financial\s+position",
            r"\bbalance\s+sheet\b",
        ],
        "weak": [r"\btotal\s+assets\b", r"\btotal\s+liabilities\b"],
    },
    {
        "name": "Statement of Profit or Loss / Statement of Income",
        "page_types": {
            "statement of income / receipts and expenses",
            "statement of income",
            "income statement",
            "statement of operations",
        },
        "strong": [
            r"statement(?:s)?\s+of\s+(?:profit\s+or\s+loss|income|operations)",
            r"\bincome\s+statement\b",
        ],
        "weak": [r"\bprofit\s+or\s+loss\b", r"\bnet\s+(?:income|loss)\b", r"\bgross\s+revenue\b"],
    },
    {
        "name": "Other Comprehensive Income",
        "page_types": {"statement of comprehensive income", "other comprehensive income"},
        "strong": [
            r"statement(?:s)?\s+of\s+comprehensive\s+income",
            r"statement(?:s)?\s+of\s+profit\s+or\s+loss\s+and\s+other\s+comprehensive\s+income",
        ],
        "weak": [r"\bother\s+comprehensive\s+income\b", r"\bcomprehensive\s+income\b", r"\bcomprehensive\b"],
    },
    {
        "name": "Statement of Changes in Equity",
        "page_types": {"statement of changes in equity / fund balance", "statement of changes in equity"},
        "strong": [
            r"statement(?:s)?\s+of\s+changes\s+in\s+equity",
        ],
        "weak": [r"\bchanges\s+in\s+equity\b", r"\bfund\s+balance\b", r"\bshareholders?'?\s+equity\b"],
    },
    {
        "name": "Statement of Cash Flows",
        "page_types": {"statement of cash flows"},
        "strong": [
            r"statement(?:s)?\s+of\s+cash\s+flows",
        ],
        "weak": [r"\bcash\s+flows\b", r"\boperating\s+activities\b", r"\bfinancing\s+activities\b"],
    },
    {
        "name": "Notes to Financial Statements",
        "page_types": {"notes to financial statements"},
        "strong": [
            r"notes\s+to\s+financial\s+statements",
            r"notes\s+to\s+(?:the\s+)?consolidated\s+financial\s+statements",
            r"summary\s+of\s+significant\s+accounting",
            r"basis\s+of\s+preparation",
        ],
        "weak": [r"\baccounting\s+policies\b"],
    },
]

REQUIRED_SECTIONS = [item["name"] for item in AFS_COMPONENT_DEFINITIONS]

AUDITOR_EXCLUDED_COMPONENTS = {
    "Statement of Financial Position / Balance Sheet",
    "Statement of Profit or Loss / Statement of Income",
    "Other Comprehensive Income",
    "Statement of Changes in Equity",
    "Statement of Cash Flows",
}

BIR_STRONG_EVIDENCE_PATTERNS = [
    r"\bproof\s+of\s+filing\b",
    r"\breceived\s+for\s+filing\b",
    r"\bbir\s+received\b",
    r"\bfiled\s+with\s+the\s+bureau\s+of\s+internal\s+revenue\b(?=.{0,120}\b(?:confirmation|receipt|received|reference\s+(?:no\.?|number)))",
    r"\beafs\s+submission\s+confirmation\b",
    r"\b(?:filing|transaction)\s+reference\s+(?:no\.?|number)\b(?=.{0,120}\b(?:confirmation|received|receipt|filing))",
    r"\b(?:date\s+received|received\s+date|received\s+by)\b(?=.{0,120}\b(?:bir|bureau\s+of\s+internal\s+revenue|eafs|filing|receipt))",
]

BIR_CONTEXT_PATTERNS = [
    r"\bbureau\s+of\s+internal\s+revenue\b",
    r"\bbir\b",
    r"\beafs\b",
    r"\bincome\s+tax\s+return\b",
    r"\bannual\s+income\s+tax\s+return\b",
    r"\btax\s+return\b",
]

PAGE_RULES = [
    ("Statement of Management's Responsibility", [
        r"statement\s+of\s+management(?:'|’)?s?\s+responsibility",
        r"management(?:'|’)?s?\s+responsibility\s+for\s+financial\s+statements",
    ]),
    ("Cover Sheet", [
        r"\bcover\s+sheet\b",
        r"\bcontents\b",
        r"\btable\s+of\s+contents\b",
    ]),
    ("Independent Auditor's Report", [
        r"independent\s+auditor(?:'|’)?s?\s+report",
        r"auditor(?:'|’)?s?\s+report",
    ]),
    ("Statement of Financial Position / Balance Sheet", [
        r"statement(?:s)?\s+of\s+financial\s+position",
        r"\bbalance\s+sheet\b",
    ]),
    ("Statement of Income / Receipts and Expenses", [
        r"statement(?:s)?\s+of\s+(?:profit\s+or\s+loss|income|operations)",
        r"\bincome\s+statement\b",
    ]),
    ("Statement of Comprehensive Income", [
        r"statement(?:s)?\s+of\s+comprehensive\s+income",
        r"statement(?:s)?\s+of\s+profit\s+or\s+loss\s+and\s+other\s+comprehensive\s+income",
    ]),
    ("Statement of Changes in Equity / Fund Balance", [
        r"statement(?:s)?\s+of\s+changes\s+in\s+equity",
    ]),
    ("Statement of Cash Flows", [
        r"statement(?:s)?\s+of\s+cash\s+flows",
    ]),
    ("Notes to Financial Statements", [
        r"notes\s+to\s+(?:the\s+)?financial\s+statements",
        r"notes\s+to\s+(?:the\s+)?consolidated\s+financial\s+statements",
        r"summary\s+of\s+significant\s+accounting",
        r"basis\s+of\s+preparation",
    ]),
]

AUTHORITATIVE_PERIOD_PATTERNS = [
    r"\byears?\s+ended\b",
    r"\bfor\s+the\s+years?\s+ended\b",
    r"\bfor\s+the\s+fiscal\s+years?\s+ended\b",
    r"\bas\s+(?:of|at)\b",
    r"\bfiscal\s+period\s+ended\b",
    r"\bperiod\s+covered\b",
]

INCIDENTAL_YEAR_CONTEXT_PATTERNS = [
    r"\baccreditation\b",
    r"\bvalid\s+until\b",
    r"\bvalidity\b",
    r"\bdue\b",
    r"\bmaturit(?:y|ies)\b",
    r"\bexpiry\b|\bexpires?\b|\bexpiration\b",
    r"\bforecast\b|\bestimat(?:e|ed|es)\b",
    r"\bcommitments?\b",
    r"\bfuture\b",
    r"\bsubsequent\b",
    r"\beffective\s+beginning\b",
]

PRIMARY_AFS_PAGE_TYPES = {
    "statement of financial position / balance sheet",
    "statement of financial position",
    "balance sheet",
    "statement of income / receipts and expenses",
    "statement of income",
    "income statement",
    "statement of operations",
    "statement of comprehensive income",
    "statement of changes in equity / fund balance",
    "statement of changes in equity",
    "statement of cash flows",
}

SUPPLEMENTARY_AUDITOR_PATTERNS = [
    r"\bsupplementary\s+schedules?\b",
    r"\bfinancial\s+soundness\s+indicators?\b",
    r"\bcomponents\s+of\s+financial\s+soundness\b",
]

GIS_PAGE_TYPES = {
    "SEC Acceptance / QR Cover",
    "Annex A / Primary Purpose",
    "Beneficial Ownership Declaration",
    "Corporate / Profile / Meeting Information",
    "AMLA Information",
    "Capital Structure",
    "Directors / Officers",
    "Stockholders' Information",
    "Investments / Other Corporate Information",
    "Corporate Secretary Attestation / Notarization",
}

GIS_PAGE_PATTERNS = {
    "Corporate / Profile / Meeting Information": [
        r"\bgeneral\s+information\s+sheet\b",
        r"\bamended\s+general\s+information\s+sheet\b",
        r"\bcorporate\s+name\b",
        r"\bsec\s+(?:registration|file)\s+(?:no|number)\b",
        r"\bactual\s+date\s+of\s+(?:annual|special)\s+meeting\b",
        r"\bprincipal\s+office\b",
        r"\bcorporate\s+address\b",
        r"\bperiod\s+covered\b",
    ],
    "AMLA Information": [
        r"\bamla\b",
        r"\banti[-\s]?money\s+laundering\b",
        r"\bbeneficial\s+ownership\s+information\b",
    ],
    "Capital Structure": [
        r"\bcapital\s+structure\b",
        r"\bauthorized\s+capital\s+stock\b",
        r"\bsubscribed\s+capital\s+stock\b",
        r"\bpaid[-\s]?up\s+capital\b",
    ],
    "Directors / Officers": [
        r"\bdirectors?\s+and\s+officers?\b",
        r"\bdirectors?\s*/\s*officers?\b",
        r"\bname(?:s)?\s+of\s+(?:the\s+)?directors?\b",
        r"\bname(?:s)?\s+of\s+(?:the\s+)?officers?\b",
        r"\bofficer\s+position\b",
    ],
    "Stockholders' Information": [
        r"\bstockholders?'?\s+(?:information|list|ownership)\b",
        r"\bstockholders?\b",
        r"\bnumber\s+of\s+shares\s+(?:subscribed|owned)\b",
        r"\btotal\s+number\s+of\s+stockholders\b",
    ],
    "Investments / Other Corporate Information": [
        r"\binvestments?\b",
        r"\baffiliations?\b",
        r"\btreasury\s+shares?\b",
        r"\bretained\s+earnings?\b",
        r"\bdividends?\b",
        r"\bsecondary\s+licen[cs]e\b",
        r"\bmanpower\b",
        r"\bfund\s+balance\b",
        r"\bother\s+corporate\s+information\b",
    ],
    "Corporate Secretary Attestation / Notarization": [
        r"\bcorporate\s+secretary\b",
        r"\bcertif(?:y|ication)\b",
        r"\bsecretary(?:'|’)?s?\s+attestation\b",
        r"\bsubscribed\s+and\s+sworn\b",
        r"\backnowledg(?:e)?ment\b",
        r"\bnotary\s+public\b",
        r"\bdoc\.?\s*no\.?\b",
        r"\bpage\s+no\.?\b",
        r"\bbook\s+no\.?\b",
        r"\bseries\s+of\b",
    ],
}

GIS_STOCK_REQUIRED = [
    "Corporate / Profile / Meeting Information",
    "Capital Structure",
    "Directors / Officers",
    "Stockholders' Information",
    "Investments / Other Corporate Information",
    "Corporate Secretary / Notarization",
]

GIS_NON_STOCK_REQUIRED = [
    "Corporate / Profile / Meeting Information",
    "Directors / Officers",
    "Investments / Other Corporate Information",
    "Corporate Secretary / Notarization",
]

GIS_OPTIONAL_COMPONENTS = [
    "AMLA Information",
    "Annex A / Primary Purpose",
]

GIS_PERIOD_YEAR_PATTERNS = [
    r"\b(?:amended\s+)?general\s+information\s+sheet\b(?:\s*\(\s*gis\s*\))?[\s\S]{0,80}?\bfor\s*(?:the\s*)?year\s*[:\-]?\s*(20\d{2})\b",
    r"\bgis\s+for\s+(?:the\s+)?year\s*[:\-]?\s*(20\d{2})\b",
]

GIS_MEETING_DATE_LABELS = {
    "Annual Meeting": [
        r"\bactual\s+date\s+of\s+annual\s+meeting\b(?!\s+per\s+by[-\s]?laws)",
        r"\bdate\s+of\s+actual\s+meeting\b",
        r"\bdate\s+of\s+annual\s+meeting\b(?!\s+per\s+by[-\s]?laws)",
    ],
    "Special Meeting": [
        r"actual\s+date\s+of\s+special\s+meeting",
        r"date\s+of\s+special\s+meeting",
    ],
}

GIS_NO_MEETING_PATTERNS = [
    r"\bno\s+meeting\b",
    r"\bno\s+meeting\s+held\b",
    r"\bnon[-\s]?holding\s+of\s+(?:the\s+)?annual\s+meeting\b",
    r"\banham\b",
]

GIS_AMENDMENT_PATTERNS = [r"\bamend(?:ment|ed)\b", r"\bamended\s+gis\b"]

GIS_BOD_HEADING_PATTERNS = [
    r"\bbeneficial\s+ownership\s+declaration\b",
    r"\bdeclaration\s+of\s+beneficial\s+ownership\b",
]

GIS_ACCEPTANCE_PATTERNS = [
    r"\bsec\s+(?:acceptance|accepted|received)\b",
    r"\bacceptance\s+(?:page|notice|reference)\b",
    r"\baccepted\s+(?:filing|report|gis)\b",
    r"\breceived\s+filing\s+(?:information|reference)\b",
]


def simplify_name(value: str) -> str:
    value = value.lower()
    value = value.replace("corporation", "corp").replace("corp.", "corp")
    value = value.replace("incorporated", "inc").replace("inc.", "inc")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def fuzzy_company_match(source: str, target: str) -> bool:
    source_clean = simplify_name(source)
    target_clean = simplify_name(target)
    if target_clean in source_clean:
        return True
    words = target_clean.split()
    if len(words) >= 3 and all(word in source_clean for word in words[:3]):
        return True
    return SequenceMatcher(None, source_clean, target_clean).ratio() >= 0.74


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _heading_text(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    line_region = " ".join(lines[:12])
    char_region = str(text or "")[:800]
    return _normalized_text(" ".join([line_region, char_region]))


def _is_contents_page(text: str) -> bool:
    heading = _heading_text(text)
    if not re.search(r"\b(?:contents|table\s+of\s+contents|index)\b", heading):
        return False
    statement_refs = [
        r"statement(?:s)?\s+of\s+financial\s+position",
        r"statement(?:s)?\s+of\s+(?:profit\s+or\s+loss|income)",
        r"statement(?:s)?\s+of\s+comprehensive\s+income",
        r"statement(?:s)?\s+of\s+changes\s+in\s+equity",
        r"statement(?:s)?\s+of\s+cash\s+flows",
    ]
    return sum(bool(re.search(pattern, heading)) for pattern in statement_refs) >= 2


def _has_heading_evidence(text: str, patterns: List[str]) -> bool:
    heading = _heading_text(text)
    full_text = _normalized_text(text)
    return any(re.search(pattern, heading) for pattern in patterns) or any(
        re.search(r"^\s*" + pattern, full_text) for pattern in patterns
    )


def _top_heading_text(text: str, line_limit: int = 4, char_limit: int = 300) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    line_region = " ".join(lines[:line_limit])
    char_region = str(text or "")[:char_limit]
    return _normalized_text(" ".join([line_region, char_region]))


def _starts_with_heading(text: str, patterns: List[str]) -> bool:
    heading = _top_heading_text(text)
    return any(re.search(r"^\s*" + pattern, heading) for pattern in patterns)


def _upper_region_has_heading(text: str, patterns: List[str], line_limit: int = 10, char_limit: int = 1200) -> bool:
    heading = _top_heading_text(text, line_limit=line_limit, char_limit=char_limit)
    return any(re.search(pattern, heading) for pattern in patterns)


def _has_statement_title_line(text: str, patterns: List[str], line_limit: int = 8) -> bool:
    lines = [line.strip().lower() for line in str(text or "").splitlines() if line.strip()]
    for line in lines[:line_limit]:
        normalized = re.sub(r"\s+", " ", line)
        if any(re.search(r"^(?:consolidated\s+|parent\s+company\s+)?" + pattern, normalized) for pattern in patterns):
            return True
    return False


def _is_notarial_opening(text: str) -> bool:
    opening = _top_heading_text(text, line_limit=6, char_limit=500)
    patterns = [
        r"\bnotarial\s+certificate\b",
        r"\backnowledg(?:e)?ment\b",
        r"\bsubscribed\s+and\s+sworn\b",
        r"\bnotary\s+public\b",
        r"\bdoc\.?\s*no\.?\b",
        r"\bpage\s+no\.?\b",
        r"\bbook\s+no\.?\b",
        r"\bseries\s+of\b",
    ]
    return any(re.search(pattern, opening) for pattern in patterns)


def _has_smr_heading(text: str, patterns: List[str]) -> bool:
    if not _upper_region_has_heading(text, patterns):
        return False
    return not _is_notarial_opening(text)


def _is_supplementary_auditor_report(text: str) -> bool:
    heading = _top_heading_text(text, line_limit=8, char_limit=900)
    return any(re.search(pattern, heading) for pattern in SUPPLEMENTARY_AUDITOR_PATTERNS)


def _has_financial_position_structure(text: str) -> bool:
    normalized = _normalized_text(text)
    markers = [
        r"\bassets\b",
        r"\bcurrent\s+assets\b",
        r"\bnon(?:current|\s+current)\s+assets\b",
        r"\btotal\s+assets\b",
        r"\bliabilities\b",
        r"\bcurrent\s+liabilities\b",
        r"\bnon(?:current|\s+current)\s+liabilities\b",
        r"\btotal\s+liabilities\b",
        r"\bequity\b",
        r"\btotal\s+liabilities\s+and\s+equity\b",
    ]
    score = sum(bool(re.search(pattern, normalized)) for pattern in markers)
    has_assets = bool(re.search(r"\bassets\b", normalized))
    has_liabilities = bool(re.search(r"\bliabilities\b", normalized))
    has_equity = bool(re.search(r"\bequity\b", normalized))
    return score >= 3 and has_assets and has_liabilities and has_equity


def _has_income_structure(text: str) -> bool:
    normalized = _normalized_text(text)
    markers = [
        r"\b(?:sales|revenues?)\b",
        r"\bcost\s+of\s+sales\b",
        r"\bgross\s+income\b",
        r"\b(?:expenses|expense)\b",
        r"\boperating\s+income\b",
        r"\bincome\s+before\s+(?:income\s+)?tax\b",
        r"\bprovision\s+for\s+income\s+tax\b",
        r"\bnet\s+(?:income|loss)\b",
    ]
    score = sum(bool(re.search(pattern, normalized)) for pattern in markers)
    has_performance = bool(re.search(r"\b(?:sales|revenues?)\b", normalized))
    has_result = bool(re.search(r"\b(?:net\s+(?:income|loss)|income\s+before\s+(?:income\s+)?tax|operating\s+income)\b", normalized))
    return score >= 3 and has_performance and has_result


def _has_oci_structure(text: str) -> bool:
    normalized = _normalized_text(text)
    return bool(
        re.search(r"\bother\s+comprehensive\s+income\b", normalized)
        and re.search(r"\btotal\s+comprehensive\s+income\b", normalized)
    )


def _has_changes_in_equity_structure(text: str) -> bool:
    normalized = _normalized_text(text)
    markers = [
        r"\bcapital\s+stock\b",
        r"\bpaid[-\s]?in\s+capital\b",
        r"\bretained\s+earnings\b",
        r"\btreasury\s+(?:stock|shares?)\b",
        r"\bnon[-\s]?controlling\s+interests?\b",
        r"\btotal\s+equity\b",
        r"\bequity\s+holders\b",
        r"\bbalances?\s+at\s+(?:january|december)\b",
        r"\btotal\s+comprehensive\s+(?:income|loss)\b",
        r"\bcash\s+dividends?\b",
    ]
    return sum(bool(re.search(pattern, normalized)) for pattern in markers) >= 2


def _has_cash_flow_structure(text: str) -> bool:
    normalized = _normalized_text(text)
    markers = [
        r"\boperating\s+activities\b",
        r"\binvesting\s+activities\b",
        r"\bfinancing\s+activities\b",
        r"\bnet\s+(?:increase|decrease)\s+in\s+cash\b",
        r"\bcash\s+flows?\s+from\b",
    ]
    return sum(bool(re.search(pattern, normalized)) for pattern in markers) >= 2


def _primary_detected(page_type: str, text: str, definition: Dict) -> bool:
    name = definition["name"]
    has_heading = page_type in definition["page_types"] or _has_heading_evidence(text, definition["strong"])
    if not has_heading:
        if name == "Statement of Profit or Loss / Statement of Income":
            if not _has_statement_title_line(text, [
                r"statement(?:s)?\s+of\s+comprehensive\s+income",
                r"statement(?:s)?\s+of\s+profit\s+or\s+loss\s+and\s+other\s+comprehensive\s+income",
            ]):
                return False
            comprehensive_heading = _has_heading_evidence(text, [
                r"statement(?:s)?\s+of\s+comprehensive\s+income",
                r"statement(?:s)?\s+of\s+profit\s+or\s+loss\s+and\s+other\s+comprehensive\s+income",
            ])
            return comprehensive_heading and _has_income_structure(text)
        return False
    if page_type not in definition["page_types"] and name in AUDITOR_EXCLUDED_COMPONENTS:
        if not _has_statement_title_line(text, definition["strong"]):
            return False
    if name == "Statement of Management's Responsibility":
        return _has_smr_heading(text, definition["strong"])
    if name == "Independent Auditor's Report":
        return not _is_supplementary_auditor_report(text)
    if name == "Statement of Financial Position / Balance Sheet":
        return _has_financial_position_structure(text)
    if name == "Statement of Profit or Loss / Statement of Income":
        return _has_income_structure(text)
    if name == "Other Comprehensive Income":
        return _has_oci_structure(text)
    if name == "Statement of Changes in Equity":
        return _has_changes_in_equity_structure(text)
    if name == "Statement of Cash Flows":
        return _has_cash_flow_structure(text)
    return True


def _is_confident_primary_statement(page_type: str, text: str) -> bool:
    for definition in AFS_COMPONENT_DEFINITIONS:
        if definition["name"] == "Notes to Financial Statements":
            continue
        if definition["name"] == "Independent Auditor's Report":
            continue
        if _primary_detected(page_type, text, definition):
            return True
    return False


def classify_page(text: str) -> str:
    if _is_contents_page(text):
        return "Cover Sheet"
    for page_type, patterns in PAGE_RULES:
        if page_type == "Statement of Management's Responsibility" and not _has_smr_heading(text, patterns):
            continue
        if _has_heading_evidence(text, patterns):
            definition = next(
                (
                    item for item in AFS_COMPONENT_DEFINITIONS
                    if page_type.lower() in item["page_types"]
                ),
                None,
            )
            if definition and definition["name"] not in {
                "Statement of Management's Responsibility",
                "Independent Auditor's Report",
                "Notes to Financial Statements",
            }:
                if not _has_statement_title_line(text, patterns):
                    continue
                if not _primary_detected(page_type.lower(), text, definition):
                    continue
            return page_type
    return "Other / Unclassified"


def is_gis_submission(metadata: Dict) -> bool:
    return str(metadata.get("report_type") or "").strip().lower() == "gis"


def _gis_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _has_explicit_bod_heading(text: str) -> bool:
    lowered = _gis_text(text).lower()
    if any(re.search(pattern, lowered) for pattern in GIS_BOD_HEADING_PATTERNS):
        return True
    return bool(
        re.search(r"\bbeneficial\s+owners?\b", lowered)
        and re.search(r"\bdeclaration\b", lowered)
    )


def is_gis_acceptance_cover(text: str) -> bool:
    lowered = _gis_text(text).lower()
    has_acceptance = any(re.search(pattern, lowered) for pattern in GIS_ACCEPTANCE_PATTERNS)
    has_qr = bool(re.search(r"\bqr(?:\s+code)?\b", lowered))
    return has_acceptance or (has_qr and bool(re.search(r"\bsec\b", lowered)))


def _gis_anchor_count(text: str, patterns: List[str]) -> int:
    return sum(bool(re.search(pattern, text, re.I)) for pattern in patterns)


def _gis_roster_structure(text: str) -> bool:
    return _gis_anchor_count(text, [
        r"\bnationality\b", r"\bgender\b", r"\bboard\s+(?:position|role)\b",
        r"\bofficer\s+position\b", r"\bposition\b",
    ]) >= 3


def _gis_stockholder_structure(text: str) -> bool:
    return _gis_anchor_count(text, [
        r"\bname\b", r"\bshares?\s+(?:subscribed|owned)\b", r"\b%\s*(?:of\s+)?ownership\b",
        r"\bamount\s+paid\b", r"\bnationality\b",
    ]) >= 3


def _gis_continuation_compatible(text: str, page_type: str) -> bool:
    if page_type == "Directors / Officers":
        return _gis_roster_structure(text) or bool(
            re.search(r"\bfilipin[oa]\b", text, re.I)
            and len(re.findall(r"\bn\s*/?\s*a\b", text, re.I)) >= 2
            and re.search(r"\b(?:vice\s+president|president|treasurer|secretary|officer)\b", text, re.I)
        )
    if page_type == "Stockholders' Information":
        return _gis_stockholder_structure(text) or bool(
            re.search(r"\bname\b", text, re.I)
            and re.search(r"\b(?:owner|ownership)\b", text, re.I)
            and len(re.findall(r"\b\d[\d,.]*\b", text)) >= 3
        )
    return False


def classify_gis_page(text: str) -> str:
    lowered = _gis_text(text).lower()
    if is_gis_acceptance_cover(lowered):
        return "SEC Acceptance / QR Cover"
    if _has_explicit_bod_heading(lowered):
        return "Beneficial Ownership Declaration"
    if re.search(r"\bannex\s+a\b", lowered) and re.search(
        r"\bprimary\s+purpose\b|\bpurpose\s+continuation\b|\battached\s+annex\b",
        lowered,
    ):
        return "Annex A / Primary Purpose"
    profile_anchors = [
        r"\bcorporate\s+name\b", r"\bsec\s+(?:registration|file)\s+(?:no\.?|number)\b",
        r"\bfiscal\s+year\s+end\b", r"\bactual\s+date\s+of\s+(?:annual|special)\s+meeting\b",
        r"\bprincipal\s+office\b", r"\bperiod\s+covered\b",
    ]
    has_gis_heading = bool(re.search(r"\b(?:amended\s+)?general\s+information\s+sheet\b", lowered))
    has_authoritative_gis_year_heading = bool(re.search(
        r"\b(?:amended\s+)?general\s+information\s+sheet\s*(?:\(\s*gis\s*\))?\s+for\s*(?:the\s*)?year\s*[:\-]?\s*20\d{2}\b",
        lowered,
    ))
    if has_authoritative_gis_year_heading or (has_gis_heading and _gis_anchor_count(lowered, profile_anchors) >= 2) or _gis_anchor_count(lowered, profile_anchors) >= 3:
        return "Corporate / Profile / Meeting Information"

    if re.search(r"\banti[-\s]?money\s+laundering\b|\bamla\b", lowered):
        return "AMLA Information"

    capital_anchors = [
        r"\bauthorized\s+capital(?:\s+stock)?\b", r"\bsubscribed\s+capital(?:\s+stock)?\b",
        r"\bpaid[-\s]?up\s+capital\b", r"\bpar\s*/?\s*stated\s+value\b",
        r"\btype\s+of\s+shares?\b", r"\bcapital\s+structure\b",
    ]
    if re.search(r"\bdirectors?\s*(?:and|/)\s*officers?\b", lowered) or _gis_roster_structure(lowered):
        return "Directors / Officers"

    if re.search(r"\bstockholder.{0,4}\s+information\b", lowered) or _gis_stockholder_structure(lowered):
        return "Stockholders' Information"

    capital_table_structure = _gis_anchor_count(lowered, [
        r"\bnumber\s+of\s+shares?\b", r"\bpar\s*/?\s*stated\s+value\b", r"\bamount\b",
    ]) >= 2
    if _gis_anchor_count(lowered, capital_anchors) >= 2 or capital_table_structure:
        return "Capital Structure"

    other_anchors = [
        r"\binvestment\s+of\s+corporate\s+funds?\b", r"\btreasury\s+shares?\b",
        r"\bretained\s+earnings?\b", r"\bdividends?\s+declared\b",
        r"\badditional\s+shares?\s+issued\b", r"\btotal\s+annual\s+compensation\b",
        r"\bother\s+corporate\s+information\b",
    ]
    if _gis_anchor_count(lowered, other_anchors) >= 2 or re.search(r"\binvestment\s+of\s+corporate\s+funds?\b", lowered):
        return "Investments / Other Corporate Information"

    certification_anchors = [
        r"\bsubscribed\s+and\s+sworn\b", r"\bnotary\s+public\b", r"\bdoc\.?\s*no\.?\b",
        r"\bpage\s+no\.?\b", r"\bbook\s+no\.?\b", r"\bseries\s+of\b",
    ]
    has_secretary_declaration = bool(re.search(r"\bcorporate\s+secretary\b", lowered) and re.search(r"\b(?:certif(?:y|ication)|attest)\b", lowered))
    if has_secretary_declaration or _gis_anchor_count(lowered, certification_anchors) >= 2:
        return "Corporate Secretary Attestation / Notarization"
    return "Other / Unclassified"


def has_period(text: str, year: int) -> bool:
    return str(year) in (text or "")


def is_afs_submission(metadata: Dict) -> bool:
    report_type = str(metadata.get("report_type") or "").strip().lower()
    submission_type = str(metadata.get("submission_type") or "").strip().lower()
    return report_type == "afs" or "annual financial statement" in submission_type


def _page_evidence_text(page: Dict) -> str:
    return " ".join([
        str(page.get("page_type") or ""),
        _processing_text(page),
    ]).lower()


def _processing_text(page: Dict) -> str:
    return str(
        page.get("extracted_text")
        or page.get("text")
        or page.get("original_text")
        or page.get("text_preview")
        or ""
    )


def _component_evidence(page: Dict, definition: Dict) -> str:
    page_type = str(page.get("page_type") or "").strip().lower().replace("’", "'")
    processing_text = _processing_text(page)
    if _is_contents_page(processing_text):
        return ""
    if (
        definition["name"] in AUDITOR_EXCLUDED_COMPONENTS
        and page_type == "independent auditor's report"
    ):
        return ""
    if definition["name"] == "Notes to Financial Statements" and _is_confident_primary_statement(page_type, processing_text):
        return ""
    if _primary_detected(page_type, processing_text, definition):
        return "Detected"
    return ""


def _primary_iar_page_numbers(pages: List[Dict]) -> List[int]:
    numbers = []
    in_primary_report = False
    for page in pages:
        text = _processing_text(page)
        page_type = str(page.get("page_type") or "").strip().lower()
        if _is_supplementary_auditor_report(text):
            in_primary_report = False
            continue
        has_iar_heading = page_type == "independent auditor's report" or _has_heading_evidence(
            text,
            [r"independent\s+auditor(?:'|’)?s?\s+report", r"auditor(?:'|’)?s?\s+report"],
        )
        if has_iar_heading:
            in_primary_report = True
            numbers.append(page.get("page_number"))
            continue
        if in_primary_report:
            if _is_confident_primary_statement(page_type, text) or page_type == "notes to financial statements":
                in_primary_report = False
                continue
            if re.search(r"\b(?:audit|auditor|audited|financial\s+statements|opinion|responsibilities)\b", _normalized_text(text)):
                numbers.append(page.get("page_number"))
    return numbers


def _cash_flow_page_numbers(pages: List[Dict], definition: Dict) -> List[int]:
    numbers = []
    in_statement = False
    for page in pages:
        text = _processing_text(page)
        page_type = str(page.get("page_type") or "").strip().lower()
        if _primary_detected(page_type, text, definition):
            in_statement = True
            numbers.append(page.get("page_number"))
            continue
        if in_statement:
            if page_type == "notes to financial statements" or _is_confident_primary_statement(page_type, text):
                in_statement = False
                continue
            if _has_cash_flow_structure(text) or re.search(r"\b(?:operating|investing|financing)\s+activities\b", _normalized_text(text)):
                numbers.append(page.get("page_number"))
    return numbers


def _gis_page_is_usable(page: Dict) -> bool:
    return page.get("page_type") != "SEC Acceptance / QR Cover"


def _gis_component_pages(pages: List[Dict], component: str) -> List[int]:
    expected_type = "Corporate Secretary Attestation / Notarization" if component == "Corporate Secretary / Notarization" else component
    matches = []
    for page in pages:
        if not _gis_page_is_usable(page):
            continue
        page_type = str(page.get("page_type") or "")
        if page_type == expected_type:
            matches.append(page.get("page_number"))
    return matches


def _gis_bod_pages(pages: List[Dict]) -> List[int]:
    return [
        page.get("page_number")
        for page in pages
        if _gis_page_is_usable(page)
        and (
            page.get("page_type") == "Beneficial Ownership Declaration"
            or _has_explicit_bod_heading(_processing_text(page))
        )
    ]


def _gis_annex_pages(pages: List[Dict]) -> List[int]:
    return [
        page.get("page_number")
        for page in pages
        if _gis_page_is_usable(page)
        and (
            page.get("page_type") == "Annex A / Primary Purpose"
            or (
                re.search(r"\bannex\s+a\b", _gis_text(_processing_text(page)), re.I)
                and re.search(r"\bprimary\s+purpose\b|\bpurpose\s+continuation\b", _gis_text(_processing_text(page)), re.I)
            )
        )
    ]


def _gis_all_text(pages: List[Dict], include_acceptance: bool = False) -> str:
    selected = pages if include_acceptance else [page for page in pages if _gis_page_is_usable(page)]
    return "\n".join(_processing_text(page) for page in selected)


def evaluate_gis_bod(pages: List[Dict]) -> Dict:
    detected_pages = _gis_bod_pages(pages)
    acceptance_pages = [
        page.get("page_number")
        for page in pages
        if page.get("page_type") == "SEC Acceptance / QR Cover"
    ]
    if detected_pages:
        status = "Detected"
        message = f"Beneficial Ownership Declaration evidence detected on {format_page_numbers(detected_pages)}."
    elif acceptance_pages:
        status = "Not Applicable / Accepted QA Copy"
        message = (
            "No Beneficial Ownership Declaration was detected; the accepted QA copy includes "
            f"{format_page_numbers(acceptance_pages)}."
        )
    else:
        status = "Not Detected"
        message = "No explicit Beneficial Ownership Declaration heading was detected."
    return {
        "status": status,
        "message": message,
        "page_numbers": detected_pages,
        "detected_pages": format_page_numbers(detected_pages),
    }


def evaluate_gis_completeness(pages: List[Dict], corporation_type: str = "Stock") -> Dict:
    required = GIS_NON_STOCK_REQUIRED if str(corporation_type or "").lower() == "non-stock" else GIS_STOCK_REQUIRED
    components = []
    uncertain_text = any(page.get("image_quality_flag") in ("Warning", "Failed") for page in pages)
    for component in required:
        page_numbers = _gis_component_pages(pages, component)
        components.append({
            "component": component,
            "status": "Detected" if page_numbers else "Needs Review" if uncertain_text else "Missing",
            "page_numbers": page_numbers,
            "detected_pages": format_page_numbers(page_numbers),
            "required": True,
        })

    for component in GIS_OPTIONAL_COMPONENTS:
        page_numbers = _gis_component_pages(
            pages,
            component,
        )
        components.append({
            "component": component,
            "status": "Detected" if page_numbers else "Not Present",
            "page_numbers": page_numbers,
            "detected_pages": format_page_numbers(page_numbers),
            "required": False,
        })

    bod = evaluate_gis_bod(pages)
    components.append({
        "component": "Beneficial Ownership Declaration",
        "status": bod["status"],
        "page_numbers": bod["page_numbers"],
        "detected_pages": bod["detected_pages"],
        "required": False,
    })

    missing = [item["component"] for item in components if item["required"] and item["status"] == "Missing"]
    uncertain = [item["component"] for item in components if item["required"] and item["status"] == "Needs Review"]
    if missing:
        status = "Failed"
        message = (
            f"Missing required GIS {corporation_type or 'Stock'} component(s): "
            + ", ".join(missing)
            + ". Optional Annex A and conditional BOD are excluded from this result."
        )
    elif uncertain:
        status = "Needs Review"
        message = (
            "Required GIS component evidence could not be reliably recovered for: "
            + ", ".join(uncertain)
            + ". Review low-text/OCR pages before treating these sections as absent."
        )
    else:
        status = "Passed"
        message = (
            f"All required GIS {corporation_type or 'Stock'} component groups were detected. "
            "Optional Annex A and conditional BOD are excluded from completeness."
        )
    return {
        "status": status,
        "message": message,
        "suggested_revert_reason": "Incomplete pages" if missing else "",
        "components": components,
    }


def extract_gis_period_years(text: str) -> List[int]:
    years = []
    lowered = _gis_text(text).lower()
    for pattern in GIS_PERIOD_YEAR_PATTERNS:
        years.extend(int(match) for match in re.findall(pattern, lowered))
    return sorted(set(years))


def _parse_gis_date(value: str):
    value = re.sub(r"\s+", " ", str(value or "").strip()).strip(" .,:;-")
    formats = (
        "%B %d, %Y",
        "%B %d %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%b %d %Y",
        "%d %b %Y",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d-%b-%y",
        "%d-%b-%Y",
        "%d/%m/%y",
        "%d/%m/%Y",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _extract_gis_meeting_dates(text: str, meeting_type: str) -> List[date]:
    lowered = _gis_text(text).lower()
    labels = GIS_MEETING_DATE_LABELS.get(meeting_type, [])
    dates = []
    date_pattern = (
        r"([a-z]+\s+\d{1,2},?\s+\d{4}|"
        r"\d{1,2}\s+[a-z]+\s+\d{4}|"
        r"\d{1,2}[/-]\d{1,2}[/-]\d{4}|"
        r"\d{1,2}-[a-z]{3}-\d{2,4}|"
        r"\d{4}-\d{1,2}-\d{1,2})"
    )
    for label in labels:
        for match in re.finditer(label + r"\s*[:\-]?\s*" + date_pattern, lowered, re.I):
            parsed = _parse_gis_date(match.group(1))
            if parsed:
                dates.append(parsed)
    return sorted(set(dates))


def _metadata_period_date(metadata: Dict):
    value = metadata.get("period_covered")
    if isinstance(value, date):
        return value
    return _parse_gis_date(value)


def _gis_meeting_validation(pages: List[Dict], metadata: Dict) -> Dict:
    all_text = _gis_all_text(pages)
    submission_type = str(metadata.get("submission_type") or "").strip()
    target_date = _metadata_period_date(metadata)
    if submission_type == "No Meeting / Non-Holding of Annual Meeting" and any(
        re.search(pattern, all_text, re.I) for pattern in GIS_NO_MEETING_PATTERNS
    ):
        return {
            "status": "Needs Review",
            "message": "No Meeting / non-holding evidence was detected; reviewer confirmation is required.",
            "suggested_revert_reason": "",
        }

    if submission_type == "Special Meeting" or re.search(r"\bspecial\s+meeting\b", all_text, re.I):
        meeting_type = "Special Meeting"
    else:
        meeting_type = "Annual Meeting"
    dates = _extract_gis_meeting_dates(all_text, meeting_type)

    if submission_type in ("Amendment / Amended GIS", "Amended GIS") or any(
        re.search(pattern, all_text, re.I) for pattern in GIS_AMENDMENT_PATTERNS
    ):
        if dates and target_date:
            status = "Passed" if target_date in dates else "Failed"
            message = (
                f"Amendment evidence shows {meeting_type.lower()} date(s) "
                f"{', '.join(item.isoformat() for item in dates)}; "
                f"Intake Period Covered is {target_date.isoformat()}."
            )
        else:
            status = "Needs Review"
            message = "Amendment evidence was detected; confirm the meeting date against Intake Period Covered."
        return {
            "status": status,
            "message": message,
            "suggested_revert_reason": "Wrong period covered" if status == "Failed" else "",
        }

    if not dates or not target_date:
        return {
            "status": "Needs Review",
            "message": (
                f"{meeting_type} evidence was not paired with a clearly readable actual meeting date "
                "and Intake Period Covered."
            ),
            "suggested_revert_reason": "",
        }
    status = "Passed" if target_date in dates else "Failed"
    return {
        "status": status,
        "message": (
            f"{meeting_type} date evidence: {', '.join(item.isoformat() for item in dates)}. "
            f"Intake Period Covered: {target_date.isoformat()}."
        ),
        "suggested_revert_reason": "Wrong period covered" if status == "Failed" else "",
    }


def _gis_company_validation(pages: List[Dict], metadata: Dict) -> List[Dict]:
    body_text = _gis_all_text(pages)
    company_name = str(metadata.get("company_name") or "").strip()
    sec_no = str(metadata.get("sec_registration_no") or "").strip()
    insufficient = len(_gis_text(body_text)) < 40
    company_match = bool(company_name) and fuzzy_company_match(body_text, company_name)
    normalized_sec = re.sub(r"[^a-z0-9]", "", sec_no.lower())
    normalized_body = re.sub(r"[^a-z0-9]", "", body_text.lower())
    sec_match = bool(normalized_sec) and normalized_sec in normalized_body
    company_status = "Passed" if company_match else "Needs Review"
    sec_status = "Passed" if sec_match else "Needs Review"
    return [
        {
            "rule_name": "GIS Company Name",
            "status": company_status,
            "message": (
                "Company name evidence matches Intake metadata."
                if company_match
                else "Company name evidence was not found in usable text; structured extraction will distinguish conflict from missing evidence."
            ),
            "suggested_revert_reason": "",
        },
        {
            "rule_name": "GIS SEC Registration Number",
            "status": sec_status,
            "message": (
                "SEC Registration Number evidence matches Intake metadata."
                if sec_match
                else "SEC Registration Number evidence was not found in usable text; missing OCR evidence is not treated as a conflict."
            ),
            "suggested_revert_reason": "",
        },
    ]


def _gis_corporate_secretary_validation(pages: List[Dict]) -> Dict:
    text = _gis_all_text(pages)
    secretary = bool(re.search(r"\bcorporate\s+secretary\b|\bsecretary(?:'|’)?s?\s+attestation\b", text, re.I))
    notarization = any(
        re.search(pattern, text, re.I)
        for pattern in GIS_PAGE_PATTERNS["Corporate Secretary Attestation / Notarization"][2:]
    )
    if secretary and notarization:
        status = "Passed"
    elif secretary or notarization:
        status = "Needs Review"
    else:
        status = "Needs Review"
    return {
        "rule_name": "Corporate Secretary / Notarization Evidence",
        "status": status,
        "message": (
            f"Corporate Secretary text: {'Detected' if secretary else 'Not Detected'}; "
            f"notarization text: {'Detected' if notarization else 'Not Detected'}. "
            "Signature or notarial-stamp appearance still requires visual confirmation."
        ),
        "suggested_revert_reason": "",
    }


def validate_gis_document(pages: List[Dict], metadata: Dict) -> List[Dict]:
    all_text = _gis_all_text(pages)
    validations = _gis_company_validation(pages, metadata)
    extracted_items = []
    try:
        from gis_extraction_engine import extract_gis_items, validate_profile_items

        extracted_items = extract_gis_items(pages, metadata)
        validations.extend(validate_profile_items(extracted_items, metadata))
    except Exception as exc:
        validations.append({
            "rule_name": "GIS Structured Profile Extraction",
            "status": "Needs Review",
            "message": f"Structured GIS profile extraction could not complete safely: {exc}",
            "suggested_revert_reason": "",
        })
    year = int(metadata.get("period_covered_year") or 0)
    year_item = next(
        (item for item in extracted_items if item.get("category") == "profile" and item.get("field_name") == "gis_reporting_year"),
        None,
    )
    if year_item and int(year_item.get("confidence_score") or 0) >= 65:
        detected_year = int(year_item.get("normalized_value") or year_item.get("value_text") or 0)
        year_status = "Passed" if detected_year == year else "Failed"
        year_message = f"Authoritative GIS heading/profile evidence shows reporting year {detected_year}; Intake Period Year is {year}."
    else:
        detected_years = extract_gis_period_years(all_text)
        if year in detected_years:
            year_status = "Passed"
            year_message = f"GIS heading evidence supports Period Year {year}."
        elif detected_years:
            year_status = "Needs Review"
            year_message = f"Weak GIS year-like evidence shows {', '.join(map(str, detected_years))}; no authoritative GIS heading/profile year was recovered."
        else:
            year_status = "Needs Review"
            year_message = f"No authoritative GIS reporting-year evidence was recovered for Intake Period Year {year}."
    validations.append({
        "rule_name": "GIS Period Year",
        "status": year_status,
        "message": year_message,
        "suggested_revert_reason": "Wrong period covered" if year_status == "Failed" else "",
    })
    validations.append({
        "rule_name": "GIS Period Covered / Submission Type",
        **_gis_meeting_validation(pages, metadata),
    })

    completeness = evaluate_gis_completeness(pages, metadata.get("corporation_type", "Stock"))
    validations.append({
        "rule_name": "GIS Completeness Check",
        "status": completeness["status"],
        "message": completeness["message"],
        "suggested_revert_reason": completeness["suggested_revert_reason"],
    })

    acceptance_pages = [
        page.get("page_number")
        for page in pages
        if page.get("page_type") == "SEC Acceptance / QR Cover"
    ]
    validations.append({
        "rule_name": "SEC Acceptance / QR Cover",
        "status": "Detected" if acceptance_pages else "Needs Review",
        "message": (
            f"Likely SEC acceptance/QR cover detected on {format_page_numbers(acceptance_pages)}; "
            "excluded from GIS completeness."
            if acceptance_pages
            else "No SEC acceptance/QR cover was detected. This optional item does not affect GIS completeness."
        ),
        "suggested_revert_reason": "",
    })

    quality_failed = [page for page in pages if page.get("image_quality_flag") == "Failed"]
    quality_warning = [page for page in pages if page.get("image_quality_flag") == "Warning"]
    critical_profile_fields = {"sec_registration_no", "gis_reporting_year"}
    recovered_critical = {
        item.get("field_name")
        for item in extracted_items
        if item.get("category") == "profile" and int(item.get("confidence_score") or 0) >= 65
    }
    noisy_profile_text = any(
        page.get("page_type") == "Corporate / Profile / Meeting Information"
        and (page.get("extraction_source") == "OCR Fallback" or _processing_text(page).count("\ufffd") >= 2)
        for page in pages
    )
    has_ocr_uncertainty = bool(critical_profile_fields - recovered_critical) and bool(
        quality_failed or quality_warning or noisy_profile_text
    )
    validations.append({
        "rule_name": "GIS Image Quality",
        "status": "Needs Review" if has_ocr_uncertainty else "Warning" if quality_warning else "Passed",
        "message": (
            "Text extraction is partially usable, but one or more critical GIS fields/sections could not be reliably recovered."
            if has_ocr_uncertainty
            else f"{len(quality_warning)} page(s) have low extracted text; review Text Layer/OCR source."
            if quality_warning
            else "Extracted text is adequate for preliminary GIS review."
        ),
        "suggested_revert_reason": "Poor image quality" if quality_failed else "",
    })
    rotated_pages = [
        page for page in pages
        if int(page.get("rotation_degrees") or 0) in (90, 180, 270)
    ]
    landscape_pages = [page for page in pages if page.get("orientation") == "Landscape"]
    validations.append({
        "rule_name": "GIS Page Orientation / Rotation",
        "status": "Warning" if rotated_pages or landscape_pages else "Passed",
        "message": (
            f"{len(rotated_pages)} rotated and {len(landscape_pages)} landscape page(s) detected; "
            "review page geometry and orientation."
            if rotated_pages or landscape_pages
            else "No non-zero rotation metadata or landscape pages detected."
        ),
        "suggested_revert_reason": "",
    })
    validations.append(_gis_corporate_secretary_validation(pages))
    return validations


def format_page_numbers(page_numbers: List[int]) -> str:
    numbers = sorted({int(number) for number in page_numbers if number is not None})
    if not numbers:
        return "—"
    ranges = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append(f"{start}–{previous}" if start != previous else str(start))
        start = previous = number
    ranges.append(f"{start}–{previous}" if start != previous else str(start))
    prefix = "Page" if len(numbers) == 1 else "Pages"
    return f"{prefix} " + ", ".join(ranges)


def _years_in_text(text: str) -> List[int]:
    return [int(match) for match in re.findall(r"\b20\d{2}\b", text or "")]


def _looks_incidental_year_context(text: str) -> bool:
    normalized = _normalized_text(text)
    return any(re.search(pattern, normalized) for pattern in INCIDENTAL_YEAR_CONTEXT_PATTERNS)


def _looks_authoritative_period_context(text: str) -> bool:
    normalized = _normalized_text(text)
    if any(re.search(pattern, normalized) for pattern in AUTHORITATIVE_PERIOD_PATTERNS):
        return True
    return False


def page_scope(text: str) -> str:
    heading = _top_heading_text(text, line_limit=8, char_limit=900)
    if re.search(r"\bparent\s+company\s+statements?\b|\bseparate\s+financial\s+statements?\b|\bcompany[-\s]?only\b", heading):
        return "parent"
    if re.search(r"\bconsolidated\b|\band\s+subsidiaries\b", heading):
        return "consolidated"
    return "unspecified"


def document_scope(metadata: Dict, pages: List[Dict]) -> str:
    metadata_text = " ".join([
        str(metadata.get("company_name") or ""),
        str(metadata.get("submission_type") or ""),
    ]).lower()
    if re.search(r"\band\s+subsidiaries\b|\bconsolidated\b", metadata_text):
        return "consolidated"
    early_pages = pages[:20]
    scopes = [page_scope(_processing_text(page)) for page in early_pages]
    if "consolidated" in scopes:
        return "consolidated"
    if "parent" in scopes and "consolidated" not in scopes:
        return "parent"
    return "unspecified"


def _scope_compatible(page_text: str, target_scope: str) -> bool:
    scope = page_scope(page_text)
    if target_scope == "consolidated" and scope == "parent":
        return False
    if target_scope == "parent" and scope == "consolidated":
        return False
    return True


def detect_afs_reporting_years(pages: List[Dict]) -> List[int]:
    """Detect AFS reporting years from authoritative statement-period contexts."""
    evidence: Dict[int, int] = {}
    primary_statement_evidence: Dict[int, int] = {}
    for page in pages:
        page_type = str(page.get("page_type") or "").strip().lower()
        text = _processing_text(page)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        authoritative_page = page_type in {
            "statement of management's responsibility",
            "independent auditor's report",
            "cover sheet",
        } or page_type in PRIMARY_AFS_PAGE_TYPES
        for index, line in enumerate(lines):
            window_lines = lines[max(0, index - 2): min(len(lines), index + 3)]
            window = " ".join(window_lines)
            years = _years_in_text(window)
            if not years:
                continue
            if not authoritative_page:
                continue
            if _looks_incidental_year_context(window):
                continue
            context_is_authoritative = _looks_authoritative_period_context(window)
            if not context_is_authoritative and authoritative_page:
                context_is_authoritative = bool(
                    index <= 8 and len(set(years)) >= 2 and re.search(r"\b20\d{2}\b", line)
                )
            if not context_is_authoritative:
                continue
            if page_type in PRIMARY_AFS_PAGE_TYPES and index > 15:
                continue
            score = 3 if authoritative_page else 1
            if len(set(years)) >= 2:
                score += 2
            if page_type in PRIMARY_AFS_PAGE_TYPES:
                score += 2
            for year in years:
                evidence[year] = evidence.get(year, 0) + score
                if page_type in PRIMARY_AFS_PAGE_TYPES:
                    primary_statement_evidence[year] = primary_statement_evidence.get(year, 0) + score
    primary_evidence = {year: score for year, score in primary_statement_evidence.items() if score >= 5}
    if primary_evidence:
        max_year = max(primary_evidence)
        # Ignore older historical note/reference years when a contiguous reporting set is available.
        contiguous = []
        year = max_year
        while year in primary_evidence:
            contiguous.append(year)
            year -= 1
        if len(contiguous) >= 2:
            return contiguous
    strong_years = [year for year, score in evidence.items() if score >= 3]
    return sorted(set(strong_years), reverse=True)


def detected_afs_current_year(pages: List[Dict]):
    years = detect_afs_reporting_years(pages)
    return years[0] if years else None


def _company_master_relevant(metadata: Dict, company_master: Dict) -> bool:
    master_name = str(company_master.get("company_name") or "").strip()
    master_sec = str(company_master.get("sec_registration_no") or "").strip()
    metadata_name = str(metadata.get("company_name") or "").strip()
    metadata_sec = str(metadata.get("sec_registration_no") or "").strip()
    if not master_name and not master_sec:
        return False
    if master_sec and metadata_sec and master_sec.lower() == metadata_sec.lower():
        return True
    return bool(master_name and metadata_name and fuzzy_company_match(metadata_name, master_name))


def validate_company_master(all_text: str, metadata: Dict, company_master: Dict) -> Dict:
    if not _company_master_relevant(metadata, company_master):
        return {
            "rule_name": "Company master data match",
            "status": "Needs Review",
            "message": "No relevant company master record was found; company identity cannot be automatically verified.",
            "suggested_revert_reason": "",
        }
    master_name = str(company_master.get("company_name") or "").strip()
    master_sec = str(company_master.get("sec_registration_no") or "").strip()
    normalized_body = re.sub(r"[^a-z0-9]", "", all_text.lower())
    normalized_sec = re.sub(r"[^a-z0-9]", "", master_sec.lower())
    company_ok = fuzzy_company_match(all_text, master_name) and bool(normalized_sec and normalized_sec in normalized_body)
    return {
        "rule_name": "Company master data match",
        "status": "Passed" if company_ok else "Failed",
        "message": (
            "Company name and SEC registration number align with master record."
            if company_ok
            else "Document company identity conflicts with the relevant master record."
        ),
        "suggested_revert_reason": "" if company_ok else "Wrong company profile",
    }


def evaluate_afs_completeness(pages: List[Dict], metadata: Dict = None) -> Dict:
    target_scope = document_scope(metadata or {}, pages)
    components = []
    for definition in AFS_COMPONENT_DEFINITIONS:
        if definition["name"] == "Independent Auditor's Report":
            detected_pages = _primary_iar_page_numbers(pages)
        elif definition["name"] == "Statement of Cash Flows":
            detected_pages = _cash_flow_page_numbers(pages, definition)
        else:
            detected_pages = []
            for page in pages:
                if definition["name"] in AUDITOR_EXCLUDED_COMPONENTS and not _scope_compatible(_processing_text(page), target_scope):
                    continue
                evidence = _component_evidence(page, definition)
                if evidence == "Detected":
                    detected_pages.append(page.get("page_number"))
        status = "Detected" if detected_pages else "Missing"
        components.append({
            "component": definition["name"],
            "status": status,
            "page_numbers": detected_pages,
            "detected_pages": format_page_numbers(detected_pages),
        })

    missing = [item["component"] for item in components if item["status"] == "Missing"]
    evidence_count = sum(item["status"] != "Missing" for item in components)
    if evidence_count == 0:
        status = "Failed"
        message = "The uploaded document does not appear to contain a complete Annual Financial Statement."
        suggested_revert_reason = "Incorrect document filed"
    elif missing:
        status = "Failed"
        message = "Missing required AFS component(s): " + ", ".join(missing) + "."
        suggested_revert_reason = "Incomplete pages"
    else:
        status = "Passed"
        message = "All required AFS components were detected."
        suggested_revert_reason = ""
    return {
        "status": status,
        "message": message,
        "suggested_revert_reason": suggested_revert_reason,
        "components": components,
    }


def evaluate_bir_filing(pages: List[Dict]) -> Dict:
    detected_pages = []
    for page in pages:
        text = _page_evidence_text(page)
        has_strong_proof = any(re.search(pattern, text) for pattern in BIR_STRONG_EVIDENCE_PATTERNS)
        if has_strong_proof:
            detected_pages.append(page.get("page_number"))
    if detected_pages:
        status = "Detected"
        message = f"BIR filing/receipt evidence detected on {format_page_numbers(detected_pages)}."
    else:
        status = "Needs Review"
        message = "No filing/receipt-type BIR proof was automatically detected. Generic tax, TIN, and accreditation references are not treated as proof of filing."
    return {
        "status": status,
        "message": message,
        "detected_pages": format_page_numbers(detected_pages),
        "note": "Visual verification of a BIR received stamp is not yet automated in this prototype.",
    }


def analyze_pages(raw_pages: List[Dict], metadata: Dict, company_master: Dict) -> List[Dict]:
    analyzed = []
    company_name = metadata.get("company_name") or company_master.get("company_name", "")
    period_year = int(metadata.get("period_covered_year") or company_master.get("period_covered_year", 0))
    previous_page_type = ""
    previous_page_number = None
    for page in raw_pages:
        text = _processing_text(page)
        page_type = page.get("page_type") or (
            classify_gis_page(text) if is_gis_submission(metadata) else classify_page(text)
        )
        page_number = page.get("page_number")
        if (
            is_gis_submission(metadata)
            and page_type == "Other / Unclassified"
            and previous_page_type in {"Directors / Officers", "Stockholders' Information"}
            and previous_page_number is not None
            and page_number == previous_page_number + 1
            and _gis_continuation_compatible(_gis_text(text).lower(), previous_page_type)
        ):
            page_type = previous_page_type
        flag = page.get("image_quality_flag") or quality_flag(text)
        text_length = page.get("text_length")
        if text_length is None:
            text_length = len(text.strip())
        analyzed.append({
            "page_number": page_number,
            "page_type": page_type,
            "orientation": page.get("orientation", "Portrait"),
            "extracted_text": text,
            "text_preview": page.get("text_preview") or text[:TEXT_PREVIEW_MAX_CHARS],
            "original_text": page.get("original_text", text),
            "ocr_text": page.get("ocr_text", ""),
            "extraction_source": page.get("extraction_source", "Text Layer"),
            "detected_company_match": fuzzy_company_match(text, company_name),
            "detected_period_match": has_period(text, period_year),
            "image_quality_flag": flag,
            "rotation_degrees": page.get("rotation_degrees", page.get("rotation", 0)) or 0,
            "text_length": text_length,
        })
        previous_page_type = page_type
        previous_page_number = page_number
    return analyzed


def validate_document(pages: List[Dict], metadata: Dict, company_master: Dict) -> List[Dict]:
    if is_gis_submission(metadata):
        return validate_gis_document(pages, metadata)
    all_text = "\n".join(_processing_text(page) for page in pages)
    validations = []
    if is_afs_submission(metadata):
        completeness = evaluate_afs_completeness(pages, metadata)
        validations.append({
            "rule_name": "AFS Completeness Check",
            "status": completeness["status"],
            "message": completeness["message"],
            "suggested_revert_reason": completeness["suggested_revert_reason"],
        })
        bir = evaluate_bir_filing(pages)
        validations.append({
            "rule_name": "Proof of BIR Filing",
            "status": bir["status"],
            "message": bir["message"] + " " + bir["note"],
            "suggested_revert_reason": "",
        })
    validations.append(validate_company_master(all_text, metadata, company_master))
    year = int(metadata.get("period_covered_year") or company_master.get("period_covered_year", 0))
    detected_years = detect_afs_reporting_years(pages) if is_afs_submission(metadata) else []
    detected_current = detected_years[0] if detected_years else None
    period_ok = bool(detected_current and year == detected_current)
    period_status = "Passed" if period_ok else "Failed" if detected_current else "Needs Review"
    if period_ok:
        period_message = f"Authoritative AFS period evidence supports {year}. Detected reporting years: {', '.join(map(str, detected_years))}."
    elif detected_current:
        period_message = (
            f"Authoritative AFS period evidence indicates current year {detected_current} "
            f"with reporting years {', '.join(map(str, detected_years))}; Intake Period Year is {year}."
        )
    else:
        period_message = f"No authoritative AFS period heading clearly supports Intake Period Year {year}."
    validations.append({
        "rule_name": "AFS period covered",
        "status": period_status,
        "message": period_message,
        "suggested_revert_reason": "" if period_status != "Failed" else "Wrong period covered",
    })
    intake_comparatives = [int(item) for item in re.findall(r"20\d{2}", str(metadata.get("comparative_years") or ""))]
    detected_comparatives = detected_years[1:] if detected_years else []
    extra_comparatives = [item for item in detected_comparatives if item not in intake_comparatives]
    missing_comparatives = [item for item in intake_comparatives if item not in detected_comparatives]
    if period_ok and (extra_comparatives or missing_comparatives):
        validations.append({
            "rule_name": "AFS comparative years metadata",
            "status": "Needs Review",
            "message": (
                f"Document reporting years include comparatives {', '.join(map(str, detected_comparatives)) or 'none'}, "
                f"while intake metadata specifies {', '.join(map(str, intake_comparatives)) or 'none'}."
            ),
            "suggested_revert_reason": "",
        })
    submission_ok = "financial statements" in all_text.lower() or metadata.get("report_type") == "AFS"
    validations.append({
        "rule_name": "Submission type",
        "status": "Passed" if submission_ok else "Failed",
        "message": "Document content is consistent with Annual Financial Statements." if submission_ok else "Submission type is not clearly consistent with AFS.",
        "suggested_revert_reason": "" if submission_ok else "Wrong submission type",
    })
    landscape_pages = [page for page in pages if page.get("orientation") == "Landscape"]
    validations.append({
        "rule_name": "Orientation review",
        "status": "Warning" if landscape_pages else "Passed",
        "message": f"{len(landscape_pages)} landscape page(s) detected; review if these are legitimate wide financial tables." if landscape_pages else "No landscape pages detected.",
        "suggested_revert_reason": "Wrong page orientation" if landscape_pages else "",
    })
    rotated_pages = [
        page for page in pages
        if int(page.get("rotation_degrees") or 0) in (90, 180, 270)
    ]
    validations.append({
        "rule_name": "Rotation metadata review",
        "status": "Warning" if rotated_pages else "Passed",
        "message": (
            f"Rotation metadata detected on {len(rotated_pages)} page(s); reviewer confirmation is required."
            if rotated_pages
            else "No non-zero PDF rotation metadata detected."
        ),
        "suggested_revert_reason": "",
    })
    quality_failed = [page for page in pages if page.get("image_quality_flag") == "Failed"]
    validations.append({
        "rule_name": "Image readability",
        "status": "Failed" if quality_failed else "Passed",
        "message": f"{len(quality_failed)} page(s) have very low extracted text." if quality_failed else "Extracted text is adequate for MVP review.",
        "suggested_revert_reason": "Poor image quality" if quality_failed else "",
    })
    return validations


def final_recommendation(validations: List[Dict]) -> str:
    statuses = [item.get("status") for item in validations]
    if "Failed" in statuses:
        return "Revert"
    if "Warning" in statuses or "Needs Review" in statuses:
        return "Needs Review"
    return "Accept"


def suggested_revert_reason(validations: List[Dict]) -> str:
    for item in validations:
        if item.get("suggested_revert_reason"):
            return item["suggested_revert_reason"]
    return ""
