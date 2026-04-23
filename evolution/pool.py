"""
evolution/pool.py — Candidate pool persistence and selection.
"""
from __future__ import annotations
import dataclasses
import json
import os
import random
import structlog

from .candidate import Candidate

log = structlog.get_logger()


def save_pool(pool: list[Candidate], path: str) -> None:
    """Serialise pool to JSON. Creates parent dirs if needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([dataclasses.asdict(c) for c in pool], f, indent=2)
    log.info("pool_saved", path=path, size=len(pool))


def load_pool(path: str) -> list[Candidate]:
    """Deserialise pool from JSON. Returns empty list if file missing."""
    if not os.path.exists(path):
        log.info("pool_load_empty", path=path)
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    pool = [Candidate.from_dict(d) for d in data]
    log.info("pool_loaded", path=path, size=len(pool))
    return pool


def select_parent(pool: list[Candidate]) -> Candidate:
    """Tournament selection: sample 3, return highest-scored.

    Falls back to unscored candidates if no scored ones in sample.
    """
    if not pool:
        raise ValueError("Cannot select parent from empty pool")

    sample = random.sample(pool, min(3, len(pool)))
    scored = [c for c in sample if c.score is not None]
    if scored:
        return max(scored, key=lambda c: c.score)
    return sample[0]


def prune_pool(
    pool: list[Candidate],
    max_size: int = 20,
    strategy: str = "top_k",
) -> list[Candidate]:
    """Prune pool to max_size.

    Strategies:
      "top_k":  Keep top-k by score (unscored go last).
      "pareto": Keep Pareto front (if multi-objective scoring added later).
    """
    if len(pool) <= max_size:
        return pool

    if strategy == "top_k":
        scored = sorted(
            [c for c in pool if c.score is not None],
            key=lambda c: c.score,
            reverse=True,
        )
        unscored = [c for c in pool if c.score is None]
        pruned = (scored + unscored)[:max_size]
        log.info("pool_pruned", before=len(pool), after=len(pruned))
        return pruned

    # Unknown strategy: fall back to top_k
    scored = sorted(
        [c for c in pool if c.score is not None],
        key=lambda c: c.score,
        reverse=True,
    )
    unscored = [c for c in pool if c.score is None]
    return (scored + unscored)[:max_size]
