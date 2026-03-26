from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analytics import summarize
from app.db import DbPaths, connect, count_jobs, get_last_refresh, get_stats, init_db, query_jobs


PATHS = DbPaths(root=ROOT)


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


def build_context(*, min_score: float, min_entry_score: float, sort: str, limit: int) -> tuple[dict, list[dict]]:
    conn = connect(PATHS.db_path)
    init_db(conn)

    rows = query_jobs(
        conn,
        limit=limit,
        us_only=True,
        recent_30d=True,
        min_overall=min_score,
        min_entry_score=min_entry_score,
        sort_by=sort,
    )
    stats = get_stats(conn)
    last_refresh = get_last_refresh(conn)
    matching_count = count_jobs(
        conn,
        us_only=True,
        recent_30d=True,
        min_overall=min_score,
        min_entry_score=min_entry_score,
    )
    summary = summarize(rows)
    conn.close()

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
        jobs.append(d)

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

    context = {
        "grouped": grouped_list,
        "toc": toc,
        "api_url": "./jobs.json",
        "is_static": True,
        "jobs": jobs,
        "stats": stats,
        "last_refresh": last_refresh,
        "min_score": min_score,
        "min_entry_score": min_entry_score,
        "sort": sort,
        "matching_count": matching_count,
        "showing_count": len(jobs),
        "summary": asdict(summary),
    }
    return context, jobs


def export_static_site(*, output_dir: Path, min_score: float, min_entry_score: float, sort: str, limit: int) -> None:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    context, jobs = build_context(
        min_score=min_score,
        min_entry_score=min_entry_score,
        sort=sort,
        limit=limit,
    )

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("index.html")
    html = template.render(**context)

    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / "jobs.json").write_text(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Exported static site to {output_dir}")
    print(f"Open file:///{(output_dir / 'index.html').as_posix()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the current job board as a static site.")
    parser.add_argument("--output-dir", default=str(ROOT / "dist"), help="Directory to write index.html and jobs.json.")
    parser.add_argument("--min-score", type=float, default=0.01)
    parser.add_argument("--min-entry-score", type=float, default=0.05)
    parser.add_argument("--sort", default="overall", choices=["overall", "agentic", "vibe", "sector", "entry", "pub"])
    parser.add_argument("--limit", type=int, default=200)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export_static_site(
        output_dir=Path(args.output_dir),
        min_score=args.min_score,
        min_entry_score=args.min_entry_score,
        sort=args.sort,
        limit=args.limit,
    )
