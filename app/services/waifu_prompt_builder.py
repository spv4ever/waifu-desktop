from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from app.config.waifu_catalog import WaifuCatalog


@dataclass(frozen=True)
class BuiltPrompt:
    title: str
    prompt_text: str
    negative_text: str
    meta: dict[str, Any]
    signature: str


def _sig_from_meta(meta: dict[str, Any]) -> str:
    # Firma estable para evitar repeticiones (orden determinista)
    # Usamos campos clave del combo.
    combo = meta.get("combo", {})
    payload = "|".join([
        str(combo.get("category", "")),
        str(combo.get("variant", "")),
        str(combo.get("ratio_key", "")),
        str(combo.get("top", "")),
        str(combo.get("bottom", "")),
        str(combo.get("dress", "")),
        str(combo.get("extra", "")),
        str(combo.get("footwear", "")),
        str(combo.get("pose", "")),
        str(combo.get("background", "")),
        str(combo.get("lighting", "")),
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_unique_prompts(
    catalog: WaifuCatalog,
    *,
    category_key: str,
    variant: str,
    count: int,
    rng_seed: int | None = None,
    used_signatures: set[str] | None = None,
) -> list[BuiltPrompt]:
    """
    Genera `count` prompts únicos (por firma) para una categoría + variante.
    """
    used = used_signatures if used_signatures is not None else set()
    rng = random.Random(rng_seed)

    cat = catalog.categories.get(category_key)
    if not cat or not cat.get("enabled", True):
        raise ValueError(f"Categoría inválida o deshabilitada: {category_key}")

    allowed_ratios = cat.get("allowed_ratios") or ["1:1"]
    base_prompt = str(cat.get("base_prompt", "")).strip()
    quality_tags = catalog.defaults.get("quality_tags", [])

    # Pools
    tops = catalog.wardrobe.get("tops", [])
    bottoms = catalog.wardrobe.get("bottoms", [])
    dresses = catalog.wardrobe.get("dresses", [])
    extras = catalog.wardrobe.get("extras", [])

    pose_groups = list(catalog.pose.values()) or []
    bg_groups = list(catalog.background.values()) or []
    light_groups = list(catalog.lighting.values()) or []

    # Negative base (puedes ampliarlo luego)
    negative_text = "low quality, blurry, bad anatomy, extra fingers, watermark, text"

    out: list[BuiltPrompt] = []
    attempts = 0
    max_attempts = count * 50  # suficiente margen

    while len(out) < count and attempts < max_attempts:
        attempts += 1

        ratio_key = rng.choice(allowed_ratios)
        ratio_obj = catalog.ratios.get(ratio_key) or {}
        ratio_tag = str(ratio_obj.get("tag", ratio_key.replace(":", "x")))

        # Outfit logic: o dress o (top+bottom), más optional extra
        use_dress = rng.random() < 0.35
        top = bottom = dress = ""
        if use_dress and dresses:
            dress = rng.choice(dresses)
        else:
            if tops:
                top = rng.choice(tops)
            if bottoms:
                bottom = rng.choice(bottoms)

        extra = rng.choice(extras) if extras and rng.random() < 0.45 else ""

        # Pose, background, lighting
        pose = rng.choice(rng.choice(pose_groups)) if pose_groups else "standing"
        bg = rng.choice(rng.choice(bg_groups)) if bg_groups else "simple background"
        light = rng.choice(rng.choice(light_groups)) if light_groups else "soft natural lighting"

        # Footwear: por categoría (heurística)
        if category_key in ("fantasy",):
            footwear_pool = catalog.footwear.get("fantasy", [])
        elif category_key in ("elegant",):
            footwear_pool = catalog.footwear.get("elegant", [])
        elif category_key in ("streetwear", "cyberpunk"):
            footwear_pool = catalog.footwear.get("urban", [])
        else:
            footwear_pool = catalog.footwear.get("casual", [])

        footwear = rng.choice(footwear_pool) if footwear_pool else "sneakers"

        # Combo/meta (trazable)
        combo = {
            "category": category_key,
            "variant": variant,
            "ratio_key": ratio_key,   # semántico (puede llevar :)
            "ratio_tag": ratio_tag,   # seguro para naming
            "top": top,
            "bottom": bottom,
            "dress": dress,
            "extra": extra,
            "footwear": footwear,
            "pose": pose,
            "background": bg,
            "lighting": light,
        }

        meta = {"combo": combo}
        sig = _sig_from_meta(meta)
        if sig in used:
            continue
        used.add(sig)

        # Prompt final
        outfit_parts = [p for p in [top, bottom, dress, extra, footwear] if p]
        outfit_text = ", ".join(outfit_parts) if outfit_parts else "casual outfit"

        quality_text = ", ".join(quality_tags) if quality_tags else ""
        prompt_parts = [
            base_prompt,
            outfit_text,
            pose,
            bg,
            light,
            quality_text,
        ]
        prompt_text = ", ".join([p for p in prompt_parts if p]).strip().strip(",")

        # Title
        title = f"{cat.get('label', category_key)} {variant} — {bg}"

        out.append(
            BuiltPrompt(
                title=title,
                prompt_text=prompt_text,
                negative_text=negative_text,
                meta=meta,
                signature=sig,
            )
        )

    if len(out) < count:
        raise RuntimeError(
            f"No se pudieron generar {count} prompts únicos. Generados={len(out)} "
            f"(intentos={attempts}). Amplía pools o reduce count."
        )

    return out
