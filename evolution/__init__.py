"""Evolution layer — GEPA-style candidate pool."""
from .candidate import Candidate
from .pool import save_pool, load_pool, select_parent, prune_pool
from .mutate import mutate_shared, mutate_form, mutate_both, choose_mutation_target
from .loop import run_evolution_loop

__all__ = [
    "Candidate",
    "save_pool", "load_pool", "select_parent", "prune_pool",
    "mutate_shared", "mutate_form", "mutate_both", "choose_mutation_target",
    "run_evolution_loop",
]
