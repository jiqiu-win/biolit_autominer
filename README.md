# Biolit AutoMiner

Automated Biomedical Literature Mining Pipeline for IEEE 2026 Big Data Conference research.

## Installation

```bash
cd ~/Downloads/biolit_autominer
pip install -e .
cp .env.example .env   # then add your API keys
```

## Quick Start

```bash
python tests/test_setup.py
python run_pipeline.py --num_articles 10
```

## Download priority

1. **PMC full text** via Entrez (saved to `downloads/PMC_full_text/`)
2. **PMC abstract-only** when full text is restricted (same folder, with `[NOTE: ...]` header)
3. **PubMed abstract** only when no PMC record exists (`downloads/Pubmed_abstracts/`)

Saved files follow the naming and format in the `example/` folder.

## Project folder layout

```
biolit_autominer/                     ← project root
│
├── downloads/                        ← raw files (outside auto_pipeline_output)
│   ├── PMC_full_text/                # PMC13240672_42216548.txt
│   └── Pubmed_abstracts/             # PM42217124_abstract.txt
│
├── gemini_raw_cache/                 ← Gemini 2.5 extractions (.txt)
│   ├── PMC_full_text/                # PMC13240672_42216548.txt
│   └── Pubmed_abstracts/             # PM42217124_abstract.txt
│
└── auto_pipeline_output/
    ├── updated/                      ← incrementally updated archive
    │   ├── PMC_full_text_updated/    # PMC13240672_42216548.txt
    │   └── Pubmed_abstracts_updated/ # PM42217124_abstract.txt
    ├── articles.db
    ├── articles_database.xlsx
    └── sync_history.json
```

Gemini output format (`.txt`, one bracket entry per line):

```
[Akkermansia muciniphila; Rodent; (C57BL/6 mice, 5 weeks, male, 20 ± 2 g); oral administration; ALT; decrease; specific doses; -; 4 weeks; serum; (Evidence sentence 1 | Evidence sentence 2)]
```

## Reproducibility

Every run uses `run_pipeline.py` and writes sync metrics to `sync_history.json`.
