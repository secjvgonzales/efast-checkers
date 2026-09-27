import shutil
import sys
import subprocess
from pathlib import Path
import re
from typing import Dict, List, Tuple

import fitz

from config import TEXT_PREVIEW_MAX_CHARS


def quality_flag(text: str) -> str:
    length = len((text or "").strip())
    if length < 25:
        return "Failed"
    if length < 140:
        return "Warning"
    return "Passed"


def normalize_rotation(rotation) -> int:
    try:
        value = int(rotation or 0) % 360
    except (TypeError, ValueError):
        return 0
    return value if value in (0, 90, 180, 270) else 0


def quality_label(text_length: int, flag: str = "") -> str:
    """Return a reviewer-facing preliminary text quality signal."""
    try:
        length = int(text_length or 0)
    except (TypeError, ValueError):
        length = 0
    if flag == "Failed" or length < 25:
        return "Poor Readability"
    if flag == "Warning" or length < 140:
        return "Low Text / Possible Scan"
    return "Readable"


OCR_TRIGGER_TEXT_LENGTH = 140
OCR_RENDER_DPI = 200
OCR_TIMEOUT_SECONDS = 15
OCR_ACCEPTABLE_SCORE = 80
OCR_CLEAR_IMPROVEMENT = 20
OCR_POOR_TEXT_IMPROVEMENT = 10
OCR_MIN_WORDS_FOR_ROTATION = 4
OCR_MIN_ALPHA_RATIO_FOR_ROTATION = 0.25

FINANCIAL_DOCUMENT_TERMS = [
    r"\bconsolidated\b",
    r"\bfinancial\s+statements?\b",
    r"\bstatements?\s+of\b",
    r"\bchanges\s+in\s+equity\b",
    r"\bfinancial\s+position\b",
    r"\bcomprehensive\s+income\b",
    r"\bcash\s+flows?\b",
    r"\bassets?\b",
    r"\bliabilities\b",
    r"\bequity\b",
    r"\brevenue\b",
    r"\bincome\b",
    r"\bretained\s+earnings\b",
    r"\bgeneral\s+information\s+sheet\b",
    r"\bcorporate\s+name\b",
    r"\bsec\s+registration\b",
    r"\bcapital\s+structure\b",
    r"\bdirectors?\b",
    r"\bofficers?\b",
    r"\bstockholders?\b",
    r"\bauthorized\s+capital\b",
    r"\bsubscribed\s+capital\b",
    r"\bpaid[-\s]?up\s+capital\b",
    r"\bcorporate\s+secretary\b",
    r"\bsubscribed\s+and\s+sworn\b",
    r"\bnotary\s+public\b",
]


def _usable_text_score(text: str) -> int:
    return sum(character.isalnum() for character in (text or ""))


def _ocr_text_quality(text: str) -> Dict[str, float]:
    """Score OCR readability with deterministic text-shape signals only."""
    value = (text or "").strip()
    if not value:
        return {
            "score": 0.0,
            "word_count": 0,
            "long_word_count": 0,
            "line_count": 0,
            "printable_ratio": 0.0,
            "alpha_ratio": 0.0,
        }
    non_space = [character for character in value if not character.isspace()]
    printable_count = sum(character.isprintable() for character in value)
    alpha_count = sum(character.isalpha() for character in non_space)
    symbol_count = sum(not character.isalnum() for character in non_space)
    words = re.findall(r"[A-Za-z]{2,}", value)
    long_words = re.findall(r"[A-Za-z]{4,}", value)
    line_count = sum(1 for line in value.splitlines() if line.strip())
    printable_ratio = printable_count / len(value)
    alpha_ratio = alpha_count / len(non_space) if non_space else 0.0
    symbol_ratio = symbol_count / len(non_space) if non_space else 0.0
    score = (
        len(words) * 3
        + len(long_words) * 2
        + line_count
        + printable_ratio * 20
        + alpha_ratio * 20
    )
    if symbol_ratio > 0.45:
        score -= (symbol_ratio - 0.45) * 40
    score -= value.count("\ufffd") * 10
    return {
        "score": max(score, 0.0),
        "word_count": len(words),
        "long_word_count": len(long_words),
        "line_count": line_count,
        "printable_ratio": printable_ratio,
        "alpha_ratio": alpha_ratio,
    }


def _ocr_semantic_score(text: str) -> float:
    value = (text or "").strip()
    if not value:
        return 0.0
    lowered = value.lower()
    words = re.findall(r"[A-Za-z]{3,}", value)
    if not words:
        return 0.0
    common_word_count = sum(
        1
        for word in words
        if re.fullmatch(
            r"(?i)(the|and|for|with|from|income|total|equity|cash|capital|stock|retained|financial|statements|consolidated|company|comprehensive|assets|liabilities|revenue|years|ended)",
            word,
        )
    )
    term_score = sum(30 for pattern in FINANCIAL_DOCUMENT_TERMS if re.search(pattern, lowered))
    long_noise = len(re.findall(r"[A-Za-z]{14,}", value))
    table_noise = value.count("|") + value.count("~") + value.count("=")
    quality = _ocr_text_quality(value)
    return (
        term_score
        + common_word_count * 4
        + min(quality["word_count"], 80)
        + quality["printable_ratio"] * 20
        - long_noise * 8
        - table_noise * 1.5
    )


def _ocr_text_is_acceptable(text: str) -> bool:
    quality = _ocr_text_quality(text)
    return (
        quality["score"] >= OCR_ACCEPTABLE_SCORE
        and quality["word_count"] >= OCR_MIN_WORDS_FOR_ROTATION
        and quality["alpha_ratio"] >= OCR_MIN_ALPHA_RATIO_FOR_ROTATION
    )


def _candidate_is_clear_improvement(candidate_text: str, baseline_text: str) -> bool:
    candidate = _ocr_text_quality(candidate_text)
    baseline = _ocr_text_quality(baseline_text)
    if baseline["score"] < OCR_POOR_TEXT_IMPROVEMENT:
        return candidate["score"] >= baseline["score"] + OCR_POOR_TEXT_IMPROVEMENT
    return (
        candidate["score"] >= baseline["score"] + OCR_CLEAR_IMPROVEMENT
        and candidate["word_count"] >= OCR_MIN_WORDS_FOR_ROTATION
        and candidate["alpha_ratio"] >= OCR_MIN_ALPHA_RATIO_FOR_ROTATION
    )


def _ocr_page_text_with_rotation_selection(page, baseline_rotation: int) -> Tuple[str, str]:
    best_text = ""
    best_error = ""
    best_score = -1.0
    baseline_text = ""
    baseline_error = ""
    rotations = []
    for rotation in (baseline_rotation, 0, 90, 180, 270):
        if rotation not in rotations:
            rotations.append(rotation)
    for index, candidate_rotation in enumerate(rotations):
        candidate_text, candidate_error = _ocr_page_text(page, candidate_rotation)
        if index == 0:
            baseline_text = (candidate_text or "").strip()
            baseline_error = candidate_error
            if _ocr_text_is_acceptable(baseline_text) and _ocr_semantic_score(baseline_text) >= 120:
                return baseline_text, baseline_error
        candidate_text = (candidate_text or "").strip()
        candidate_score = _ocr_semantic_score(candidate_text)
        if candidate_score > best_score:
            best_text = candidate_text
            best_error = candidate_error
            best_score = candidate_score

    if best_text and (
        _candidate_is_clear_improvement(best_text, baseline_text)
        or _ocr_semantic_score(best_text) >= _ocr_semantic_score(baseline_text) + 60
    ):
        return best_text, best_error
    return baseline_text, baseline_error


def _ocr_page_text(page, rotation: int) -> Tuple[str, str]:
    """Render one low-text page and run bounded Tesseract OCR on the image."""
    if not shutil.which("tesseract"):
        return "", "Tesseract is not available in the current environment."
    try:
        scale = OCR_RENDER_DPI / 72
        matrix = fitz.Matrix(scale, scale)
        # Normalize the pixels with the inverse of the PDF rotation metadata.
        # This is metadata-based only; no visual orientation detection is used.
        if rotation:
            matrix = matrix.prerotate(-rotation)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "6"],
            input=pixmap.tobytes("png"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if result.returncode != 0 and not text:
            error = result.stderr.decode("utf-8", errors="replace").strip()
            return "", error or f"Tesseract exited with status {result.returncode}."
        return text, ""
    except subprocess.TimeoutExpired:
        return "", f"Tesseract timed out after {OCR_TIMEOUT_SECONDS} seconds."
    except Exception as exc:
        return "", f"OCR fallback failed: {exc}"


def _apply_ocr_fallback(page, text: str) -> Tuple[str, str, str, str, str]:
    """Return effective text plus original/OCR text and source label."""
    original_text = text or ""
    ocr_text = ""
    extraction_source = "Text Layer"
    if len(original_text.strip()) >= OCR_TRIGGER_TEXT_LENGTH:
        return original_text, original_text, ocr_text, extraction_source, ""

    rotation = normalize_rotation(getattr(page, "rotation", 0))
    ocr_text, ocr_error = _ocr_page_text_with_rotation_selection(page, rotation)
    if _usable_text_score(ocr_text) > _usable_text_score(original_text):
        return ocr_text, original_text, ocr_text, "OCR Fallback", ocr_error
    return original_text, original_text, ocr_text, extraction_source, ocr_error


def extract_pdf_pages(file_path: Path) -> Tuple[List[Dict], List[str]]:
    """
    Extract pages from a PDF file.

    Returns a tuple of (pages, errors) where errors is a list of human-readable
    messages describing any parser failures that occurred. pages may be non-empty
    even when errors is non-empty (partial extraction via fallback).
    """
    errors: List[str] = []
    pages: List[Dict] = []

    try:
        import fitz
        document = fitz.open(str(file_path))
        for index, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            effective_text, original_text, ocr_text, extraction_source, ocr_error = _apply_ocr_fallback(page, text)
            if ocr_error:
                errors.append(f"Page {index} OCR fallback issue: {ocr_error}")
            rect = page.rect
            orientation = "Landscape" if rect.width > rect.height else "Portrait"
            pages.append({
                "page_number": index,
                "text": effective_text,
                "extracted_text": effective_text,
                "text_preview": effective_text[:TEXT_PREVIEW_MAX_CHARS],
                "original_text": original_text,
                "ocr_text": ocr_text,
                "extraction_source": extraction_source,
                "orientation": orientation,
                "rotation_degrees": normalize_rotation(getattr(page, "rotation", 0)),
                "text_length": len(effective_text.strip()),
                "width": rect.width,
                "height": rect.height,
            })
        document.close()
    except Exception as exc:
        msg = f"PyMuPDF extraction failed: {exc}"
        print(msg, file=sys.stderr)
        errors.append(msg)
        pages = []

    if pages:
        return pages, errors

    try:
        import pdfplumber
        with pdfplumber.open(str(file_path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                orientation = "Landscape" if page.width > page.height else "Portrait"
                pages.append({
                    "page_number": index,
                    "text": text,
                    "extracted_text": text,
                    "text_preview": text[:TEXT_PREVIEW_MAX_CHARS],
                "original_text": text,
                "ocr_text": "",
                "extraction_source": "Text Layer",
                    "orientation": orientation,
                    "rotation_degrees": normalize_rotation(getattr(page, "rotation", 0)),
                    "text_length": len(text.strip()),
                    "width": page.width,
                    "height": page.height,
                })
    except Exception as exc:
        msg = f"pdfplumber extraction failed: {exc}"
        print(msg, file=sys.stderr)
        errors.append(msg)
        pages = []

    return pages, errors


def prepare_uploaded_file(uploaded_file, uploads_dir: Path) -> Path:
    uploads_dir.mkdir(parents=True, exist_ok=True)
    target = uploads_dir / uploaded_file.name
    target.write_bytes(uploaded_file.getbuffer())
    return target
