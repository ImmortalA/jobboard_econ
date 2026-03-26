from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from dateutil import parser as date_parser

from .db import DbPaths
from .scoring import score_job


STATE_ABBR = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}


def _stable_id_from_url(url: str) -> int:
    u = (url or "").strip()
    if not u:
        # Fall back to a constant if URL missing.
        u = "missing-url"
    h = hashlib.sha256(u.encode("utf-8")).hexdigest()
    # Fits into signed 64-bit range.
    return int(h[:16], 16) % (2**63 - 1)


def _now_utc(now: datetime | None) -> datetime:
    if now is not None:
        return now
    return datetime.now(timezone.utc)


def looks_like_us_location(text: str | None) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return False

    if "united states" in s or "usa" in s or s == "us" or "u.s." in s:
        return True

    # Handle things like "CA" / "NY" in location strings.
    tokens = {t.strip().upper() for t in s.replace(",", " ").split()}
    if STATE_ABBR.intersection(tokens):
        return True

    return False


def _parse_datetime_maybe(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _read_csv_rows(csv_path: Path) -> Iterable[dict[str, str]]:
    # Encoding differences happen on Windows; try a couple.
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return []
                return list(reader)
        except UnicodeDecodeError:
            continue
    # Last resort: let it throw.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


@dataclass(frozen=True)
class LinkedinScrapeConfig:
    location: str = "United States"
    hours_old: int = 720
    results_wanted: int = 200
    distance: int = 25
    output_dir: Path = Path("data/linkedin")
    sites: tuple[str, ...] = ("linkedin",)
    linkedin_experience_levels: tuple[str, ...] = ("internship", "entry_level", "associate")

    # Keep search terms biased toward entry-level finance/econ-adjacent roles.
    search_terms: tuple[str, ...] = (
        "finance analyst",
        "financial analyst",
        "investment banking analyst",
        "risk analyst",
        "data analyst finance",
        "econometrics",
        "consulting analyst",
        "research analyst",
        "credit analyst",
        "strategy analyst",
    )


def scrape_linkedin_jobs(
    *,
    output_dir: Path,
    hours_old: int,
    results_wanted: int,
    timeout_seconds: int | None = None,
    sleep_time_seconds: int = 5,
    search_terms: Iterable[str] | None = None,
) -> list[Path]:
    """
    Uses jobsparser (JobSpy-based) to scrape LinkedIn and returns the created CSV paths.
    """
    cfg = LinkedinScrapeConfig(
        hours_old=hours_old,
        results_wanted=results_wanted,
        output_dir=output_dir,
        search_terms=tuple(search_terms) if search_terms is not None else LinkedinScrapeConfig.search_terms,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot time to filter "newly created" CSV files.
    started_at = datetime.now(timezone.utc)

    # Build CLI arguments for `python -m jobsparser ...`
    cmd: list[str] = [
        sys.executable,
        "-m",
        "jobsparser",
        "--site",
        "linkedin",
        "--location",
        cfg.location,
        "--output-dir",
        str(cfg.output_dir),
        "--results-wanted",
        str(cfg.results_wanted),
        "--distance",
        str(cfg.distance),
        "--hours-old",
        str(cfg.hours_old),
        # Reduce the default inter-batch sleep to avoid waiting ~100s.
        # (Higher values reduce block/captcha risk, lower values increase speed.)
        "--sleep-time",
        str(sleep_time_seconds),
        "--fetch-description",
    ]

    for term in cfg.search_terms:
        cmd += ["--search-term", term]

    for level in cfg.linkedin_experience_levels:
        cmd += ["--linkedin-experience-level", level]

    # Run jobsparser and stream output. We treat "progress/found" lines as notifications.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    start = time.monotonic()
    try:
        while True:
            if timeout_seconds is not None and (time.monotonic() - start) > timeout_seconds:
                print(f"[NOTI] Timeout reached after {timeout_seconds}s; stopping scrape.")
                try:
                    proc.kill()
                except Exception:
                    pass
                break

            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                clean = line.rstrip("\r\n")
                print(clean)

                low = clean.lower()
                # Notifications: these strings show up during jobsparser/JobSpy LinkedIn scraping.
                if ("found" in low and "jobs" in low) or ("reached desired" in low) or ("successfully saved" in low):
                    print(f"[NOTI] {clean}")
                    try:
                        import winsound

                        winsound.Beep(1200, 120)
                    except Exception:
                        pass
            else:
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
    finally:
        # Read remaining output to avoid pipe deadlocks.
        try:
            if proc.stdout:
                for tail_line in proc.stdout:
                    print(tail_line.rstrip("\r\n"))
        except Exception:
            pass

    if proc.returncode not in (0, None):
        # If we timed out, returncode is likely non-zero; don't hard-fail because CSVs may still exist.
        if timeout_seconds is None:
            raise RuntimeError(f"jobsparser failed with code {proc.returncode}")

    # Return CSVs created after start time.
    csvs: list[Path] = []
    for p in cfg.output_dir.glob("*.csv"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue
        if mtime >= started_at - timedelta(minutes=2):
            csvs.append(p)

    csvs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return csvs


def _pick_first(row: dict[str, Any], keys: Iterable[str]) -> str | None:
    for k in keys:
        for kk in (k, k.upper(), k.lower()):
            if kk in row and row[kk]:
                return str(row[kk]).strip()
    return None


def linkedin_csv_rows_to_db_rows(csv_paths: list[Path], *, now: datetime) -> list[dict[str, Any]]:
    now = _now_utc(now)
    rows: list[dict[str, Any]] = []

    for csv_path in csv_paths:
        if not csv_path.exists():
            continue
        csv_rows = _read_csv_rows(csv_path)

        for r in csv_rows:
            title = _pick_first(r, ["TITLE", "title"]) or ""
            company_name = _pick_first(r, ["COMPANY", "company"]) or ""
            url = _pick_first(r, ["JOB_URL", "job_url", "URL", "url"]) or ""
            description = _pick_first(r, ["DESCRIPTION", "description", "JOB_DESCRIPTION", "job_description"]) or ""

            # Location fields used to decide "job location is US".
            country = _pick_first(r, ["COUNTRY", "country"])
            state = _pick_first(r, ["STATE", "state"])
            city = _pick_first(r, ["CITY", "city"])
            location = _pick_first(r, ["LOCATION", "location"])
            loc_text = " ".join([x for x in [location, city, state, country] if x])

            # Publication date (best-effort). If missing, treat as now.
            pub_raw = _pick_first(r, ["POSTED_DATE", "posted_date", "DATE", "date", "PUBLISHED_DATE", "published_date"])
            pub = _parse_datetime_maybe(pub_raw) or now
            is_recent_30d = 1 if pub >= (now - timedelta(days=30)) else 0

            # Experience-level isn’t reliably present in every CSV; our scoring uses keywords too.
            # Here we only implement the US location rule.
            is_us = 1 if looks_like_us_location(loc_text) else 0

            score = score_job(title=title, category=_pick_first(r, ["CATEGORY", "category"]), tags=[], description=description)

            # Salary fields vary; keep best-effort.
            salary = _pick_first(r, ["SALARY", "salary", "INTERVAL", "interval"]) or None
            job_type = _pick_first(r, ["JOB_TYPE", "job_type", "JOB_TYPE_LABEL", "job_type_label"])

            rows.append(
                {
                    "id": _stable_id_from_url(url),
                    "url": url,
                    "title": title,
                    "company_name": company_name,
                    "company_logo": None,
                    "category": _pick_first(r, ["CATEGORY", "category"]),
                    "tags_json": "[]",
                    "job_type": job_type,
                    "publication_date": pub.isoformat(),
                    "candidate_required_location": loc_text,
                    "salary": salary,
                    "description": description,
                    "source": "linkedin",
                    "is_us": is_us,
                    "is_recent_30d": is_recent_30d,
                    "sector_score": float(score.sector_score),
                    "agentic_score": float(score.agentic_score),
                    "vibe_score": float(score.vibe_score),
                    "entry_score": float(score.entry_score),
                    "hard_block": int(score.hard_block),
                    "overall_score": float(score.overall_score),
                    "reasons_json": score.reasons_json,
                    "inserted_at": now.isoformat(),
                }
            )

    return rows

