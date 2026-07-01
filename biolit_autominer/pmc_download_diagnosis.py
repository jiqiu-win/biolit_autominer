"""Classify why PMC full text was or was not downloaded."""

from .config import config

# Who is responsible when download fails or is partial
RESPONSIBILITY = {
    "none": "No issue — expected behavior",
    "pmc_dataset": "PMC licensing / Open Access dataset limitation (not our code)",
    "pmc_service": "PMC or NCBI service issue (AWS bucket, Entrez, BioC)",
    "pipeline": "Pipeline or local environment issue (network, config, bug)",
    "pubmed": "Article has no PMC record — PubMed abstract only",
}


def classify_article_outcome(pmid, pmcid, availability, content_source, error=None):
    """
    Return diagnosis dict for one article.

    availability: from PMCAwsFetcher.check_availability()
    """
    pmcid = config.format_pmcid(pmcid) if pmcid else ""

    if error:
        err_lower = str(error).lower()
        if any(k in err_lower for k in ("timeout", "connection", "503", "502", "504")):
            return _diag(
                "pmc_service_unreachable",
                RESPONSIBILITY["pmc_service"],
                f"PMID {pmid}: Could not reach PMC/NCBI services ({error}). "
                "This is likely a temporary PMC/network issue, not a bug in our search query.",
            )
        return _diag(
            "pipeline_error",
            RESPONSIBILITY["pipeline"],
            f"PMID {pmid}: Download failed ({error}). Check NCBI credentials and network.",
        )

    if not pmcid:
        return _diag(
            "no_pmc_record",
            RESPONSIBILITY["pubmed"],
            f"PMID {pmid}: No PMC record — only PubMed abstract is available.",
        )

    if content_source == "pmc_full_text":
        method = availability.get("source_method") or "unknown"
        return _diag(
            "full_text_downloaded",
            RESPONSIBILITY["none"],
            f"PMID {pmid} ({pmcid}): Full text downloaded via {method}.",
            success=True,
        )

    if not availability.get("in_aws_bucket"):
        return _diag(
            "pmc_not_in_open_access_subset",
            RESPONSIBILITY["pmc_dataset"],
            f"PMID {pmid} ({pmcid}): Article appears on the PMC website but is NOT in the "
            "PMC Open Access / Author Manuscript AWS datasets. Full text cannot be retrieved "
            "automatically under PMC copyright rules. This is a PMC licensing limitation, "
            "not a bug in our pipeline.",
        )

    return _diag(
        "pmc_entrez_abstract_only",
        RESPONSIBILITY["pmc_dataset"],
        f"PMID {pmid} ({pmcid}): PMC record exists but Entrez returns abstract-only. "
        "Publisher may restrict full-text API access even though the article is in PMC.",
    )


def build_run_diagnosis(
    classification,
    downloaded,
    abstract_only,
    skipped_no_pmc,
    errors,
    aws_reachable,
    to_process_count,
):
    """Build top-level diagnosis for a daily run."""
    new_count = len(classification.get("new", []))
    modified_count = len(classification.get("modified", []))
    unchanged_count = len(classification.get("unchanged", []))
    total_found = len(classification.get("all_pmids", []))

    if not aws_reachable:
        return {
            "status": "pmc_service_down",
            "responsibility": RESPONSIBILITY["pmc_service"],
            "user_message": (
                "Could not reach the PMC AWS Cloud Service (pmc-oa-opendata). "
                "This is a PMC/infrastructure issue — wait and retry later. Our code did not fail."
            ),
            "details": {
                "aws_reachable": False,
                "total_found": total_found,
                "new_count": new_count,
                "modified_count": modified_count,
            },
        }

    if new_count == 0 and modified_count == 0 and to_process_count == 0:
        return {
            "status": "no_new_articles",
            "responsibility": RESPONSIBILITY["none"],
            "user_message": (
                f"No new or modified articles matched your PubMed search today "
                f"({total_found} total in search, {unchanged_count} unchanged). "
                "This is normal — not a PMC website problem and not a pipeline bug."
            ),
            "details": {
                "aws_reachable": True,
                "total_found": total_found,
                "unchanged_count": unchanged_count,
            },
        }

    if downloaded:
        return {
            "status": "success",
            "responsibility": RESPONSIBILITY["none"],
            "user_message": (
                f"Downloaded {len(downloaded)} PMC full-text article(s). "
                "Files are visible immediately in updated/PMC_full_text_updated/txt/."
            ),
            "details": {
                "aws_reachable": True,
                "downloaded_count": len(downloaded),
                "abstract_only_count": len(abstract_only),
                "errors_count": len(errors),
            },
        }

    if abstract_only and not downloaded:
        pmc_limited = sum(
            1 for a in abstract_only if a.get("diagnosis_code") == "pmc_not_in_open_access_subset"
        )
        return {
            "status": "pmc_license_limited",
            "responsibility": RESPONSIBILITY["pmc_dataset"],
            "user_message": (
                f"Found {to_process_count} article(s) to process but 0 full-text downloads. "
                f"{pmc_limited} article(s) are on PMC but outside the licensed Open Access "
                "datasets — this is a PMC copyright/dataset limitation, not our code. "
                "See abstract_only details in this summary."
            ),
            "details": {
                "aws_reachable": True,
                "abstract_only_count": len(abstract_only),
                "pmc_license_limited_count": pmc_limited,
            },
        }

    if errors:
        return {
            "status": "pipeline_errors",
            "responsibility": RESPONSIBILITY["pipeline"],
            "user_message": (
                f"Encountered {len(errors)} error(s) while downloading. "
                "See errors list in this summary — may be network or NCBI API issues."
            ),
            "details": {"aws_reachable": True, "errors_count": len(errors)},
        }

    if skipped_no_pmc:
        return {
            "status": "no_pmc_records",
            "responsibility": RESPONSIBILITY["pubmed"],
            "user_message": (
                f"{len(skipped_no_pmc)} article(s) have no PMC record — "
                "only PubMed abstracts can be retrieved. Not a PMC website outage."
            ),
            "details": {"skipped_no_pmc_count": len(skipped_no_pmc)},
        }

    return {
        "status": "nothing_downloaded",
        "responsibility": RESPONSIBILITY["none"],
        "user_message": "Run completed but no files were downloaded. See per-article details.",
        "details": {"aws_reachable": True},
    }


def _diag(code, responsibility, user_message, success=False):
    return {
        "diagnosis_code": code,
        "responsibility": responsibility,
        "user_message": user_message,
        "success": success,
    }
