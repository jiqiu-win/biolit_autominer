"""
PubMed search query and Gemini extraction prompt.

Source: Auto_pipeline_complete.ipynb — do not edit here unless the notebook is updated.
"""

from datetime import datetime, timedelta

BATCH_SIZE   = 200

MAX_RESULTS  = 9999
RETMAX_FETCH = 200


# Search query
markers = (
    '"ALT"[tiab] OR ' +
    '"LDH"[tiab] OR ' +
    '"alanine aminotransferase"[tiab] OR ' +
    '"AST"[tiab] OR ' +
    '"aspartate aminotransferase"[tiab] OR ' +
    '"ALP"[tiab] OR ' +
    '"alkaline phosphatase"[tiab] OR ' +
    '"bilirubin"[tiab] OR ' +
    '"albumin"[tiab] OR ' +
    '"ROS"[tiab] OR ' +
    '"MDA"[tiab] OR ' +
    '"TNF-alpha"[tiab] OR ' +
    '"IL-6"[tiab] OR ' +
    '"apoptosis"[tiab] OR ' +
    '"necrosis"[tiab] OR ' +
    '"mitochondrial dysfunction"[tiab] OR ' +
    '"mitochondrial damage"[tiab] OR ' +
    '"mitochondrial injury"[tiab] OR ' +
    '"mitochondrial toxicity"[tiab] OR ' +
    '"mitochondrial impairment"[tiab] OR ' +
    '"ATP"[tiab] OR ' +
    '"mitochondrial membrane potential"[tiab] OR ' +
    '"MMP"[tiab] OR ' +
    '"mitochondrial depolarization"[tiab] OR ' +
    '"mitochondrial polarization"[tiab] OR ' +
    '"Rhodamine 123"[tiab] OR ' +
    '"mitochondrial ROS"[tiab] OR ' +
    '"mtROS"[tiab] OR ' +
    '"MitoSOX"[tiab] OR ' +
    '"electron transport chain"[tiab] OR ' +
    '"ETC"[tiab] OR ' +
    '"respiratory chain"[tiab] OR ' +
    '"mitochondrial respiration"[tiab] OR ' +
    '"oxygen consumption rate"[tiab] OR ' +
    '"OCR"[tiab] OR ' +
    '"mitochondrial permeability transition"[tiab] OR ' +
    '"MPT"[tiab] OR ' +
    '"mPTP"[tiab] OR ' +
    '"cytochrome c release"[tiab]'
)

subjects = (
    '"cell"[tiab] OR ' +
    '"cells"[tiab] OR ' +
    '"rat"[tiab] OR ' +
    '"rats"[tiab] OR ' +
    '"mouse"[tiab] OR ' +
    '"mice"[tiab] OR ' +
    '"zebrafish"[tiab] OR ' +
    '"urine"[tiab] OR ' +
    '"urinary"[tiab] OR ' +
    '"serum"[tiab] OR ' +
    '"blood"[tiab] OR ' +
    '"plasma"[tiab]'
)

topics = (
    '"hepatotoxicity"[tiab] OR ' +
    '"hepatic toxicity"[tiab] OR ' +
    '"liver toxicity"[tiab] OR ' +
    '"liver injury"[tiab] OR ' +
    '"hepatic injury"[tiab] OR ' +
    '"liver damage"[tiab] OR ' +
    '"hepatic damage"[tiab] OR ' +
    '"drug-induced liver injury"[tiab] OR ' +
    '"DILI"[tiab] OR ' +
    '"hepatocyte toxicity"[tiab] OR ' +
    '"hepatocyte injury"[tiab] OR ' +
    '"hepatocellular injury"[tiab] OR ' +
    '"hepatocellular damage"[tiab] OR ' +
    '"hepatocyte apoptosis"[tiab] OR ' +
    '"hepatocyte necrosis"[tiab] OR ' +
    '"hepatocyte cytotoxicity"[tiab] OR ' +
    '"steatosis"[tiab] OR ' +
    '"cholestasis"[tiab] OR ' +
    '"liver fibrosis"[tiab]'
)

# Rolling window relative to whenever this module is imported (a fresh process
# each day via scrontab), not a fixed calendar range -- the old hardcoded dates
# meant the daily search silently found 0 articles once "today" moved past them.
# 30-day lookback gives buffer against PubMed indexing lag or a missed run;
# already-downloaded articles get skipped by the existing dedup logic regardless.
_today = datetime.now()
_lookback_start = _today - timedelta(days=30)
date_filter = f"{_lookback_start.strftime('%Y/%m/%d')}:{_today.strftime('%Y/%m/%d')}[dp]"
article_filter = '"journal article"[pt]'
lang_filter    = 'English[la]'

exclusions = (
    'NOT ("nanoparticle"[tiab] OR "nanoparticles"[tiab] OR '
    '"microplastic"[tiab] OR "microplastics"[tiab] OR '
    '"epidemiol"[tiab] OR "cohort"[tiab] OR "survey"[tiab])'
)

SEARCH_QUERY = (
    f"{markers} AND {subjects} AND {topics} "
    f"AND {date_filter} AND {article_filter} AND {lang_filter} "
    f"{exclusions}"
)


def build_search_query(start_date=None, end_date=None):
    """Same query as SEARCH_QUERY, but with an explicit date range instead of
    the rolling 30-day window -- for one-time catch-up runs covering a gap
    (e.g. between a static backlog corpus and when the daily job started),
    rather than permanently changing the daily job's own default behavior."""
    if start_date is None and end_date is None:
        return SEARCH_QUERY
    start = start_date or (datetime.now() - timedelta(days=30)).strftime("%Y/%m/%d")
    end = end_date or datetime.now().strftime("%Y/%m/%d")
    custom_date_filter = f"{start}:{end}[dp]"
    return (
        f"{markers} AND {subjects} AND {topics} "
        f"AND {custom_date_filter} AND {article_filter} AND {lang_filter} "
        f"{exclusions}"
    )

EXCLUDE_TYPES = [
    "review",
    "meta-analysis",
    "editorial",
    "letter",
    "comment",
    "guideline",
    "biography",
    "news",
    "patent",
    "patient education",
    "personal narrative",
    "collected work",
    "lecture",
    "retracted",
    "preprint",
    "books and documents",
    "evidence synthesis",
]



PROMPT = """
You are an expert in environmental science, Hepatotoxicity,  liver injure, toxicology,  pharmacology, specializing in Mitochondrial toxicology.

Please read the text inside the triple curly braces and extract the desired information.

1. Extraction Requirements
(1) A brief description of the desired information: Which chemicals were tested with which specified markers indicative of Hepatotoxicity or mitochondrial toxicity? In which cells or model species and under what conditions was the test conducted? What were the test results?

(2) Return the extracted information in the specified output format directly without any explanation or analyses.

(3) The specified output format: [tested chemical; subject type; (cell’s or model species’ basic information); exposure method; marker; result; evidence type; (exposure dose 1,exposure dose 2…); (exposure duration 1, exposure duration 2…);
(detected tissue/organ 1, detected tissue/organ 2…)].
Note: append an 11th field at the end of each entry: (evidence sentence 1 | evidence sentence 2 | evidence sentence 3). The full format is therefore: [tested chemical; subject type; （basic information）; exposure method; marker; result; evidence type; (exposure dose); (exposure duration); (detected tissue/organ); (evidence sentences)].

(4) Note that all elements within a single output entry are corresponding and related.The following elements must have unique values within one output entry: “tested chemical”, “subject type”, “cell’s or model species’ basic information”, “exposure
method”, “marker”, “result”, and “evidence type”. If there are multiple values for any of these elements, they should be separated into multiple output entries. Conversely,“exposure dose”, “exposure duration”, and “detected tissue/organ” can have multiple
values. In other words, if several exposure doses, exposure durations, and detected tissues/organs yield the same test result, they can be combined and included within a single entry.

(5) The information of four elements (i.e., “tested chemical”, “subject type”, “marker”, and “result”) are essential. If no entry including information of all those four elements can be extracted, please output only “No results”.

(6) For the elements with no available information, please return “-”.

2. Detailed Explanation for Each Output Element
(1) “tested chemical”:
“Tested chemical” should be one single specific chemical. Exclude chemical classes (e.g., PAHs, metals, quinones), mixtures(e.g., organic extractable matter, water extractable matter, secondary organic aerosol,
the mixtures of two or more chemicals), environmental matrices (e.g., PM2.5, dust),solvents, microplastics, and nanomaterials.

If both full name and abbreviation are available, please return the full name instead of the abbreviation.

(2) “subject type”:
The value should be one of the following terms — "Animal cell line", "Animal primary cells", "Human cell line", "Human primary cell line
, "Rodent", "Human subject"

Exclude plant cells, plant species, and microorganisms. Exclude model species other than zebrafish, rat, and mice. Exclude the transfected cells and gene-edited animals.
If it’s impossible to distinguish between “human cell” and “animal cell”, please simply return “cell”.
If it’s impossible to distinguish between “zebrafish embryo” and “adult zebrafish”,please simply return “zebrafish”.

(3) “cell’s or model species’ basic information”:For cells, please return cell name. The elements should be written as (cell name).
If both the full name (e.g., Human Bronchial Epithelial Cell Line) and abbreviation (e.g., BEAS-2b) are available, please return the abbreviation instead of the full name.
For zebrafish embryos, the elements should be written as (strain, age). The age is recorded at the start of exposure to the tested chemical, for which the unit is usually hpf(hours post fertilization) or dpf (days post fertilization).
For adult zebrafish, the elements should be written as (strain, age, gender).
For rat and mice, the elements should be written as (strain, age, gender, weight).

(4) “exposure method”:
Only when “subject type” is “rat” or “mice” or "cell", it needs to be extracted.
The common exposure methods include oral (e.g., dietary exposure and oral
intubation) and injection (e.g., intraperitoneal injection and subcutaneous injection).

(5) “marker”:
The value should be one of the following terms —“cell viability”, “ALT”, “LDH”, “AST”, "ALP", "bilirubin", "albumin", "ROS", "MDA", "TNF-α", "IL-6", "apoptosis", "necrosis", "ATP", "MMP/ΔΨm", "mtROS", "OCR", "OXPHOS", "cytochrome c release", "mPTP", "steatosis", "cholestasis", "fibrosis".
ALT is alanine aminotransferase. LDH is lactate dehydrogenase. AST is aspartate aminotransferase. ALP is alkaline phosphatase.
ROS is reactive oxygen species. MDA is malondialdehyde. TNF-α is tumor necrosis factor alpha. IL-6 is interleukin-6. ATP is adenosine triphosphate. MMP/ΔΨm is mitochondrial membrane potential. mtROS is mitochondrial reactive oxygen species. OCR is oxygen consumption rate. OXPHOS is oxidative phosphorylation. mPTP is mitochondrial permeability transition pore.
Exclude other markers. Cell viability is commonly assessed using metabolic activity–based assays, including the MTT assay, MTS assay, XTT assay, WST-1 assay, WST-8 (CCK-8) assay, Alamar Blue (Resazurin) assay, and PrestoBlue assay; TNF-α and IL-6 are typically measured by ELISA at the protein level and by qPCR at the mRNA level; Apoptosis is commonly measured using Annexin V/PI staining, caspase activity assays (e.g., Caspase-3/7), TUNEL assay, and Western blotting for apoptotic markers such as cleaved caspase-3, cleaved PARP, Bax, and Bcl-2; Necrosis is commonly measured using lactate dehydrogenase (LDH) release assays, Propidium Iodide (PI) staining, 7-AAD staining, and histological assessment (e.g., H&E staining);  ROS is usually tested with DCFH-DA (also known as DCFDA, H2DCFDA, 2’,7’-dichlorofluorescein diacetate, 2,7-dichlorofluorescein diacetate, 2’,7’-dichlorodihydrofluorescein diacetate, 2,7-dichlorodihydrofluorescein diacetate),
carboxy-H2DCFDA, carboxy-H2DFFDA, or CM-H2DCFDA

(6) “result”:
The value should be one of the following terms — “increase”, “decrease”, “no significant change”.
Include only the results generated from direct experimental tests and exclude results from correlation analysis and previous study citations.
Return only the results that can be definitively stated.

(7) “evidence type”:
The value should be one of the following terms — “specific doses” or “dosedependent”. This indicates that the returned result is determined by comparing specific
doses with the control group (which may be written as negative control, NC, CON，CTL) or by observing a dose-dependent pattern.

If the specific doses corresponding to the observed result were available, the value should be “specific doses”. If a dose-dependent pattern was specifically mentioned, the
value should be “dose-dependent”. If neither specific doses nor a dose-dependent pattern was mentioned, the value shoul
d be “-”.

(8) “exposure dose”:
The unit is usually nM (nmol/L, nmol L-1), µM (µmol/L, µmol L-1), mM (mmol/L,mmol L-1), ng/L (ng L-1), µg/L (µg L-1), mg/L (mg L-1), ng/mL (ng mL-1),
µg/mL (µg mL-1), mg/mL (mg mL-1) for cells and zebrafish.

The unit is usually mg per kg body weight per day (equivalent to mg/kg bw/day,mg/kg bw/d, mg/kg/day, mg/kg/d, mg/kg,
mg kg-1 day-1, mg kg-1 d-1, mg kg-1) for rats and mice.

If the “evidence type” is “specific doses”, please return the exposure doses corresponding to the observed activity instead of all measured exposure doses. If the “evidence type” is “dose-dependent” or “-”, please return all measured exposure doses.
It is preferable to return specific doses instead of a range.

(9) “exposure duration”:
The unit is usually h (hours), d (days), months, hpf, and dpf. Please return the exposure duration corresponding to the observed result, not all measured exposure duration.

(10) “detected tissue/organ”:
Commonly detected tissues/organs include heart, liver, lung, kidney, testis, brain,cerebellum, hippocampus, and blood.
Please return the tissue/organ corresponding to the observed result, not all detected tissue/organ.

(11) "evidence sentences":
Copy 1-3 sentences VERBATIM from the provided text that most directly support this specific record (the combination of tested chemical + marker + result). Enclose in parentheses. Separate multiple sentences with " | ".
Rules:

- Must be exact verbatim quotes from the text. Do not paraphrase or summarize.
- CRITICAL: If "evidence type" is "specific doses", at least one sentence MUST contain the actual dose value listed in field 8. Do not select sentences that only describe a group difference without mentioning the dose.
- CRITICAL: If "evidence type" is "dose-dependent", at least one sentence MUST explicitly describe the dose-dependent trend.
- If no directly supporting sentence exists, return (-).
Example: (Mice were administered 3% DSS in drinking water for 10 days. | MDA levels in the 3% DSS group were significantly higher than in the control group.)

3. Important Notes
(1) Output the extracted information in the specified output format directly. Do not
output any explanation or analyses.
(2) The “tested chemical” should be one single specific chemical, not be the combination of two or more chemicals.
(3) If available, please return the full name for “tested chemical” instead of their abbreviations.
(4) All of the other elements must be corresponding to the “tested chemical”, especially “exposure dose”.
(5) Only output the results about the specified markers. Do not output the results about any other marker like SOD, GSH, CAT, etc.
(6) For “exposure dose”, “exposure duration”, and “detected tissue/organ”, only output the values directly corresponding to the returned “marker” and “result”.
(7) If there is no desired information, which is possible, please output only “No results”.Do not make up any entries.
(8) For "evidence sentences", use ONLY verbatim sentences copied from the provided text. Never paraphrase. Every output entry must include this field.
(9) If a result is produced by the combined action of two or more chemicals together 
(e.g., co-treatment, combination group, synergistic effect), do NOT extract that result 
as a single-chemical entry. Only extract results where a single chemical is tested alone 
and its individual effect on the marker is clearly reported. If no such single-chemical 
result exists for that marker, skip it entirely.

"""
def build_prompt(text: str, title: str) -> str:
    header = (
        "You are an expert in Hepatotoxicity, liver injury, toxicology, "
        "pharmacology, specializing in Mitochondrial toxicology. "
        "Read the text inside the triple curly braces and extract the desired information.\n"
        f"Title: {title}\n"
        "{{{\n"
    )
    return header + text + "\n}}}\n" + PROMPT
