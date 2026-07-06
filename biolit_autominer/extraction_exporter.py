"""Export Gemini extraction results to styled Excel in updated/."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import config
from .excel_exporter import (
    ALT_ROW_FILL,
    HEADER_FILL,
    HEADER_FONT,
    WHITE_FILL,
)
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

EXTRACTION_COLUMNS = [
    "Updated time",
    "Source file",
    "Tested chemical",
    "Subject type",
    "Basic information",
    "Exposure method",
    "Marker",
    "Result",
    "Evidence type",
    "Exposure dose",
    "Exposure duration",
    "Tissue/organ",
    "Evidence sentences",
    "Chain of thought for deriving evidence",
    "Annotation (correct?)",
    "Correct answer",
    "Gemini raw output",
]

# Column A–O (main fields): readable widths; column P+ (Gemini raw) stays narrow.
EXTRACTION_COLUMN_WIDTHS = {
    "Updated time": 20,
    "Source file": 32,
    "Tested chemical": 22,
    "Subject type": 14,
    "Basic information": 20,
    "Exposure method": 16,
    "Marker": 14,
    "Result": 20,
    "Evidence type": 16,
    "Exposure dose": 20,
    "Exposure duration": 18,
    "Tissue/organ": 18,
    "Evidence sentences": 60,
    "Chain of thought for deriving evidence": 24,
    "Annotation (correct?)": 18,
    "Correct answer": 30,
    "Gemini raw output": 28,
}

GEMINI_RAW_COLUMN = "Gemini raw output"
DATA_ROW_HEIGHT = 60


def _empty_row(source_file=""):
    return {col: "" for col in EXTRACTION_COLUMNS} | {"Source file": source_file}


def _parse_bracket_line(line):
    """Parse one bracket extraction into Excel columns."""
    line = line.strip()
    if not line.startswith("[") or not line.endswith("]"):
        return None
    parts = [part.strip() for part in line[1:-1].split(";")]
    if len(parts) < 11:
        return None
    return {
        "Source file": "",
        "Tested chemical": parts[0],
        "Subject type": parts[1],
        "Basic information": parts[2],
        "Exposure method": parts[3],
        "Marker": parts[4],
        "Result": parts[5],
        "Evidence type": parts[6],
        "Exposure dose": parts[7],
        "Exposure duration": parts[8],
        "Tissue/organ": parts[9],
        "Evidence sentences": parts[10],
        "Chain of thought for deriving evidence": "",
        "Annotation (correct?)": "",
        "Correct answer": "",
        "Gemini raw output": line,
    }


def rows_from_gemini_text(source_file, gemini_text, chain_of_thought=""):
    rows = []
    for line in gemini_text.splitlines():
        parsed = _parse_bracket_line(line)
        if not parsed:
            continue
        parsed["Source file"] = source_file
        parsed["Chain of thought for deriving evidence"] = chain_of_thought
        rows.append(parsed)
    if not rows and gemini_text.strip():
        row = _empty_row(source_file)
        row["Gemini raw output"] = gemini_text.strip()
        row["Chain of thought for deriving evidence"] = chain_of_thought
        rows.append(row)
    return rows


def _apply_extraction_style(workbook_path, sheet_name="Extractions"):
    wb = load_workbook(workbook_path)
    ws = wb[sheet_name]
    gemini_col_idx = None

    for col_idx in range(1, ws.max_column + 1):
        header = ws.cell(row=1, column=col_idx).value
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if header == GEMINI_RAW_COLUMN:
            gemini_col_idx = col_idx

        width = EXTRACTION_COLUMN_WIDTHS.get(str(header), 18)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    for row_idx in range(2, ws.max_row + 1):
        row_fill = ALT_ROW_FILL if row_idx % 2 == 0 else WHITE_FILL
        ws.row_dimensions[row_idx].height = DATA_ROW_HEIGHT
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = row_fill
            wrap = col_idx != gemini_col_idx
            cell.alignment = Alignment(vertical="top", wrap_text=wrap)

    ws.freeze_panes = "A2"
    wb.save(workbook_path)


def _normalize_existing_columns(existing):
    """Ensure workbook has all columns, with Updated time first."""
    if "Updated time" not in existing.columns:
        existing.insert(0, "Updated time", "")
    for col in EXTRACTION_COLUMNS:
        if col not in existing.columns:
            existing[col] = ""
    return existing[EXTRACTION_COLUMNS]


def export_extraction_workbook(rows, output_path=None, replace_source_files=None):
    output_path = Path(output_path or config.UPDATED_EXTRACTION_XLSX)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        existing = pd.read_excel(output_path)
        existing = _normalize_existing_columns(existing)
    else:
        existing = pd.DataFrame(columns=EXTRACTION_COLUMNS)

    if replace_source_files:
        replace_source_files = set(replace_source_files)
        existing = existing[~existing["Source file"].isin(replace_source_files)]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if rows:
        for row in rows:
            row["Updated time"] = now

    new_df = pd.DataFrame(rows, columns=EXTRACTION_COLUMNS) if rows else pd.DataFrame(columns=EXTRACTION_COLUMNS)
    combined = pd.concat([existing, new_df], ignore_index=True)
    if not combined.empty:
        combined = combined.drop_duplicates(
            subset=["Source file", "Tested chemical", "Marker", "Result", "Evidence sentences"],
            keep="last",
        )

    combined.to_excel(output_path, sheet_name="Extractions", index=False)
    _apply_extraction_style(output_path)
    print(f"Extraction workbook saved to {output_path}")
    return output_path


def build_rows_from_cache(source_file, gemini_path, chain_of_thought_path=None):
    gemini_path = Path(gemini_path)
    if not gemini_path.is_file():
        return []

    gemini_text = gemini_path.read_text(encoding="utf-8")
    chain_text = ""
    if chain_of_thought_path:
        cot_path = Path(chain_of_thought_path)
        if cot_path.is_file():
            chain_text = cot_path.read_text(encoding="utf-8").strip()
    return rows_from_gemini_text(source_file, gemini_text, chain_of_thought=chain_text)
