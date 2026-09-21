import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import DB_PATH, DATA_DIR


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        company_name TEXT,
        sec_registration_no TEXT,
        report_type TEXT,
        period_covered_year INTEGER,
        comparative_years TEXT,
        submission_type TEXT,
        filing_year INTEGER,
        uploaded_at TEXT,
        corporation_type TEXT,
        period_covered TEXT,
        gis_bod_routing_page INTEGER
    );
    CREATE TABLE IF NOT EXISTS company_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        sec_registration_no TEXT,
        period_covered_year INTEGER,
        comparative_years TEXT
    );
    CREATE TABLE IF NOT EXISTS page_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER,
        page_number INTEGER,
        page_type TEXT,
        orientation TEXT,
        text_preview TEXT,
        detected_company_match INTEGER,
        detected_period_match INTEGER,
        image_quality_flag TEXT,
        rotation_degrees INTEGER DEFAULT 0,
        text_length INTEGER DEFAULT 0,
        extracted_text TEXT,
        original_text TEXT,
        ocr_text TEXT,
        extraction_source TEXT DEFAULT 'Text Layer'
    );
    CREATE TABLE IF NOT EXISTS validations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER,
        rule_name TEXT,
        status TEXT,
        message TEXT,
        suggested_revert_reason TEXT
    );
    CREATE TABLE IF NOT EXISTS extracted_figures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER,
        page_number INTEGER,
        statement_type TEXT,
        raw_label TEXT,
        normalized_label TEXT,
        fiscal_year INTEGER,
        displayed_value TEXT,
        normalized_peso_value REAL,
        unit_basis TEXT,
        source_snippet TEXT,
        reviewer_edited INTEGER DEFAULT 0,
        reviewed_value TEXT,
        review_status TEXT,
        confidence REAL
    );
    CREATE TABLE IF NOT EXISTS reviewer_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER UNIQUE,
        reviewer_remarks TEXT,
        final_recommendation TEXT,
        final_revert_reason TEXT,
        updated_at TEXT
    );
    """)
    page_columns = {row[1] for row in cur.execute("PRAGMA table_info(page_analysis)").fetchall()}
    if "rotation_degrees" not in page_columns:
        cur.execute("ALTER TABLE page_analysis ADD COLUMN rotation_degrees INTEGER DEFAULT 0")
    if "text_length" not in page_columns:
        cur.execute("ALTER TABLE page_analysis ADD COLUMN text_length INTEGER DEFAULT 0")
    if "extracted_text" not in page_columns:
        cur.execute("ALTER TABLE page_analysis ADD COLUMN extracted_text TEXT")
    if "original_text" not in page_columns:
        cur.execute("ALTER TABLE page_analysis ADD COLUMN original_text TEXT")
    if "ocr_text" not in page_columns:
        cur.execute("ALTER TABLE page_analysis ADD COLUMN ocr_text TEXT")
    if "extraction_source" not in page_columns:
        cur.execute("ALTER TABLE page_analysis ADD COLUMN extraction_source TEXT DEFAULT 'Text Layer'")
    cur.execute(
        """
        UPDATE page_analysis
        SET extracted_text = CASE
            WHEN extraction_source = 'OCR Fallback' AND COALESCE(ocr_text, '') != '' THEN ocr_text
            WHEN COALESCE(original_text, '') != '' THEN original_text
            WHEN COALESCE(text_preview, '') != '' THEN text_preview
            ELSE ''
        END
        WHERE extracted_text IS NULL OR extracted_text = ''
        """
    )
    document_columns = {row[1] for row in cur.execute("PRAGMA table_info(documents)").fetchall()}
    if "corporation_type" not in document_columns:
        cur.execute("ALTER TABLE documents ADD COLUMN corporation_type TEXT")
    if "period_covered" not in document_columns:
        cur.execute("ALTER TABLE documents ADD COLUMN period_covered TEXT")
    if "gis_bod_routing_page" not in document_columns:
        cur.execute("ALTER TABLE documents ADD COLUMN gis_bod_routing_page INTEGER")
    conn.commit()
    conn.close()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def query(sql: str, params: Iterable[Any] = ()) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def insert_document(metadata: Dict[str, Any]) -> int:
    return execute(
        """
        INSERT INTO documents (
            filename, company_name, sec_registration_no, report_type, period_covered_year,
            comparative_years, submission_type, filing_year, uploaded_at,
            corporation_type, period_covered, gis_bod_routing_page
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metadata.get("filename"), metadata.get("company_name"), metadata.get("sec_registration_no"),
            metadata.get("report_type"), metadata.get("period_covered_year"), metadata.get("comparative_years"),
            metadata.get("submission_type"), metadata.get("filing_year"), datetime.now().isoformat(timespec="seconds"),
            metadata.get("corporation_type"), metadata.get("period_covered"), metadata.get("gis_bod_routing_page"),
        ),
    )


def replace_document_analysis(document_id: int, pages: List[Dict], validations: List[Dict], figures: List[Dict]) -> None:
    conn = get_connection()
    cur = conn.cursor()
    for table in ["page_analysis", "validations", "extracted_figures"]:
        cur.execute(f"DELETE FROM {table} WHERE document_id = ?", (document_id,))
    for page in pages:
        extraction_source = page.get("extraction_source", "Text Layer")
        extracted_text = page.get("extracted_text") or page.get("text")
        if not extracted_text:
            if extraction_source == "OCR Fallback" and page.get("ocr_text"):
                extracted_text = page.get("ocr_text")
            else:
                extracted_text = page.get("original_text") or page.get("text_preview", "")
        cur.execute(
            """
            INSERT INTO page_analysis (
                document_id, page_number, page_type, orientation, text_preview,
                detected_company_match, detected_period_match, image_quality_flag,
                rotation_degrees, text_length, extracted_text, original_text, ocr_text, extraction_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                page.get("page_number"),
                page.get("page_type"),
                page.get("orientation"),
                page.get("text_preview"),
                int(bool(page.get("detected_company_match"))),
                int(bool(page.get("detected_period_match"))),
                page.get("image_quality_flag"),
                page.get("rotation_degrees", page.get("rotation", 0)) or 0,
                page.get("text_length", len(str(page.get("text_preview") or "").strip())),
                extracted_text,
                page.get("original_text", page.get("text_preview", "")),
                page.get("ocr_text", ""),
                extraction_source,
            ),
        )
    for item in validations:
        cur.execute(
            """
            INSERT INTO validations (document_id, rule_name, status, message, suggested_revert_reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (document_id, item.get("rule_name"), item.get("status"), item.get("message"), item.get("suggested_revert_reason")),
        )
    for fig in figures:
        cur.execute(
            """
            INSERT INTO extracted_figures (document_id, page_number, statement_type, raw_label, normalized_label, fiscal_year, displayed_value, normalized_peso_value, unit_basis, source_snippet, reviewer_edited, reviewed_value, review_status, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, fig.get("page_number"), fig.get("statement_type"), fig.get("raw_label"), fig.get("normalized_label"), fig.get("fiscal_year"), fig.get("displayed_value"), fig.get("normalized_peso_value"), fig.get("unit_basis"), fig.get("source_snippet"), int(bool(fig.get("reviewer_edited", False))), fig.get("reviewed_value", ""), fig.get("review_status") or fig.get("status", "Needs Review"), fig.get("confidence", 0.8)),
        )
    conn.commit()
    conn.close()


def delete_document_records(document_id: int) -> bool:
    """Delete one document and all dependent analysis/reviewer rows atomically."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        for table in ["reviewer_actions", "extracted_figures", "validations", "page_analysis"]:
            cur.execute(f"DELETE FROM {table} WHERE document_id = ?", (document_id,))
        cur.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        deleted = cur.rowcount > 0
        if deleted:
            conn.commit()
        else:
            conn.rollback()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_reviewer_action(document_id: int, remarks: str, recommendation: str, revert_reason: str) -> None:
    existing = query("SELECT id FROM reviewer_actions WHERE document_id = ?", (document_id,))
    if existing:
        execute(
            """
            UPDATE reviewer_actions
            SET reviewer_remarks = ?, final_recommendation = ?, final_revert_reason = ?, updated_at = ?
            WHERE document_id = ?
            """,
            (remarks, recommendation, revert_reason, datetime.now().isoformat(timespec="seconds"), document_id),
        )
    else:
        execute(
            """
            INSERT INTO reviewer_actions (document_id, reviewer_remarks, final_recommendation, final_revert_reason, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (document_id, remarks, recommendation, revert_reason, datetime.now().isoformat(timespec="seconds")),
        )


def update_gis_bod_routing(document_id: int, page_number: Optional[int]) -> None:
    execute(
        "UPDATE documents SET gis_bod_routing_page = ? WHERE id = ?",
        (page_number, document_id),
    )


def update_figure_reviews(document_id: int, rows: List[Dict]) -> None:
    conn = get_connection()
    cur = conn.cursor()
    for row in rows:
        figure_id = row.get("id")
        if not figure_id:
            continue
        edited = str(row.get("reviewed_value") or "").strip() not in ["", str(row.get("displayed_value") or "").strip()]
        cur.execute(
            """
            UPDATE extracted_figures
            SET reviewed_value = ?, reviewer_edited = ?, review_status = ?
            WHERE id = ? AND document_id = ?
            """,
            (row.get("reviewed_value", ""), int(edited), row.get("review_status", "Needs Review"), figure_id, document_id),
        )
    conn.commit()
    conn.close()


def latest_document_id() -> Optional[int]:
    rows = query("SELECT id FROM documents ORDER BY id DESC LIMIT 1")
    return rows[0]["id"] if rows else None
