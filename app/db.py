from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class DbPaths:
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "data" / "jobs.sqlite3"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY,
          url TEXT NOT NULL,
          title TEXT NOT NULL,
          company_name TEXT NOT NULL,
          company_logo TEXT,
          category TEXT,
          tags_json TEXT,
          job_type TEXT,
          publication_date TEXT NOT NULL,
          candidate_required_location TEXT,
          salary TEXT,
          description TEXT NOT NULL,
          source TEXT NOT NULL,

          -- computed fields
          is_us INTEGER NOT NULL,
          is_recent_30d INTEGER NOT NULL,
          sector_score REAL NOT NULL,
          agentic_score REAL NOT NULL,
          vibe_score REAL NOT NULL,
          entry_score REAL NOT NULL,
          hard_block INTEGER NOT NULL DEFAULT 0,
          overall_score REAL NOT NULL,
          reasons_json TEXT NOT NULL,

          inserted_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_pubdate ON jobs(publication_date);
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(overall_score);
        """
    )
    conn.commit()

    # Lightweight migration: add missing columns if the DB already exists.
    cur = conn.execute("PRAGMA table_info(jobs)")
    cols = {row["name"] for row in cur.fetchall()}
    if "entry_score" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN entry_score REAL NOT NULL DEFAULT 0;")
        conn.commit()
    if "hard_block" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN hard_block INTEGER NOT NULL DEFAULT 0;")
        conn.commit()


def upsert_jobs(conn: sqlite3.Connection, rows: Iterable[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO jobs (
          id, url, title, company_name, company_logo, category, tags_json, job_type,
          publication_date, candidate_required_location, salary, description, source,
          is_us, is_recent_30d, sector_score, agentic_score, vibe_score, overall_score,
          entry_score, hard_block, reasons_json, inserted_at
        )
        VALUES (
          :id, :url, :title, :company_name, :company_logo, :category, :tags_json, :job_type,
          :publication_date, :candidate_required_location, :salary, :description, :source,
          :is_us, :is_recent_30d, :sector_score, :agentic_score, :vibe_score, :overall_score,
          :entry_score, :hard_block, :reasons_json, :inserted_at
        )
        ON CONFLICT(id) DO UPDATE SET
          url=excluded.url,
          title=excluded.title,
          company_name=excluded.company_name,
          company_logo=excluded.company_logo,
          category=excluded.category,
          tags_json=excluded.tags_json,
          job_type=excluded.job_type,
          publication_date=excluded.publication_date,
          candidate_required_location=excluded.candidate_required_location,
          salary=excluded.salary,
          description=excluded.description,
          source=excluded.source,
          is_us=excluded.is_us,
          is_recent_30d=excluded.is_recent_30d,
          sector_score=excluded.sector_score,
          agentic_score=excluded.agentic_score,
          vibe_score=excluded.vibe_score,
          entry_score=excluded.entry_score,
          hard_block=excluded.hard_block,
          overall_score=excluded.overall_score,
          reasons_json=excluded.reasons_json,
          inserted_at=excluded.inserted_at
        ;
        """,
        list(rows),
    )
    conn.commit()


def query_jobs(
    conn: sqlite3.Connection,
    *,
    limit: int = 200,
    us_only: bool = True,
    recent_30d: bool = True,
    min_overall: float = 0.0,
    min_entry_score: float = 0.0,
    sort_by: str = "overall",
) -> list[sqlite3.Row]:
    where = []
    params: dict[str, object] = {"limit": limit, "min_overall": min_overall}
    if us_only:
        where.append("is_us = 1")
    if recent_30d:
        where.append("is_recent_30d = 1")
    where.append("hard_block = 0")
    where.append("overall_score >= :min_overall")
    params["min_entry_score"] = min_entry_score
    where.append("entry_score >= :min_entry_score")
    where_sql = " AND ".join(where) if where else "1=1"

    sort_map = {
        "overall": "overall_score",
        "agentic": "agentic_score",
        "vibe": "vibe_score",
        "sector": "sector_score",
        "entry": "entry_score",
        "pub": "publication_date",
    }
    sort_field = sort_map.get(sort_by, "overall_score")

    cur = conn.execute(
        f"""
        SELECT *
        FROM jobs
        WHERE {where_sql}
        ORDER BY {sort_field} DESC, publication_date DESC
        LIMIT :limit
        """,
        params,
    )
    return list(cur.fetchall())


def count_jobs(
    conn: sqlite3.Connection,
    *,
    us_only: bool = True,
    recent_30d: bool = True,
    min_overall: float = 0.0,
    min_entry_score: float = 0.0,
) -> int:
    where = []
    params: dict[str, object] = {"min_overall": min_overall, "min_entry_score": min_entry_score}
    if us_only:
        where.append("is_us = 1")
    if recent_30d:
        where.append("is_recent_30d = 1")
    where.append("hard_block = 0")
    where.append("overall_score >= :min_overall")
    where.append("entry_score >= :min_entry_score")
    where_sql = " AND ".join(where) if where else "1=1"

    cur = conn.execute(f"SELECT COUNT(*) AS c FROM jobs WHERE {where_sql}", params)
    row = cur.fetchone()
    return int(row["c"]) if row else 0


def get_stats(conn: sqlite3.Connection) -> dict:
    cur = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN is_us=1 THEN 1 ELSE 0 END) AS us_total,
          SUM(CASE WHEN is_recent_30d=1 THEN 1 ELSE 0 END) AS recent_total,
          MAX(publication_date) AS newest_pubdate
        FROM jobs
        """
    )
    row = cur.fetchone()
    return dict(row) if row else {"total": 0, "us_total": 0, "recent_total": 0, "newest_pubdate": None}


def get_last_refresh(conn: sqlite3.Connection) -> Optional[str]:
    cur = conn.execute("SELECT MAX(inserted_at) AS last_refresh FROM jobs")
    row = cur.fetchone()
    if not row:
        return None
    return row["last_refresh"]

