"""
evolution/loop.py — Main GEPA-style evolution loop for HPE-AFF.

Stopping criteria (AGENTS.md §9):
  - numeric_score >= 0.92 for 3 consecutive generations
  - AFF_EVOLUTION_BUDGET LLM calls exhausted (default 50)
  - Score delta < 0.005 for 5 consecutive generations
"""
from __future__ import annotations
import os
import json
import structlog
from datetime import datetime, timezone
from typing import Callable

from .candidate import Candidate
from .pool import save_pool, load_pool, select_parent, prune_pool
from .mutate import mutate_shared, mutate_form, mutate_both, choose_mutation_target

log = structlog.get_logger()

DEFAULT_BUDGET = int(os.environ.get("AFF_EVOLUTION_BUDGET", "50"))
DEFAULT_POOL_PATH = os.environ.get(
    "AFF_POOL_PATH",
    os.path.join(os.path.dirname(__file__), "..", "experiment_state", "candidate_pool.json"),
)


def run_evolution_loop(
    evaluate_fn: Callable[[Candidate], Candidate],
    initial_candidate: Candidate,
    pool_path: str | None = None,
    budget: int | None = None,
    max_pool_size: int = 20,
    field_inventory: list[dict] | None = None,
    azure_endpoint: str | None = None,
    azure_key: str | None = None,
    deployment: str | None = None,
    run_id: str | None = None,
) -> tuple[Candidate, list[Candidate]]:
    """Run the evolution loop to convergence.

    Args:
        evaluate_fn:       Function (Candidate) → Candidate with .score and .traces set.
        initial_candidate: Seed candidate (generation 0).
        pool_path:         JSON path for pool persistence.
        budget:            Max LLM calls (default AFF_EVOLUTION_BUDGET env var).
        max_pool_size:     Max candidates in pool before pruning.
        field_inventory:   Form field list for mutate_form.
        azure_endpoint:    Azure OpenAI endpoint.
        azure_key:         Azure OpenAI API key.
        deployment:        Model deployment name.
        run_id:            Run identifier for logging.

    Returns:
        (best_candidate, final_pool)
    """
    pool_path = pool_path or DEFAULT_POOL_PATH
    budget    = budget if budget is not None else DEFAULT_BUDGET
    run_id    = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    log.info("evolution_loop_start", run_id=run_id, budget=budget)

    # Load existing pool or start fresh
    pool = load_pool(pool_path)
    if not pool:
        pool = [initial_candidate]

    llm_calls = 0
    consecutive_high = 0   # consecutive gens with score >= 0.92
    recent_scores: list[float] = []

    for step in range(budget):
        # --- Select parent ---
        parent = select_parent(pool)

        # --- Evaluate parent if not yet scored ---
        if parent.score is None:
            parent = evaluate_fn(parent)
            llm_calls += 1
            # Update in pool
            for i, c in enumerate(pool):
                if c.id == parent.id:
                    pool[i] = parent
                    break

        if parent.score is None:
            log.warning("eval_returned_no_score", parent_id=parent.id)
            continue

        current_score = parent.score
        log.info(
            "evolution_step",
            run_id=run_id,
            step=step,
            parent_id=parent.id,
            score=current_score,
            pool_size=len(pool),
            llm_calls=llm_calls,
        )

        # --- Stopping: high score ---
        if current_score >= 0.92:
            consecutive_high += 1
            if consecutive_high >= 3:
                log.info("evolution_converged_high_score", score=current_score, step=step)
                break
        else:
            consecutive_high = 0

        # --- Stopping: plateau ---
        recent_scores = (recent_scores + [current_score])[-5:]
        if len(recent_scores) >= 5:
            delta = max(recent_scores[-5:]) - min(recent_scores[-5:])
            if delta < 0.005:
                log.info("evolution_converged_plateau", delta=delta, step=step)
                break

        # --- Budget check before mutate (mutate_both costs 2 LLM calls) ---
        if llm_calls >= budget:
            log.info("evolution_budget_exhausted", llm_calls=llm_calls)
            break

        # --- Mutate ---
        target = choose_mutation_target(parent.traces)
        log.info("mutation_target_chosen", target=target, parent_id=parent.id)

        kwargs = dict(
            azure_endpoint=azure_endpoint,
            azure_key=azure_key,
            deployment=deployment,
        )

        if target == "shared":
            child = mutate_shared(parent, **kwargs)
        elif target == "form":
            child = mutate_form(parent, field_inventory=field_inventory, **kwargs)
        else:
            child = mutate_both(parent, field_inventory=field_inventory, **kwargs)

        llm_calls += 1

        # --- Evaluate child ---
        child = evaluate_fn(child)
        llm_calls += 1

        if child.score is not None and (parent.score is None or child.score >= parent.score):
            pool.append(child)
            log.info("child_accepted", child_id=child.id, score=child.score)
        else:
            log.info("child_rejected", child_id=child.id,
                     child_score=child.score, parent_score=parent.score)

        # --- Prune ---
        if len(pool) > max_pool_size:
            pool = prune_pool(pool, max_size=max_pool_size)

        # --- Persist ---
        save_pool(pool, pool_path)

    # Final save
    save_pool(pool, pool_path)

    # Return best
    scored = [c for c in pool if c.score is not None]
    if scored:
        best = max(scored, key=lambda c: c.score)
    else:
        log.warning("evolution_no_scored_candidates", pool_size=len(pool))
        best = pool[0]

    log.info(
        "evolution_loop_complete",
        run_id=run_id,
        best_score=best.score,
        best_id=best.id,
        total_llm_calls=llm_calls,
        pool_size=len(pool),
    )

    return best, pool
