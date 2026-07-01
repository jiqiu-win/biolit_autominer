"""Stage PMC full-text .txt in updated/, then archive to downloaded/ after N days."""

import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .config import config


class PmcStagingManager:
    """
    Day 0: PMC full-text .txt lives in auto_pipeline_output/updated/PMC_full_text_updated/txt/
    Day N: move to downloaded/pmc_full_text/txt/ and update articles.db local_file_path.
    """

    def __init__(self, manifest_path=None, age_days=None):
        self.manifest_path = Path(manifest_path or config.PMC_STAGING_MANIFEST)
        self.age_days = age_days if age_days is not None else config.PMC_STAGING_AGE_DAYS

    def _load_manifest(self):
        if not self.manifest_path.is_file():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_manifest(self, manifest):
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def record_staged_file(self, path, pmid, pmcid="", title=""):
        path = Path(path)
        if path.parent.resolve() != config.UPDATED_PMC_TXT.resolve():
            return

        manifest = self._load_manifest()
        manifest[path.name] = {
            "staged_at": datetime.now().isoformat(),
            "pmid": str(pmid),
            "pmcid": config.format_pmcid(pmcid) if pmcid else "",
            "title": title or "",
        }
        self._save_manifest(manifest)

    def bootstrap_manifest_from_staging(self):
        """Register existing staging .txt files that pre-date the manifest."""
        manifest = self._load_manifest()
        changed = False

        for path in sorted(config.UPDATED_PMC_TXT.glob("*.txt")):
            if path.name.startswith("."):
                continue
            if path.name in manifest:
                continue
            manifest[path.name] = {
                "staged_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "pmid": "",
                "pmcid": "",
                "title": "",
            }
            changed = True

        if changed:
            self._save_manifest(manifest)
        return len(manifest)

    def _update_local_file_path(self, db_path, pmid, new_path):
        if not pmid:
            return
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE articles SET local_file_path = ?, updated_at = ? WHERE pmid = ?",
            (str(new_path), datetime.now(), str(pmid)),
        )
        conn.commit()
        conn.close()

    def archive_staged_files(self, db=None):
        """
        Move staging files older than age_days to downloaded/pmc_full_text/txt/.
        Returns summary dict.
        """
        self.bootstrap_manifest_from_staging()
        manifest = self._load_manifest()
        cutoff = datetime.now() - timedelta(days=self.age_days)

        moved = []
        kept = []
        missing = []

        config.DOWNLOADS_PMC_TXT.mkdir(parents=True, exist_ok=True)

        for filename, meta in list(manifest.items()):
            staged_at = datetime.fromisoformat(meta["staged_at"])
            if staged_at > cutoff:
                kept.append(filename)
                continue

            source = config.UPDATED_PMC_TXT / filename
            if not source.is_file():
                missing.append(filename)
                del manifest[filename]
                continue

            dest = config.DOWNLOADS_PMC_TXT / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()
            shutil.move(str(source), str(dest))

            pmid = meta.get("pmid")
            if db and pmid:
                self._update_local_file_path(db.db_path, pmid, dest)

            del manifest[filename]
            moved.append({"filename": filename, "pmid": pmid, "archive_path": str(dest)})

        self._save_manifest(manifest)

        summary = {
            "age_days": self.age_days,
            "moved_count": len(moved),
            "kept_in_staging": len(kept),
            "missing_removed": len(missing),
            "moved": moved,
        }
        if moved:
            print(
                f"Archived {len(moved)} PMC full-text file(s) to {config.DOWNLOADS_PMC_TXT}"
            )
        return summary

    @staticmethod
    def migrate_flat_downloads_to_txt_subfolder():
        """Move legacy flat downloaded/pmc_full_text/*.txt into .../txt/."""
        config.DOWNLOADS_PMC_TXT.mkdir(parents=True, exist_ok=True)
        moved = 0
        for path in config.DOWNLOADS_PMC.glob("*.txt"):
            dest = config.DOWNLOADS_PMC_TXT / path.name
            if dest.exists():
                path.unlink(missing_ok=True)
                continue
            shutil.move(str(path), str(dest))
            moved += 1
        return moved
