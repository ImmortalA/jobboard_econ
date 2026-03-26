from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass


def _safe_load_json_list(s: str | None) -> list[str]:
    if not s:
        return []
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x) for x in v]
    except Exception:
        return []
    return []


def _safe_load_reasons(s: str | None) -> dict:
    if not s:
        return {}
    try:
        v = json.loads(s)
        if isinstance(v, dict):
            return v
    except Exception:
        return {}
    return {}


@dataclass(frozen=True)
class Summary:
    top_titles: list[tuple[str, int]]
    top_companies: list[tuple[str, int]]
    top_skills: list[tuple[str, int]]
    top_agentic_skills: list[tuple[str, int]]
    top_vibe_skills: list[tuple[str, int]]
    delta_agentic_minus_vibe: list[tuple[str, int]]
    delta_vibe_minus_agentic: list[tuple[str, int]]


def summarize(rows) -> Summary:
    titles = Counter()
    companies = Counter()
    skills_all = Counter()
    skills_agentic = Counter()
    skills_vibe = Counter()

    for r in rows:
        titles[r["title"]] += 1
        companies[r["company_name"]] += 1

        reasons = _safe_load_reasons(r["reasons_json"])
        skill_hits = reasons.get("skill_hits") or []
        for s in skill_hits:
            skills_all[s] += 1

            # Split buckets by stronger side for "delta"
            if float(r["agentic_score"]) >= float(r["vibe_score"]):
                skills_agentic[s] += 1
            if float(r["vibe_score"]) >= float(r["agentic_score"]):
                skills_vibe[s] += 1

    # "Subtract summaries": compute deltas from the two buckets above.
    all_skill_keys = set(skills_agentic) | set(skills_vibe)
    delta_a = Counter({k: skills_agentic[k] - skills_vibe[k] for k in all_skill_keys})
    delta_v = Counter({k: skills_vibe[k] - skills_agentic[k] for k in all_skill_keys})

    return Summary(
        top_titles=titles.most_common(15),
        top_companies=companies.most_common(15),
        top_skills=skills_all.most_common(25),
        top_agentic_skills=skills_agentic.most_common(25),
        top_vibe_skills=skills_vibe.most_common(25),
        delta_agentic_minus_vibe=[(k, v) for k, v in delta_a.most_common(25) if v > 0],
        delta_vibe_minus_agentic=[(k, v) for k, v in delta_v.most_common(25) if v > 0],
    )

