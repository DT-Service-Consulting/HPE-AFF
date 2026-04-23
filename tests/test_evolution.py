"""
tests/test_evolution.py — Unit tests for evolution/ layer (no LLM calls).
"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from evolution.candidate import Candidate
from evolution.pool import save_pool, load_pool, select_parent, prune_pool
from evolution.mutate import choose_mutation_target


class TestCandidate:
    def test_defaults(self):
        c = Candidate(theta_L="shared prompt", theta_F="form prompt")
        assert c.score is None
        assert c.generation == 0
        assert len(c.id) == 8
        assert c.parent_id is None

    def test_serializable(self):
        c = Candidate(theta_L="L", theta_F="F", score=0.85, generation=1)
        d = vars(c)
        assert d["theta_L"] == "L"
        assert d["score"] == 0.85


class TestPool:
    def test_save_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "pool.json")
        pool = [
            Candidate(theta_L="L1", theta_F="F1", score=0.7),
            Candidate(theta_L="L2", theta_F="F2", score=0.9),
        ]
        save_pool(pool, path)

        loaded = load_pool(path)
        assert len(loaded) == 2
        assert loaded[0].theta_L == "L1"
        assert loaded[1].score == 0.9

    def test_load_missing_returns_empty(self, tmp_path):
        result = load_pool(str(tmp_path / "nonexistent.json"))
        assert result == []

    def test_select_parent_picks_best(self):
        pool = [
            Candidate(theta_L="L", theta_F="F", score=0.3),
            Candidate(theta_L="L", theta_F="F", score=0.9),
            Candidate(theta_L="L", theta_F="F", score=0.5),
        ]
        # Run multiple times — tournament should usually pick 0.9
        scores = [select_parent(pool).score for _ in range(20)]
        assert max(scores) == 0.9

    def test_prune_top_k(self):
        pool = [Candidate(theta_L="L", theta_F="F", score=float(i)/10) for i in range(15)]
        pruned = prune_pool(pool, max_size=5)
        assert len(pruned) == 5
        assert all(c.score >= 0.5 for c in pruned)

    def test_prune_no_op_if_small(self):
        pool = [Candidate(theta_L="L", theta_F="F") for _ in range(3)]
        pruned = prune_pool(pool, max_size=10)
        assert len(pruned) == 3


class TestChooseMutationTarget:
    def test_all_shared_traces(self):
        traces = ["LEVEL: shared — date format wrong"] * 5
        result = choose_mutation_target(traces)
        assert result in ("shared", "both")

    def test_all_form_traces(self):
        traces = ["LEVEL: form — missing mapping"] * 5
        result = choose_mutation_target(traces)
        assert result in ("form", "both")

    def test_empty_traces_returns_both(self):
        assert choose_mutation_target([]) == "both"

    def test_mixed_traces(self):
        traces = ["LEVEL: shared"] * 3 + ["LEVEL: form"] * 3
        result = choose_mutation_target(traces)
        assert result in ("shared", "form", "both")
