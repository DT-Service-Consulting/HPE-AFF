"""
evaluation/semantic.py — Layer 2: Semantic correctness.

Uses token overlap as a fast, dependency-free semantic similarity metric.
Optional: if sentence-transformers is available, uses cosine similarity.
"""
from __future__ import annotations
import re
import structlog

log = structlog.get_logger()


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def token_overlap_similarity(a: str, b: str) -> float:
    """Fast token overlap coefficient: |A∩B| / max(|A|, |B|)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def cosine_similarity(a: str, b: str) -> float | None:
    """Cosine similarity via sentence-transformers, if available. Returns None otherwise."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embs = model.encode([a, b], normalize_embeddings=True)
        return float(np.dot(embs[0], embs[1]))
    except ImportError:
        return None
    except Exception as e:
        log.warning("cosine_similarity_failed", error=str(e))
        return None


def semantic_score(
    expected_mapping: dict[str, str],
    actual_values: dict[str, str],
    use_embeddings: bool = False,
) -> dict:
    """Layer 2 semantic evaluation of all text fields.

    Skips checkbox fields (handled in structural/format layers).

    Returns:
        {
          "score": float,                  # mean semantic similarity across text fields
          "field_similarities": dict,      # field_id → similarity score
          "semantic_mismatches": list,     # field_ids with sim < 0.85
        }
    """
    similarities = {}
    mismatches = []

    for field_name, expected_val in expected_mapping.items():
        # Skip checkboxes
        if expected_val in ("/Yes", "/Off"):
            continue

        actual_val = actual_values.get(field_name, "")
        if not actual_val or actual_val == "None":
            similarities[field_name] = 0.0
            mismatches.append(field_name)
            continue

        if expected_val == actual_val:
            similarities[field_name] = 1.0
            continue

        if use_embeddings:
            sim = cosine_similarity(expected_val, actual_val)
            if sim is None:
                sim = token_overlap_similarity(expected_val, actual_val)
        else:
            sim = token_overlap_similarity(expected_val, actual_val)

        similarities[field_name] = round(sim, 4)
        if sim < 0.85:
            mismatches.append(field_name)

    text_fields = len(similarities)
    mean_score = (
        sum(similarities.values()) / text_fields if text_fields else 1.0
    )

    log.info(
        "semantic_score",
        text_fields=text_fields,
        mismatches=len(mismatches),
        score=round(mean_score, 4),
    )

    return {
        "score": round(mean_score, 4),
        "field_similarities": similarities,
        "semantic_mismatches": mismatches,
    }
