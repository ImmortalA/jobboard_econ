from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Iterable


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _count_hits(haystack: str, needles: Iterable[str]) -> tuple[int, list[str]]:
    hits: list[str] = []
    for n in needles:
        if not n:
            continue
        if re.search(rf"\b{re.escape(n.lower())}\b", haystack):
            hits.append(n)
    return len(hits), hits


# Sector keyword proxy.
#
# We don't have a reliable taxonomy from Remotive, so this list broadens the
# “finance/economics” intent to include adjacent domains like banking and consulting.
SECTOR_TERMS = [
    "finance",
    "fintech",
    "economics",
    "econometric",
    "econometrics",
    "macro",
    "microeconomics",
    # banking / credit / markets
    "portfolio",
    "bank",
    "banking",
    "investment bank",
    "credit",
    "lending",
    "underwriting",
    "brokerage",
    "capital markets",
    "market data",
    "trading",
    "risk",
    "investment",
    "investing",
    "equity",
    "fixed income",
    "derivatives",
    "asset management",
    "assets under management",
    "wealth management",
    "hedge fund",
    "valuation",
    "m&a",
    "mergers and acquisitions",
    "corporate finance",
    "advisory",
    "consulting",
    "consultant",
    "strategy consulting",
    "financial services",
    "audit",
    "accounting",
    "actuarial",
    "capital",
    "rates",

    # econometrics / research-adjacent
    "econometrics",
    "causal",
    "causal inference",
    "forecasting",
]

AGENTIC_TERMS = [
    "agent",
    "agents",
    "agentic",
    "autonomous",
    "ai workflow",
    "workflow automation",
    "ai automation",
    "tool use",
    "tool-use",
    "function calling",
    "function-calling",
    "orchestration",
    "multi step",
    "multi-step",
    "planner",
    "executor",
    "workflow",
    "prompt engineering",
    "generative ai",
    "genai",
    "llm application",
    "llm applications",
    "llm app",
    "ai assistant",
    "ai assistants",
    "rag",
    "retrieval augmented generation",
    "llm",
    "llms",
    "prompt",
    "openai",
    "anthropic",
    "claude",
    "evaluation",
    "evals",
]

VIBE_TERMS = [
    "rapid",
    "iterate",
    "iteration",
    "prototype",
    "prototyping",
    "ship",
    "shipping",
    "developer productivity",
    "ai assisted",
    "ai-assisted",
    "ai powered",
    "ai-powered",
    "cursor",
    "copilot",
    "github copilot",
    "windsurf",
    "claude code",
    "code generation",
    "pair programming",
    "vibe coding",
    "prototype fast",
    "build fast",
    "move fast",
]

# Entry-level / less-technical signal (keyword proxy).
ENTRY_LEVEL_TERMS = [
    "intern",
    "internship",
    "junior",
    "entry level",
    "entry-level",
    "trainee",
    "graduate",
    "new grad",
    "associate",
    "assistant",
    "research assistant",
    "analyst",
    "data analyst",
    "business analyst",
    "financial analyst",
    "credit analyst",
    "risk analyst",
    "research",
    "researcher",
    "coordinator",
    "operations",
    "customer success",
    "customer support",
    "trainee analyst",
]

# Penalize highly technical engineering roles if you want less “engineer” content.
TECH_NEGATIVE_TERMS = [
    "engineer",
    "engineering",
    "developer",
    "development",
    "software",
    "full-stack",
    "full stack",
    "devops",
    "sre",
    "site reliability",
    "backend",
    "frontend",
    "platform engineer",
    "rails",
    "react",
    "kubernetes",
    "docker",
    "terraform",
]

# A small canonical skills dictionary (you can extend later).
SKILL_TERMS = [
    # core
    "python",
    "sql",
    "r",
    "stata",
    "pandas",
    "numpy",
    "scikit-learn",
    "pytorch",
    "tensorflow",
    "spark",
    "databricks",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "postgresql",
    "redis",
    "elasticsearch",
    "langchain",
    "hugging face",
    "rag",
    "vector database",
    # finance/econ
    "time series",
    "forecasting",
    "risk",
    "portfolio",
    "valuation",
    "econometrics",
    "causal inference",
]

# Hard exclusions requested by user:
# - no PhD-required roles
# - no clearance/citizenship/green-card restricted roles
PHD_EXCLUSION_TERMS = [
    "phd required",
    "ph.d required",
    "phd preferred",
    "ph.d preferred",
    "doctorate required",
    "doctorate preferred",
    "must have a phd",
    "must hold a phd",
    "requires phd",
    "requires a phd",
    "phd in",
]

CLEARANCE_EXCLUSION_TERMS = [
    "security clearance",
    "clearance required",
    "active clearance",
    "top secret",
    "secret clearance",
    "ts/sci",
    "u.s. citizen",
    "us citizen",
    "must be a us citizen",
    "citizenship required",
    "green card required",
    "permanent resident required",
    "visa sponsorship not available",
    "must be authorized to work in the us without sponsorship",
]


@dataclass(frozen=True)
class ScoreResult:
    sector_score: float
    agentic_score: float
    vibe_score: float
    entry_score: float
    hard_block: int
    overall_score: float
    reasons_json: str
    extracted_skills: list[str]


def score_job(*, title: str, category: str | None, tags: list[str], description: str) -> ScoreResult:
    text = _norm(" ".join([title or "", category or "", " ".join(tags or []), description or ""]))

    sector_n, sector_hits = _count_hits(text, SECTOR_TERMS)
    agentic_n, agentic_hits = _count_hits(text, AGENTIC_TERMS)
    vibe_n, vibe_hits = _count_hits(text, VIBE_TERMS)
    entry_n, entry_hits = _count_hits(text, ENTRY_LEVEL_TERMS)
    tech_neg_n, tech_neg_hits = _count_hits(text, TECH_NEGATIVE_TERMS)
    phd_n, phd_hits = _count_hits(text, PHD_EXCLUSION_TERMS)
    clearance_n, clearance_hits = _count_hits(text, CLEARANCE_EXCLUSION_TERMS)

    # Soft saturation: more hits help, but diminishing returns.
    sector_score = 1.0 - math.exp(-0.6 * sector_n)
    agentic_score = 1.0 - math.exp(-0.7 * agentic_n)
    vibe_score = 1.0 - math.exp(-0.7 * vibe_n)

    # Prefer entry-level roles, and penalize “engineer/developer” heavy postings.
    # The entry score rises with ENTRY_LEVEL_TERMS and is dampened by TECH_NEGATIVE_TERMS.
    entry_score_raw = 1.0 - math.exp(-0.55 * entry_n)
    tech_penalty = math.exp(-0.9 * tech_neg_n)
    entry_score = entry_score_raw * tech_penalty

    # Enforce finance + skill-signal alignment while strongly preferring entry-level roles.
    # If a posting has no entry-level evidence, its overall score is heavily dampened.
    entry_score_factor = 0.1 + 0.9 * entry_score
    overall_score = (
        sector_score
        * (0.55 + 0.45 * agentic_score)
        * (0.55 + 0.45 * vibe_score)
        * entry_score_factor
    )
    hard_block = 1 if (phd_n > 0 or clearance_n > 0) else 0
    if hard_block:
        overall_score = 0.0

    skill_n, skill_hits = _count_hits(text, SKILL_TERMS)

    reasons = {
        "sector_hits": sector_hits,
        "agentic_hits": agentic_hits,
        "vibe_hits": vibe_hits,
        "entry_level_hits": entry_hits,
        "tech_negative_hits": tech_neg_hits,
        "skill_hits": skill_hits,
        "exclusion_hits": {
            "phd": phd_hits,
            "clearance_or_citizenship": clearance_hits,
        },
        "scores": {
            "sector_score": sector_score,
            "agentic_score": agentic_score,
            "vibe_score": vibe_score,
            "entry_score": entry_score,
        },
        "counts": {
            "sector": sector_n,
            "agentic": agentic_n,
            "vibe": vibe_n,
            "entry_level": entry_n,
            "tech_negative": tech_neg_n,
            "phd_exclusion": phd_n,
            "clearance_exclusion": clearance_n,
            "skills": skill_n,
        },
    }

    return ScoreResult(
        sector_score=sector_score,
        agentic_score=agentic_score,
        vibe_score=vibe_score,
        entry_score=entry_score,
        hard_block=hard_block,
        overall_score=overall_score,
        reasons_json=json.dumps(reasons, ensure_ascii=False),
        extracted_skills=skill_hits,
    )

