from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import DbPaths, connect, init_db, query_jobs
from .view_data import build_page_context


ROOT = Path(__file__).resolve().parents[1]
PATHS = DbPaths(root=ROOT)

app = FastAPI(title="Jobboard Econ (Agentic + Vibe)")

templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
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
    context, _ = build_page_context(
        conn,
        min_score=min_score,
        min_entry_score=min_entry_score,
        sort=sort,
        limit=200,
        api_url="/api/jobs",
        is_static=False,
    )
    conn.close()
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/api/jobs")
def api_jobs(min_score: float = 0.01, min_entry_score: float = 0.05, limit: int = 200, sort: str = "overall") -> dict:
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
    conn.close()
    return {"jobs": [dict(r) for r in rows]}

