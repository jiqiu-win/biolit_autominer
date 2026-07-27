"""
Build a full-text extraction workbook in the standard review format.

Reproduces the layout and styling of full_text_extraction_1001.xlsx:
  - 15 columns (extraction fields + annotation columns for the reviewer)
  - styled header (dark-blue background, white bold Arial)
  - alternating row shading, wrapped text, frozen header row

Requirements:
  pip install openpyxl

Usage (fill with your own rows):
  from build_extraction_workbook import build_extraction_workbook, COLUMNS

  rows = [
      {"Source file": "...", "Tested chemical": "...", "Subject type": "...", ...},
      # one dict per finding; keys are the COLUMNS names below
  ]
  build_extraction_workbook(rows, "full_text_extraction.xlsx")

You can also build an empty template (header only) with rows=[].
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Column order (exactly matches full_text_extraction_1001.xlsx)
COLUMNS = [
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
    "Annotation (correct?)",   # reviewer marks yes/no
    "Correct answer",          # reviewer's fix if wrong
    "Gemini raw output",       # original model output for reference
]

# Column widths (Excel units)
COLUMN_WIDTHS = {
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
    "Annotation (correct?)": 18,
    "Correct answer": 30,
    "Gemini raw output": 50,
}

# Styling
HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E79")   # dark blue
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

DATA_FONT = Font(name="Arial", size=9)
DATA_ALIGN = Alignment(vertical="center", wrap_text=True)
ALT_FILL = PatternFill(fill_type="solid", fgColor="F5F5F5")      # even rows (light gray)
WHITE_FILL = PatternFill(fill_type="solid", fgColor="FFFFFF")    # odd rows (white)


def build_extraction_workbook(rows, output_path, sheet_name="Sheet1"):
    """
    rows: list of dicts (keys = COLUMNS) OR list of lists (values in COLUMNS order).
          Pass [] for an empty template with just the styled header.
    output_path: where to save the .xlsx
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    # --- header row ---
    for col_idx, name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        ws.column_dimensions[get_column_letter(col_idx)].width = COLUMN_WIDTHS.get(name, 18)

    # --- data rows ---
    for r, row in enumerate(rows, start=2):
        fill = ALT_FILL if r % 2 == 0 else WHITE_FILL   # row 2 gray, row 3 white, ...
        for col_idx, name in enumerate(COLUMNS, start=1):
            if isinstance(row, dict):
                value = row.get(name, "")
            else:
                value = row[col_idx - 1] if col_idx - 1 < len(row) else ""
            cell = ws.cell(row=r, column=col_idx, value=value)
            cell.font = DATA_FONT
            cell.fill = fill
            cell.alignment = DATA_ALIGN

    ws.freeze_panes = "A2"   # keep header visible when scrolling
    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    # Demo: one example finding + an empty annotation template.
    example = [
        {
            "Source file": "PMC11421952_39318637_Example.txt",
            "Tested chemical": "Acetaminophen",
            "Subject type": "Rodent",
            "Basic information": "(C57BL/6 mice, 8 weeks, male)",
            "Exposure method": "oral gavage",
            "Marker": "ALT",
            "Result": "increase",
            "Evidence type": "specific doses",
            "Exposure dose": "(300 mg/kg)",
            "Exposure duration": "(24 h)",
            "Tissue/organ": "(liver)",
            "Evidence sentences": "(Serum ALT levels were significantly elevated at 300 mg/kg.)",
            "Annotation (correct?)": "",
            "Correct answer": "",
            "Gemini raw output": "[Acetaminophen; Rodent; ...]",
        }
    ]
    build_extraction_workbook(example, "full_text_extraction_demo.xlsx")
    build_extraction_workbook([], "full_text_extraction_template.xlsx")  # header-only template
    print("Wrote full_text_extraction_demo.xlsx and full_text_extraction_template.xlsx")
