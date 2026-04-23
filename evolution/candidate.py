"""
evolution/candidate.py — Candidate dataclass for HPE-AFF evolution pool.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class Candidate:
    """A candidate (theta_L, theta_F) pair in the evolution pool.

    theta_L: Shared primitive library prompt (governs cross-form behaviour).
    theta_F: Form-specific generator prompt (governs field mapping for one form family).
    """
    theta_L: str
    theta_F: str
    score: float | None = None
    traces: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: str | None = None
    generation: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    form_id: str | None = None      # form this candidate was evaluated on
    fill_code: str | None = None    # generated PF code (if available)

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        """Deserialise from JSON dict, tolerating missing fields from older pool files."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})
