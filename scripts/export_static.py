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

from app.db import DbPaths, connect, init_db
from app.view_data import build_page_context


PATHS = DbPaths(root=ROOT)


def export_static_site(*, output_dir: Path, min_score: float, min_entry_score: float, sort: str, limit: int) -> None:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(PATHS.db_path)
    init_db(conn)
    context, jobs = build_page_context(
        conn,
        min_score=min_score,
        min_entry_score=min_entry_score,
        sort=sort,
        limit=limit,
        api_url="./jobs.json",
        is_static=True,
    )
    conn.close()

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
