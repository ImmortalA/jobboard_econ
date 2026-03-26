from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .analytics import summarize
from .db import DbPaths, connect, count_jobs, get_last_refresh, get_stats, init_db, query_jobs


ROOT = Path(__file__).resolve().parents[1]
PATHS = DbPaths(root=ROOT)

app = FastAPI(title="Jobboard Econ (Agentic + Vibe)")

templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _seniority_group(title: str) -> str:
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


@app.on_event("startup")
def _startup() -> None:
    conn = connect(PATHS.db_path)
    init_db(conn)
    conn.close()


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    min_score: float = 0.01,
    min_entry_score: float = 0.05,
    sort: str = "overall",
) -> HTMLResponse:
    conn = connect(PATHS.db_path)
    init_db(conn)

    rows = query_jobs(
        conn,
        limit=200,
        us_only=True,
        recent_30d=True,
        min_overall=min_score,
        min_entry_score=min_entry_score,
        sort_by=sort,
    )
    stats = get_stats(conn)
    last_refresh = get_last_refresh(conn)
    matching_count = count_jobs(conn, us_only=True, recent_30d=True, min_overall=min_score, min_entry_score=min_entry_score)
    summary = summarize(rows)

    # Pre-decode some JSON fields for template convenience
    jobs = []
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
        jobs.append(d)

    # Group jobs into buckets so the UI isn’t a single long vertical list.
    group_order = [
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
    grouped = {k: [] for k in group_order}
    for j in jobs:
        grouped[_seniority_group(j.get("title"))].append(j)
    grouped_list = [(k, grouped[k]) for k in group_order if grouped[k]]
    toc = [{"name": name, "count": len(items)} for (name, items) in grouped_list]

    conn.close()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "grouped": grouped_list,
            "toc": toc,
            "api_url": "/api/jobs",
            "is_static": False,
            "jobs": jobs,  # kept for backward-compat with the existing template logic
            "stats": stats,
            "last_refresh": last_refresh,
            "min_score": min_score,
            "min_entry_score": min_entry_score,
            "sort": sort,
            "matching_count": matching_count,
            "showing_count": len(jobs),
            "summary": summary,
        },
    )


@app.get("/api/jobs")
def api_jobs(min_score: float = 0.01, min_entry_score: float = 0.05, limit: int = 200) -> dict:
    conn = connect(PATHS.db_path)
    init_db(conn)
    rows = query_jobs(conn, limit=limit, us_only=True, recent_30d=True, min_overall=min_score, min_entry_score=min_entry_score)
    conn.close()
    return {"jobs": [dict(r) for r in rows]}

