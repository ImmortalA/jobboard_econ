# Job Board Econ (US • last 30 days • Finance/Econ • Agentic + Vibe)

Small job board that imports jobs from LinkedIn (via `jobsparser` scraping), filtering to:

- US-only (by `candidate_required_location`)
- last 30 days (by `publication_date`)
- Finance/Economics signals
- “agentic AI” + “vibe coding” signals (keyword proxies)

It stores results in SQLite and serves a simple UI plus JSON API.

## Setup (Windows / PowerShell)

Use Python 3.12 for best wheel compatibility (Python 3.14 may force Rust builds).

Create a Python virtual environment and install deps:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Refresh jobs

Fetch and insert/update jobs into SQLite:

```powershell
python .\scripts\refresh.py
```

## Run the web app

```powershell
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/`.

## One-command convenience

This repo includes `.\scripts\run.ps1`, which uses a separate Python 3.12 virtual environment (`.venv312`) to avoid Windows file-lock issues:

```powershell
.\scripts\run.ps1
```

## Share without install

If someone only needs to browse the board, you can export the current data into a static site:

```powershell
.\scripts\export_static.ps1
```

That writes:

- `dist/index.html`
- `dist/jobs.json`
- `dist/.nojekyll`

You can open `dist/index.html` locally, or upload the `dist/` folder to a static host like GitHub Pages, Cloudflare Pages, or Netlify and share the link.

## GitHub Pages

This repo includes `.github/workflows/pages.yml` to deploy the exported `dist/` folder to GitHub Pages.

Important:

- The workflow deploys the committed `dist/` folder; it does not scrape LinkedIn on GitHub.
- Refresh data locally first, then export again before pushing:

```powershell
.\scripts\auto_run_linkedin.ps1
.\scripts\export_static.ps1
git add dist
git commit -m "Update exported site"
git push
```

- In the GitHub repo, set `Settings -> Pages -> Build and deployment -> Source` to `GitHub Actions` once.

## Notes

- The “subtract summaries” view shows skill deltas computed as:
  - Agentic-minus-vibe: skills that show up more often in jobs where `agentic_score >= vibe_score`
  - Vibe-minus-agentic: the reverse
- You can adjust the threshold via `/?min_score=0.1`
- Extend keyword lists in `app/scoring.py`
- LinkedIn import is controlled by `scripts/refresh.py`:
  - `--scrape` runs `jobsparser` to generate fresh CSVs
  - without `--scrape`, it imports existing CSVs from `data/linkedin/`

