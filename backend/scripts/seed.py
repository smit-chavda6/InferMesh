"""Generate realistic historical `requests` rows so the dashboard (and its
performance target) are testable before the frontend exists (spec Phase 9).

    uv run seed                       # ~100k rows over the last 30 days, 5 projects
    uv run seed --rows 250000 --days 45 --truncate
    uv run seed --rows 2000 --seed 1  # small, reproducible

Or via Docker:  docker compose --profile seed run --rm seed
"""

from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.db.models import Alert, Project, RequestLog, SemanticCacheEntry
from app.db.session import Database
from app.pricing import get_pricing_table
from app.security import generate_api_key, hash_api_key, key_display_prefix

# --- distributions ----------------------------------------------------------

PROVIDER_WEIGHTS = {"openai": 0.55, "anthropic": 0.25, "gemini": 0.20}

MODELS: dict[str, list[tuple[str, float]]] = {
    "openai": [("gpt-4o-mini", 0.5), ("gpt-4o", 0.22), ("gpt-5.4", 0.16), ("gpt-4.1-mini", 0.12)],
    "anthropic": [
        ("claude-3-5-sonnet-latest", 0.5),
        ("claude-3-5-haiku-latest", 0.4),
        ("claude-3-opus-latest", 0.1),
    ],
    "gemini": [("gemini-3.6-flash", 0.5), ("gemini-1.5-flash", 0.3), ("gemini-1.5-pro", 0.2)],
}

# provider -> (median latency ms, sigma) for a lognormal draw on success
LATENCY = {"openai": (420, 0.5), "anthropic": (560, 0.55), "gemini": (720, 0.6)}

ERROR_TYPES = [
    ("provider_error", 502, 0.45),
    ("provider_timeout", 504, 0.30),
    ("provider_rate_limited", 429, 0.15),
    ("all_providers_failed", 502, 0.10),
]

# hour-of-day traffic weight (UTC) — a simple diurnal shape
HOUR_WEIGHT = [
    0.25,
    0.20,
    0.18,
    0.18,
    0.20,
    0.30,
    0.45,
    0.65,
    0.85,
    1.00,
    1.00,
    0.95,
    0.90,
    0.95,
    1.00,
    0.95,
    0.85,
    0.70,
    0.55,
    0.45,
    0.40,
    0.38,
    0.33,
    0.28,
]


def _weighted(items: list[tuple[str, float]], rng: random.Random) -> str:
    r = rng.random() * sum(w for _, w in items)
    upto = 0.0
    for name, w in items:
        upto += w
        if r <= upto:
            return name
    return items[-1][0]


def _timestamp(now: datetime, days: int, rng: random.Random) -> datetime:
    for _ in range(6):  # rejection-sample toward the diurnal shape
        ts = now - timedelta(seconds=rng.random() * days * 86_400)
        if rng.random() <= HOUR_WEIGHT[ts.hour]:
            return ts
    return ts


def _row(
    now: datetime,
    days: int,
    projects: list[dict],
    pricing,
    rng: random.Random,
) -> dict:
    provider = _weighted(list(PROVIDER_WEIGHTS.items()), rng)
    model = _weighted(MODELS[provider], rng)
    ts = _timestamp(now, days, rng)

    is_error = rng.random() < 0.045
    prompt = max(1, int(rng.lognormvariate(5.0, 0.7)))  # ~150 median
    completion = 0 if is_error else max(1, int(rng.lognormvariate(4.7, 0.8)))  # ~110 median
    med, sigma = LATENCY[provider]

    fallback = (not is_error) and rng.random() < 0.03
    retries = rng.choice([0, 0, 0, 1, 2]) if (is_error or fallback) else 0

    cache_roll = rng.random()
    cache_status = "HIT" if cache_roll < 0.20 else ("DISABLED" if cache_roll > 0.95 else "MISS")
    if is_error:
        cache_status = "MISS"

    cost = pricing.cost(provider, model, prompt, completion) if not is_error else None
    cost_usd = Decimal("0") if cache_status == "HIT" else (cost.total_cost_usd if cost else None)
    cache_saved = cost.total_cost_usd if (cache_status == "HIT" and cost) else None

    if is_error:
        etype, http_status, _ = _weighted_err(rng)
        mult = rng.uniform(0.1, 0.4) if etype == "provider_error" else rng.uniform(2.0, 4.0)
        latency = round(med * mult, 2)
    else:
        etype, http_status = None, 200
        latency = round(min(rng.lognormvariate(0, sigma) * med, med * 12), 2)

    pr = rng.random()
    project = None if pr < 0.10 else projects[int(pr * len(projects)) % len(projects)]

    return {
        # match the gateway's real id shape (req_ + 32 hex) so the Requests table
        # shows distinct ids, not a wall of near-identical seed strings
        "request_id": f"req_{uuid.uuid4().hex}",
        "created_at": ts,
        "provider": provider,
        "model": model,
        "upstream_model": f"{model}-2026",
        "status": "error" if is_error else "success",
        "http_status": http_status,
        "error_type": etype,
        "error_message": (f"{provider}: simulated {etype}" if is_error else None),
        "finish_reason": None if is_error else rng.choice(["stop", "stop", "stop", "length"]),
        "latency_ms": latency,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cost_usd": cost_usd,
        "input_cost_usd": cost.input_cost_usd if (cost and cache_status != "HIT") else None,
        "output_cost_usd": cost.output_cost_usd if (cost and cache_status != "HIT") else None,
        "pricing_version": pricing.version if cost else None,
        "cache_saved_usd": cache_saved,
        "fallback_used": fallback,
        "retries": retries,
        "provider_chain": (
            [
                {"provider": "openai", "model": model, "outcome": "timeout", "retries": retries},
                {"provider": provider, "model": model, "outcome": "success", "retries": 0},
            ]
            if fallback
            else None
        ),
        "cache_status": cache_status,
        "cache_key": (uuid.uuid4().hex if cache_status in ("HIT", "MISS") else None),
        "streamed": (not is_error) and rng.random() < 0.15,
        "message_count": rng.choice([1, 1, 1, 2, 3, 5]),
        "project_id": project["id"] if project else None,
        "project_name": project["name"] if project else None,
        "api_key_prefix": project["prefix"] if project else None,
    }


def _weighted_err(rng: random.Random) -> tuple[str, int, float]:
    r = rng.random() * sum(w for *_, w in ERROR_TYPES)
    upto = 0.0
    for etype, code, w in ERROR_TYPES:
        upto += w
        if r <= upto:
            return etype, code, w
    return ERROR_TYPES[0]


# --- runner ---------------------------------------------------------------


async def seed(
    rows: int,
    days: int,
    n_projects: int,
    truncate: bool,
    rng_seed: int | None,
    settings: object | None = None,
    quiet: bool = False,
) -> int:
    settings = settings or get_settings()
    pricing = get_pricing_table()

    def _say(msg: str) -> None:
        if not quiet:
            print(msg)

    rng = random.Random(rng_seed)
    db = Database(settings)
    maker = async_sessionmaker(db.engine, expire_on_commit=False)
    now = datetime.now(UTC)
    started = now

    try:
        async with maker() as session:
            if truncate:
                await session.execute(delete(RequestLog))
                await session.execute(delete(Alert))
                await session.execute(delete(SemanticCacheEntry))
                await session.execute(delete(Project))
                await session.commit()
                _say("truncated requests / alerts / semantic_cache / projects")

            projects: list[dict] = []
            for k in range(n_projects):
                key = generate_api_key()
                p = Project(
                    name=f"{rng.choice(['RAG', 'Chatbot', 'Summariser', 'Agent', 'Copilot'])} "
                    f"{rng.choice(['Prod', 'Staging', 'Internal', 'Beta'])} {k + 1}",
                    key_hash=hash_api_key(key),
                    key_prefix=key_display_prefix(key),
                    rate_limit_per_minute=rng.choice([30, 60, 60, 120, 240]),
                    rate_limit_window_seconds=60,
                    last_used_at=now - timedelta(minutes=rng.randint(1, 600)),
                )
                session.add(p)
                await session.flush()
                projects.append({"id": p.id, "name": p.name, "prefix": p.key_prefix})
            await session.commit()
            _say(f"created {len(projects)} projects")

            batch: list[dict] = []
            written = 0
            for _ in range(rows):
                batch.append(_row(now, days, projects, pricing, rng))
                if len(batch) >= 5000:
                    await session.execute(insert(RequestLog), batch)
                    await session.commit()
                    written += len(batch)
                    batch.clear()
                    if not quiet:
                        print(f"  {written:>7,} / {rows:,}", end="\r", flush=True)
            if batch:
                await session.execute(insert(RequestLog), batch)
                await session.commit()
                written += len(batch)

        elapsed = (datetime.now(UTC) - started).total_seconds()
        _say(
            f"\nseeded {written:,} requests over {days} days in {elapsed:.1f}s "
            f"({written / max(elapsed, 0.01):,.0f} rows/s)"
        )
        return written
    finally:
        await db.dispose()


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed realistic historical request logs.")
    ap.add_argument("--rows", type=int, default=100_000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--projects", type=int, default=5)
    ap.add_argument("--truncate", action="store_true", help="wipe requests/alerts/projects first")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    a = ap.parse_args()
    asyncio.run(seed(a.rows, a.days, a.projects, a.truncate, a.seed))


if __name__ == "__main__":
    main()
