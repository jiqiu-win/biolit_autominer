"""Styled Excel export matching example/full_text_extraction_1001.xlsx."""

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Columns removed from export (original SQLite names)
EXCLUDED_COLUMNS = {
    "authors",
    "journal",
    "source",
    "gemini_processed",
    "gemini_result",
    "created_at",
    "abstract",
    "local_file_path",
}

HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF")
ALT_ROW_FILL = PatternFill(fill_type="solid", fgColor="F5F5F5")
WHITE_FILL = PatternFill(fill_type="solid", fgColor="FFFFFF")

EXAMPLE_STYLE_PATH = Path(__file__).resolve().parent.parent / "example" / "full_text_extraction_1001.xlsx"


def capitalize_column(name):
    name = str(name)
    return name[:1].upper() + name[1:] if name else name


def _column_widths_from_example(num_columns):
    default_widths = [32, 22, 18, 18, 18, 18, 18, 18, 18, 18]
    if EXAMPLE_STYLE_PATH.exists():
        wb = load_workbook(EXAMPLE_STYLE_PATH)
        ws = wb.active
        widths = []
        for idx in range(1, num_columns + 1):
            letter = get_column_letter(idx)
            width = ws.column_dimensions[letter].width if letter in ws.column_dimensions else None
            if width is None and idx <= len(default_widths):
                width = default_widths[idx - 1]
            widths.append(width or 18)
        wb.close()
        return widths
    return default_widths[:num_columns] + [18] * max(0, num_columns - len(default_widths))


def export_articles_to_excel(df, output_path, sheet_name="Articles"):
    """Export articles dataframe with example workbook styling."""
    df = df[[col for col in df.columns if col not in EXCLUDED_COLUMNS]].copy()
    df.columns = [capitalize_column(col) for col in df.columns]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, sheet_name=sheet_name, index=False)

    wb = load_workbook(output_path)
    ws = wb[sheet_name]

    for col_idx, column_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx in range(2, ws.max_row + 1):
        row_fill = ALT_ROW_FILL if row_idx % 2 == 0 else WHITE_FILL
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = row_fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    widths = _column_widths_from_example(ws.max_column)
    for col_idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = "A2"
    wb.save(output_path)
    return output_path
