from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone

from dateutil import parser as date_parser

from .analytics import summarize
from .db import count_jobs, get_last_refresh, get_stats, query_jobs


GROUP_ORDER = [
    "Internship",
    "Entry Level",
    "Associate",
    "Junior",
    "Analyst",
    "Manager",
    "Coordinator/Assistant",
    "Support/Ops",
    "Other",
]

SORT_OPTIONS = [
    {"value": "overall", "label": "Best match"},
    {"value": "pub", "label": "Newest"},
    {"value": "entry", "label": "Most entry-level"},
    {"value": "agentic", "label": "Most AI workflow"},
    {"value": "vibe", "label": "Most AI-assisted build"},
    {"value": "sector", "label": "Most finance-relevant"},
]

FIT_PRESETS = [
    {"value": "shown", "label": "Shown now", "min_overall": 0.0, "min_entry": 0.0},
    {"value": "good", "label": "Good fit+", "min_overall": 0.04, "min_entry": 0.09},
    {"value": "strong", "label": "Strong fit", "min_overall": 0.09, "min_entry": 0.15},
    {"value": "entry", "label": "Entry-first", "min_overall": 0.01, "min_entry": 0.15},
]


def seniority_group(title: str) -> str:
    t = (title or "").lower()
    if "intern" in t or "internship" in t:
        return "Internship"
    if "entry" in t and "level" in t:
        return "Entry Level"
    if "associate" in t:
        return "Associate"
    if "junior" in t or "jr" in t:
        return "Junior"
    if "analyst" in t or "f p & a" in t or "fp&a" in t:
        return "Analyst"
    if "manager" in t:
        return "Manager"
    if "coordinator" in t or "assistant" in t:
        return "Coordinator/Assistant"
    if "support" in t or "customer" in t or "operations" in t:
        return "Support/Ops"
    return "Other"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_date(value: str | None) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "—"
    return dt.strftime("%b %d, %Y")


def _relative_time(value: str | None, *, now: datetime | None = None) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "—"
    now = now or datetime.now(timezone.utc)
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 3600:
        mins = max(1, seconds // 60)
        return f"{mins}m ago"
    if seconds < 86400:
        hours = max(1, seconds // 3600)
        return f"{hours}h ago"
    if seconds < 86400 * 14:
        days = max(1, seconds // 86400)
        return f"{days}d ago"
    return dt.strftime("%b %d")


def _clean_excerpt(text: str | None, *, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    if len(clean) <= limit:
        return clean
    trimmed = clean[: limit - 1].rsplit(" ", 1)[0].strip()
    return (trimmed or clean[: limit - 1]).rstrip(".,;:") + "..."


def _fit_meta(overall_score: float, entry_score: float) -> tuple[str, str]:
    if overall_score >= 0.09 and entry_score >= 0.15:
        return "Strong fit", "emerald"
    if overall_score >= 0.04 and entry_score >= 0.09:
        return "Good fit", "sky"
    if overall_score >= 0.015 and entry_score >= 0.05:
        return "Worth a look", "amber"
    return "Stretch", "zinc"


def _evidence_chips(reasons: dict, *, limit: int = 5) -> list[str]:
    chips: list[str] = []
    buckets = [
        ("Entry", reasons.get("entry_level_hits") or []),
        ("Finance", reasons.get("sector_hits") or []),
        ("AI workflow", reasons.get("agentic_hits") or []),
        ("AI build", reasons.get("vibe_hits") or []),
        ("Skill", reasons.get("skill_hits") or []),
    ]
    seen: set[str] = set()
    for label, hits in buckets:
        for hit in hits:
            text = f"{label}: {hit}"
            if text in seen:
                continue
            seen.add(text)
            chips.append(text)
            if len(chips) >= limit:
                return chips
    return chips


def _search_blob(job: dict) -> str:
    parts = [
        job.get("title", ""),
        job.get("company_name", ""),
        job.get("candidate_required_location", ""),
        job.get("category", ""),
        job.get("job_type", ""),
        " ".join(job.get("tags") or []),
        " ".join(job.get("evidence_chips") or []),
        job.get("description", ""),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def build_page_context(
    conn,
    *,
    min_score: float,
    min_entry_score: float,
    sort: str,
    limit: int,
    api_url: str,
    is_static: bool,
) -> tuple[dict, list[dict]]:
    matching_count = count_jobs(
        conn,
        us_only=True,
        recent_30d=True,
        min_overall=min_score,
        min_entry_score=min_entry_score,
    )
    rows = query_jobs(
        conn,
        limit=limit,
        us_only=True,
        recent_30d=True,
        min_overall=min_score,
        min_entry_score=min_entry_score,
        sort_by=sort,
    )
    summary_rows = query_jobs(
        conn,
        limit=max(limit, min(matching_count, 500)),
        us_only=True,
        recent_30d=True,
        min_overall=min_score,
        min_entry_score=min_entry_score,
        sort_by=sort,
    )
    stats = get_stats(conn)
    last_refresh = get_last_refresh(conn)
    summary = summarize(summary_rows)
    now = datetime.now(timezone.utc)

    jobs: list[dict] = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d.get("tags_json") or "[]")
        except Exception:
            d["tags"] = []
        try:
            d["reasons"] = json.loads(d.get("reasons_json") or "{}")
        except Exception:
            d["reasons"] = {}

        group_name = seniority_group(d.get("title", ""))
        fit_label, fit_tone = _fit_meta(float(d.get("overall_score") or 0.0), float(d.get("entry_score") or 0.0))
        published_dt = _parse_dt(d.get("publication_date"))
        d["group_name"] = group_name
        d["group_slug"] = _slugify(group_name)
        d["fit_label"] = fit_label
        d["fit_tone"] = fit_tone
        d["display_date"] = _format_date(d.get("publication_date"))
        d["published_relative"] = _relative_time(d.get("publication_date"), now=now)
        d["published_ts"] = int(published_dt.timestamp()) if published_dt else 0
        d["description_preview"] = _clean_excerpt(d.get("description"))
        d["evidence_chips"] = _evidence_chips(d["reasons"])
        d["search_blob"] = _search_blob(d)
        jobs.append(d)

    grouped = {k: [] for k in GROUP_ORDER}
    for j in jobs:
        grouped[j["group_name"]].append(j)
    grouped_list = [(k, grouped[k]) for k in GROUP_ORDER if grouped[k]]
    toc = [{"name": name, "slug": _slugify(name), "count": len(items)} for (name, items) in grouped_list]

    context = {
        "grouped": grouped_list,
        "toc": toc,
        "api_url": api_url,
        "is_static": is_static,
        "jobs": jobs,
        "stats": stats,
        "last_refresh": last_refresh,
        "last_refresh_display": _format_date(last_refresh),
        "last_refresh_relative": _relative_time(last_refresh, now=now),
        "min_score": min_score,
        "min_entry_score": min_entry_score,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "fit_presets": FIT_PRESETS,
        "matching_count": matching_count,
        "showing_count": len(jobs),
        "summary": asdict(summary),
    }
    return context, jobs
