"""Safe loading of model artifacts.

``joblib.load`` unpickles arbitrary objects, which means loading an attacker-controlled
file is remote code execution. Model artifact paths in this system come from the
``ModelRegistry`` table, so a tampered/poisoned registry row must never be able to point
the loader at a file outside the trusted models directory. ``safe_load_model`` enforces
that the resolved path lives under ``allowed_dir`` (the models directory) before loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def safe_load_model(path: str | Path, allowed_dir: str | Path | None = None) -> Any:
    """Load a joblib artifact, refusing any path outside ``allowed_dir``.

    Args:
        path: Path to the ``.joblib`` artifact (typically from the model registry).
        allowed_dir: Trusted directory the artifact must reside within. Defaults to the
            project ``models/`` directory.

    Raises:
        ValueError: if the resolved path escapes ``allowed_dir`` (e.g. ``../`` traversal
            or an absolute path elsewhere on disk).
        FileNotFoundError: if no file exists at the validated path.
    """
    base = Path(allowed_dir or MODELS_DIR).resolve()
    resolved = Path(path).resolve()

    if base != resolved and base not in resolved.parents:
        raise ValueError(
            f"Refusing to load model artifact outside trusted directory {base}: {resolved}"
        )
    if not resolved.is_file():
        raise FileNotFoundError(f"Model file not found: {resolved}")

    return joblib.load(resolved)
