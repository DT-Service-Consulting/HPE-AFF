"""
synthesis/program_cache.py — PF program cache keyed by form_id + template hash.

Programs are serialised as .py files under AFF_PROGRAM_CACHE_PATH.
"""
from __future__ import annotations
import hashlib
import json
import os
import structlog

log = structlog.get_logger()

DEFAULT_CACHE_PATH = os.environ.get(
    "AFF_PROGRAM_CACHE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "program_cache"),
)


def cache_key(form_id: str, template_pdf_path: str) -> str:
    """Compute cache key: form_id + SHA-256 of PDF bytes (first 8KB)."""
    try:
        with open(template_pdf_path, "rb") as f:
            pdf_bytes = f.read(8192)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    except FileNotFoundError:
        pdf_hash = "nopdf"
    return f"{form_id}_{pdf_hash}"


def save_program(
    key: str,
    program_source: str,
    metadata: dict | None = None,
    cache_dir: str | None = None,
) -> str:
    """Write a PF program to cache.

    Args:
        key:          Cache key (from cache_key()).
        program_source: Complete Python source string.
        metadata:     Optional dict saved as companion .json file.
        cache_dir:    Cache directory (default: AFF_PROGRAM_CACHE_PATH env var).

    Returns:
        Path to saved .py file.
    """
    cdir = cache_dir or DEFAULT_CACHE_PATH
    os.makedirs(cdir, exist_ok=True)

    py_path = os.path.join(cdir, f"{key}.py")
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(program_source)

    if metadata:
        meta_path = os.path.join(cdir, f"{key}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    log.info("program_saved", key=key, path=py_path)
    return py_path


def load_program(
    key: str,
    cache_dir: str | None = None,
) -> tuple[str | None, dict | None]:
    """Load a PF program from cache.

    Returns:
        (program_source, metadata) or (None, None) if not cached.
    """
    cdir = cache_dir or DEFAULT_CACHE_PATH
    py_path = os.path.join(cdir, f"{key}.py")
    meta_path = os.path.join(cdir, f"{key}.json")

    if not os.path.exists(py_path):
        log.info("program_cache_miss", key=key)
        return None, None

    with open(py_path, encoding="utf-8") as f:
        source = f.read()

    metadata = None
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)

    log.info("program_cache_hit", key=key, path=py_path)
    return source, metadata


def list_cached_programs(cache_dir: str | None = None) -> list[dict]:
    """List all cached programs with metadata."""
    cdir = cache_dir or DEFAULT_CACHE_PATH
    if not os.path.exists(cdir):
        return []

    programs = []
    for fname in sorted(os.listdir(cdir)):
        if not fname.endswith(".py"):
            continue
        key = fname[:-3]
        meta_path = os.path.join(cdir, f"{key}.json")
        metadata = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metadata = json.load(f)
        programs.append({"key": key, "path": os.path.join(cdir, fname), **metadata})

    return programs
