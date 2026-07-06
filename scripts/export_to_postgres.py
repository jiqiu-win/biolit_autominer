"""Load the conference dataset into PostgreSQL and verify it.

Prereqs:
  - A reachable PostgreSQL server + database.
  - Connection via BIOLIT_PG_DSN, e.g.
      export BIOLIT_PG_DSN="host=localhost port=5432 dbname=biolit user=me"

Usage:
  python scripts/export_to_postgres.py            # load current dataset into Postgres
  python scripts/export_to_postgres.py --verify   # also print row counts + sample queries
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from biolit_autominer.config import config
from biolit_autominer.postgres_loader import PostgresLoader


def verify(loader):
    conn = loader._connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM articles")
    n_articles = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM findings")
    n_findings = cur.fetchone()[0]
    print(f"\nRow counts:  articles={n_articles}  findings={n_findings}")

    print("\nArticles by source:")
    cur.execute("SELECT source, COUNT(*) FROM articles GROUP BY source ORDER BY 2 DESC")
    for source, n in cur.fetchall():
        print(f"  {source or '(none)':12} {n}")

    print("\nTop markers in findings:")
    cur.execute(
        "SELECT marker, result, COUNT(*) FROM findings "
        "GROUP BY marker, result ORDER BY 3 DESC LIMIT 8"
    )
    for marker, result, n in cur.fetchall():
        print(f"  {marker or '-':16} {result or '-':12} {n}")

    print("\nJoin check (findings -> articles via PMID), first 5:")
    cur.execute(
        "SELECT f.finding_id, f.pmid, a.source, f.tested_chemical, f.marker, f.result "
        "FROM findings f JOIN articles a ON a.pmid = f.pmid "
        "ORDER BY f.finding_id LIMIT 5"
    )
    for row in cur.fetchall():
        print("  ", row)
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load conference dataset into PostgreSQL")
    parser.add_argument("--dsn", default=None, help="Postgres DSN (default: BIOLIT_PG_DSN env)")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Append instead of truncating tables first",
    )
    parser.add_argument("--verify", action="store_true", help="Run verification queries after load")
    args = parser.parse_args()

    config.setup()
    loader = PostgresLoader(dsn=args.dsn)
    summary = loader.load_from_dataset(refresh=not args.no_refresh)
    print(f"Loaded into PostgreSQL: {summary['articles']} articles, {summary['findings']} findings")

    if args.verify:
        verify(loader)


if __name__ == "__main__":
    main()
