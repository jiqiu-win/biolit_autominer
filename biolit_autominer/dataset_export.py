"""Export the consolidated articles.db (articles + findings tables) to one
spreadsheet -- Articles, Findings, About. Always a fresh, on-demand read
straight from the database, so it can never drift out of sync with it."""

from datetime import datetime

import pandas as pd
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from .excel_exporter import ALT_ROW_FILL, HEADER_FILL, HEADER_FONT, WHITE_FILL

ARTICLES_COLUMNS = [
    "PMID", "PMCID", "Title", "Authors", "Journal", "Publish date", "Source",
    "Full text?", "Downloaded at", "Extracted date", "Gemini processed",
    "Download status", "Download error", "Extraction error",
    "PubMed URL", "PMC URL",
]

FINDINGS_COLUMNS = [
    "Finding ID", "PMCID", "PMID", "Tested chemical", "Subject type",
    "Basic information", "Exposure method", "Marker", "Result", "Evidence type",
    "Exposure dose", "Exposure duration", "Tissue/organ", "Evidence sentences",
]

ARTICLES_WIDTHS = {
    "PMID": 12, "PMCID": 14, "Title": 45, "Authors": 30, "Journal": 22,
    "Publish date": 14, "Source": 16, "Full text?": 10, "Downloaded at": 18,
    "Extracted date": 18, "Gemini processed": 14, "Download status": 14,
    "Download error": 30, "Extraction error": 30, "PubMed URL": 32, "PMC URL": 32,
}
FINDINGS_WIDTHS = {
    "Finding ID": 10, "PMCID": 14, "PMID": 12, "Tested chemical": 20,
    "Subject type": 14, "Basic information": 20, "Exposure method": 16,
    "Marker": 14, "Result": 16, "Evidence type": 16, "Exposure dose": 18,
    "Exposure duration": 16, "Tissue/organ": 16, "Evidence sentences": 60,
}


def _pubmed_url(pmid):
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""


def _pmc_url(pmcid):
    return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""


def build_articles_df(db):
    conn = db._connect()
    conn.row_factory = None
    rows = conn.execute(
        """
        SELECT pmid, pmcid, title, authors, journal, pub_date, source, has_full_text,
               created_at, updated_at, gemini_processed, download_status,
               download_error, extraction_error
        FROM articles ORDER BY pmid
        """
    ).fetchall()
    conn.close()

    records = []
    for (pmid, pmcid, title, authors, journal, pub_date, source, has_full_text,
         created_at, updated_at, gemini_processed, download_status,
         download_error, extraction_error) in rows:
        records.append({
            "PMID": pmid,
            "PMCID": pmcid,
            "Title": title,
            "Authors": authors,
            "Journal": journal,
            "Publish date": pub_date,
            "Source": source,
            "Full text?": "Yes" if has_full_text else "No",
            "Downloaded at": created_at,
            "Extracted date": updated_at if gemini_processed else "",
            "Gemini processed": "Yes" if gemini_processed else "No",
            "Download status": download_status or "",
            "Download error": download_error or "",
            "Extraction error": extraction_error or "",
            "PubMed URL": _pubmed_url(pmid),
            "PMC URL": _pmc_url(pmcid),
        })
    return pd.DataFrame(records, columns=ARTICLES_COLUMNS)


def build_findings_df(db):
    conn = db._connect()
    rows = conn.execute(
        """
        SELECT f.id, a.pmcid, f.pmid, f.tested_chemical, f.subject_type,
               f.basic_information, f.exposure_method, f.marker, f.result,
               f.evidence_type, f.exposure_dose, f.exposure_duration,
               f.tissue_organ, f.evidence_sentences
        FROM findings f
        LEFT JOIN articles a ON f.pmid = a.pmid
        ORDER BY f.pmid, f.id
        """
    ).fetchall()
    conn.close()

    records = []
    for (finding_id, pmcid, pmid, chem, subj, info, method, marker, result,
         etype, dose, duration, tissue, evidence) in rows:
        records.append({
            "Finding ID": finding_id, "PMCID": pmcid, "PMID": pmid,
            "Tested chemical": chem, "Subject type": subj, "Basic information": info,
            "Exposure method": method, "Marker": marker, "Result": result,
            "Evidence type": etype, "Exposure dose": dose,
            "Exposure duration": duration, "Tissue/organ": tissue,
            "Evidence sentences": evidence,
        })
    return pd.DataFrame(records, columns=FINDINGS_COLUMNS)


def _style_sheet(ws, column_widths, data_row_height=45):
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_idx in range(1, ws.max_column + 1):
        header = ws.cell(row=1, column=col_idx).value
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = header_alignment
        ws.column_dimensions[get_column_letter(col_idx)].width = column_widths.get(str(header), 18)

    wrap_alignment = Alignment(vertical="top", wrap_text=True)
    for row_idx, row_cells in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
        row_fill = ALT_ROW_FILL if row_idx % 2 == 0 else WHITE_FILL
        ws.row_dimensions[row_idx].height = data_row_height
        for cell in row_cells:
            cell.fill = row_fill
            cell.alignment = wrap_alignment
    ws.freeze_panes = "A2"


def _write_about_sheet(wb, article_count, finding_count, sync_time):
    ws = wb.create_sheet("About", 0)
    lines = [
        ("Biolit AutoMiner — Toxicology Dataset", ""),
        ("", ""),
        ("Description", "Hepatotoxicity & mitochondrial toxicity literature dataset"),
        ("Extraction model", "Gemini 2.5 via Vertex AI"),
        ("Last exported", sync_time),
        ("Total articles", article_count),
        ("Total findings (rows)", finding_count),
        ("", ""),
        ("Structure", "One consolidated database: articles + findings, linked by PMID"),
        ("Sheets", ""),
        ("  Articles", "One row per article -- metadata, download status, extraction status"),
        ("  Findings", "One row per extracted finding. Join to Articles on PMID."),
        ("", ""),
        ("Key columns", ""),
        ("  Download status / error", "ok / failed / not_applicable -- traces download-side problems"),
        ("  Gemini processed / Extraction error", "whether extraction succeeded, and why if it didn't"),
        ("  Downloaded at / Extracted date", "when the article was obtained vs. when Gemini finished it"),
        ("", ""),
        ("Covers", "Both the backlog batches and the daily new-article pipeline"),
        ("Source database", "articles.db (single consolidated database)"),
    ]
    for row_idx, (label, value) in enumerate(lines, start=1):
        ws.cell(row=row_idx, column=1, value=label)
        ws.cell(row=row_idx, column=2, value=value)
        if row_idx == 1:
            ws.cell(row=row_idx, column=1).font = Font(bold=True, size=14, color="1F4E79")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 70


def export_dataset(db, output_path):
    articles_df = build_articles_df(db)
    findings_df = build_findings_df(db)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        articles_df.to_excel(writer, sheet_name="Articles", index=False)
        findings_df.to_excel(writer, sheet_name="Findings", index=False)

    from openpyxl import load_workbook
    wb = load_workbook(output_path)
    _style_sheet(wb["Articles"], ARTICLES_WIDTHS)
    _style_sheet(wb["Findings"], FINDINGS_WIDTHS, data_row_height=60)
    _write_about_sheet(wb, len(articles_df), len(findings_df), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    wb.save(output_path)
    print(f"Dataset exported to {output_path}: {len(articles_df)} articles, {len(findings_df)} findings")
    return output_path
