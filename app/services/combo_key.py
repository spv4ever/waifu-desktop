from __future__ import annotations

import hashlib
import json
from typing import Any


def make_combo_key(payload: dict[str, Any]) -> str:
    """
    Devuelve una clave estable para una combinación de parámetros.
    - Canonicaliza JSON (ordenado, sin espacios)
    - Hash SHA1 (suficiente y rápido para dedupe; si prefieres SHA256, cambiamos)
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()
