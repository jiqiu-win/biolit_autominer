import re


def title_slug(title, max_length=120):
    """Build a filename-safe title slug like the example/ folder."""
    if not title:
        return "Untitled"
    cleaned = title.strip().rstrip(".")
    cleaned = re.sub(r"[^\w\s\-]", "", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("_")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("_")
    return cleaned or "Untitled"


def format_pubmed_abstract_file(title, abstract):
    """Format like example/PMID34763627_....txt"""
    return f"Title: {title.strip()}\n\nAbstract:\n{abstract.strip()}\n"


def format_pmc_fulltext_file(title, body):
    """Format like example/PMC7617754_40403112_....txt"""
    return f"Title: {title.strip()}\n\n\n{body.strip()}\n"


def format_pmc_abstract_only_file(title, abstract):
    """Format like example/PMC11559786_39301884_....txt"""
    note = (
        "[NOTE: Full text not available via API due to publisher restrictions. Abstract only.]"
    )
    return f"{note}\n\n\nTitle: {title.strip()}\n\n\n{abstract.strip()}\n"
