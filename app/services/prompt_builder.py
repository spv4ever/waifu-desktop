from __future__ import annotations

import random
from typing import Any

from app.domain.models import PromptDraft
from app.services.combo_key import make_combo_key
from app.services.ratios import resolve_size
from app.config.app_config import load_app_config


def build_random_combo(
    *,
    category: str,
    variant: str,
    ratio: str = "1:1",
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Genera un payload de combo a partir del config real.
    - category: define pools
    - variant: define mods/prefix/negatives
    - ratio: define width/height
    """
    cfg = load_app_config()
    rng = random.Random(seed) if seed is not None else random

    cat_cfg = cfg.categories.get(category, {})
    pools = cat_cfg.get("pools", {})

    defaults = cfg.defaults
    ratios = cfg.ratios

    width, height = resolve_size(
        ratios,
        ratio,
        fallback_w=int(defaults.get("width", 1024)),
        fallback_h=int(defaults.get("height", 1024)),
    )
    defaults = cfg.defaults
    ratios = cfg.ratios
    lock_steps = bool(cfg.raw.get("defaults", {}).get("lock_steps", False))
    combo = {
        "category": category,
        "variant": variant,
        "ratio": ratio,
        "outfit": rng.choice(pools.get("outfit", ["hoodie"])),
        "location": rng.choice(pools.get("location", ["street"])),
        "lighting": rng.choice(pools.get("lighting", ["soft daylight"])),
        "camera": rng.choice(pools.get("camera", ["50mm"])),
        "mood": rng.choice(pools.get("mood", ["relaxed"])),
        "mods": cfg.variants.get(variant, {}).get("mods", []),
        "width": width,
        "height": height,
        "filename_prefix": str(defaults.get("filename_prefix", "keiko")),
    }
    if not lock_steps:
        combo["steps"] = int(defaults.get("steps", 50))
    return combo


def build_prompt_from_combo(combo: dict[str, Any], *, index_in_pack: int | None = None) -> PromptDraft:
    cfg = load_app_config()
    vcfg = cfg.variants.get(combo["variant"], {})

    combo_key = make_combo_key(combo)

    # naming estable (para luego nombre de archivo/cola)
    num = f"{index_in_pack:04d}" if index_in_pack is not None else "0000"
    title = f"{combo['category'].title()} {combo['variant']} {num} — {combo['location']}"

    prefix = vcfg.get("prompt_prefix", "") or ""
    mods_txt = ""
    if combo.get("mods"):
        mods_txt = ", " + ", ".join(combo["mods"])

    prompt = (
        f"{prefix}Hyperreal portrait, {combo['mood']} mood, {combo['outfit']}, "
        f"scene in a {combo['location']}, {combo['lighting']}, shot on {combo['camera']}"
        f"{mods_txt}, high detail, natural skin texture, sharp focus."
    )

    negative_base = "lowres, blurry, deformed, extra fingers, bad anatomy, watermark, text"
    negative_append = vcfg.get("negative_append", "")
    negative = f"{negative_base}, {negative_append}".strip().strip(",")

    meta = {
        "combo": combo,
        "seed": None,
        "width": combo.get("width"),
        "height": combo.get("height"),
        "filename_prefix": combo.get("filename_prefix"),
        "ratio": combo.get("ratio"),
    }
    if "steps" in combo:
        meta["steps"] = combo["steps"]

    return PromptDraft(
        title=title,
        prompt_text=prompt,
        negative_text=negative,
        meta=meta,
        combo_key=combo_key,
    )
