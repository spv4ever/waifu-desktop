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


def _sig_from_combo(combo: dict[str, Any]) -> str:
    """
    Firma estable para evitar repeticiones.
    Incluye identidad/cámara/mood además de outfit/escena.
    """
    keys = [
        "category", "variant", "ratio_key", "ratio_tag",
        "combination_key",
        "base_subject",
        "face_features", "eye_style",
        "hair_color", "hair_style", "hair_detail",
        "camera_focal", "camera_framing", "camera_angle",
        "mood",
        "top", "bottom", "dress", "extra", "footwear",
        "pose", "background", "lighting",
    ]
    payload = "|".join(str(combo.get(k, "")) for k in keys)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _pick_from_grouped_dict(
    rng: random.Random,
    grouped: dict[str, list[str]] | None,
    fallback: str,
) -> str:
    if not grouped:
        return fallback
    groups = [v for v in grouped.values() if isinstance(v, list) and v]
    if not groups:
        return fallback
    return rng.choice(rng.choice(groups))


def _pick_from_list(rng: random.Random, items: list[str] | None, fallback: str) -> str:
    if not items:
        return fallback
    items2 = [x for x in items if isinstance(x, str) and x.strip()]
    if not items2:
        return fallback
    return rng.choice(items2)


def _build_ratios_plan(rng: random.Random, allowed_ratios: list[str], count: int) -> list[str]:
    """
    Garantiza variedad en batches pequeños:
    - baraja allowed_ratios y los “repite” hasta llegar a count
    """
    if not allowed_ratios:
        allowed_ratios = ["1:1"]
    plan: list[str] = []
    while len(plan) < count:
        chunk = list(allowed_ratios)
        rng.shuffle(chunk)
        plan.extend(chunk)
    return plan[:count]


def build_unique_prompts(
    catalog: WaifuCatalog,
    *,
    category_key: str,
    variant: str,
    count: int,
    combination_key: str | None = None,
    rng_seed: int | None = None,
    used_signatures: set[str] | None = None,
) -> list[BuiltPrompt]:
    used = used_signatures if used_signatures is not None else set()
    rng = random.Random(rng_seed)

    cat = catalog.categories.get(category_key)
    if not cat or not cat.get("enabled", True):
        raise ValueError(f"Categoría inválida o deshabilitada: {category_key}")

    defaults = catalog.defaults or {}
    base_subject = str(defaults.get("base_subject", "adult anime woman")).strip()
    quality_tags = defaults.get("quality_tags", []) or []

    allowed_ratios = list(cat.get("allowed_ratios") or ["1:1"])
    base_prompt = str(cat.get("base_prompt", "")).strip()
    kind = str(cat.get("kind", "category"))
    is_character = kind == "character"

    combinations = catalog.combinations or {}
    combination_prompt = ""
    if combination_key:
        combo_cfg = combinations.get(combination_key)
        if isinstance(combo_cfg, list):
            combination_prompt = ", ".join(
                [item for item in combo_cfg if isinstance(item, str) and item.strip()]
            ).strip()
        elif isinstance(combo_cfg, dict):
            combination_prompt = str(combo_cfg.get("prompt", "")).strip()
        else:
            raise ValueError(f"Combinación inválida: {combination_key}")

    negative_text = str(catalog.raw.get("negative_prompt") or "").strip()
    if not negative_text:
        negative_text = "low quality, blurry, bad anatomy, extra fingers, watermark, text"

    # Pools: wardrobe
    wardrobe = catalog.wardrobe or {}
    tops = wardrobe.get("tops", []) or []
    bottoms = wardrobe.get("bottoms", []) or []
    dresses = wardrobe.get("dresses", []) or []
    extras = wardrobe.get("extras", []) or []

    # Pools: grouped dicts
    pose_grouped = catalog.pose or {}
    bg_grouped = catalog.background or {}
    light_grouped = catalog.lighting or {}

    # Footwear dict
    footwear = catalog.footwear or {}

    # Identity
    identity = catalog.raw.get("identity", {}) or {}
    face_features_list = identity.get("face_features", []) or []
    eye_styles_list = identity.get("eye_styles", []) or []
    hair = identity.get("hair", {}) or {}
    hair_colors = hair.get("colors", []) or []
    hair_styles = hair.get("styles", []) or []
    hair_details = hair.get("details", []) or []

    # Camera
    camera = catalog.raw.get("camera", {}) or {}
    focal_lengths = camera.get("focal_lengths", []) or []
    framings = camera.get("framing", []) or []
    angles = camera.get("angle", []) or []

    # Mood
    mood_list = catalog.raw.get("mood", []) or []

    out: list[BuiltPrompt] = []
    attempts = 0
    max_attempts = count * 120

    # Plan de ratios para variedad
    ratios_plan = _build_ratios_plan(rng, allowed_ratios, count)

    # Diversidad suave por batch (cuando el batch es pequeño)
    small_batch = count <= 12
    used_bg: set[str] = set()
    used_pose: set[str] = set()
    used_light: set[str] = set()
    used_face: set[str] = set()
    used_hair: set[str] = set()

    while len(out) < count and attempts < max_attempts:
        attempts += 1

        # Ratio
        ratio_key = ratios_plan[len(out)]
        ratio_obj = catalog.ratios.get(ratio_key) or {}
        ratio_tag = str(ratio_obj.get("tag", ratio_key.replace(":", "x")))
        ratio_w = int(ratio_obj.get("width") or 1024)
        ratio_h = int(ratio_obj.get("height") or 1024)

        # Outfit logic
        use_dress = rng.random() < 0.35
        top = bottom = dress = ""
        if use_dress and dresses:
            dress = rng.choice(dresses)
        else:
            top = _pick_from_list(rng, tops, "")
            bottom = _pick_from_list(rng, bottoms, "")

        extra = _pick_from_list(rng, extras, "") if extras and rng.random() < 0.45 else ""

        # Pose / background / lighting
        pose = _pick_from_grouped_dict(rng, pose_grouped, "standing")
        bg = "" if is_character else _pick_from_grouped_dict(rng, bg_grouped, "simple background")
        light = _pick_from_grouped_dict(rng, light_grouped, "soft natural lighting")

        if small_batch:
            # Evita repetir dentro del batch: reintenta esa pieza 1 vez
            if bg in used_bg:
                bg = _pick_from_grouped_dict(rng, bg_grouped, bg)
            if pose in used_pose:
                pose = _pick_from_grouped_dict(rng, pose_grouped, pose)
            if light in used_light:
                light = _pick_from_grouped_dict(rng, light_grouped, light)

        # Footwear por categoría
        if category_key == "fantasy":
            footwear_pool = footwear.get("fantasy", [])
        elif category_key == "elegant":
            footwear_pool = footwear.get("elegant", [])
        elif category_key in ("streetwear", "cyberpunk"):
            footwear_pool = footwear.get("urban", [])
        else:
            footwear_pool = footwear.get("casual", [])

        footwear_pick = _pick_from_list(rng, footwear_pool, "sneakers")

        # Identity (anti sameface)
        if is_character:
            face_features = ""
            eye_style = ""
            hair_color = ""
            hair_style = ""
            hair_detail = ""
        else:
            face_features = _pick_from_list(rng, face_features_list, "distinct facial features")
            eye_style = _pick_from_list(rng, eye_styles_list, "expressive eyes")
            hair_color = _pick_from_list(rng, hair_colors, "chestnut brown")
            hair_style = _pick_from_list(rng, hair_styles, "long wavy hair")
            hair_detail = _pick_from_list(rng, hair_details, "loose strands framing the face")

        hair_key = f"{hair_color}|{hair_style}|{hair_detail}"

        if small_batch and not is_character:
            if face_features in used_face:
                face_features = _pick_from_list(rng, face_features_list, face_features)
            if hair_key in used_hair:
                hair_color = _pick_from_list(rng, hair_colors, hair_color)
                hair_style = _pick_from_list(rng, hair_styles, hair_style)
                hair_detail = _pick_from_list(rng, hair_details, hair_detail)
                hair_key = f"{hair_color}|{hair_style}|{hair_detail}"

        hair_desc = f"{hair_color} {hair_style}, {hair_detail}".strip().strip(",") if not is_character else ""

        # Camera
        camera_focal = _pick_from_list(rng, focal_lengths, "50mm look")
        camera_framing = _pick_from_list(rng, framings, "three-quarter shot")
        camera_angle = _pick_from_list(rng, angles, "eye-level angle")
        camera_desc = f"{camera_framing}, {camera_angle}, {camera_focal}".strip().strip(",")

        # Mood
        mood = _pick_from_list(rng, mood_list, "calm mood")

        outfit_parts = [p for p in [top, bottom, dress, extra, footwear_pick] if p]
        outfit_text = ", ".join(outfit_parts) if outfit_parts else "casual outfit"

        combo: dict[str, Any] = {
            "category": category_key,
            "variant": variant,
            "combination_key": combination_key,
            "ratio_key": ratio_key,
            "ratio_tag": ratio_tag,
            "width": ratio_w,
            "height": ratio_h,
            "base_subject": base_subject,

            "face_features": face_features,
            "eye_style": eye_style,
            "hair_color": hair_color,
            "hair_style": hair_style,
            "hair_detail": hair_detail,

            "camera_focal": camera_focal,
            "camera_framing": camera_framing,
            "camera_angle": camera_angle,

            "mood": mood,

            "top": top,
            "bottom": bottom,
            "dress": dress,
            "extra": extra,
            "footwear": footwear_pick,
            "pose": pose,
            "background": bg,
            "lighting": light,
        }

        signature = _sig_from_combo(combo)
        if signature in used:
            continue
        used.add(signature)

        # Ahora que ya fue aceptado, marcamos usados (para diversidad suave)
        if small_batch:
            used_bg.add(bg)
            used_pose.add(pose)
            used_light.add(light)
            used_face.add(face_features)
            used_hair.add(hair_key)

        quality_text = ", ".join([q for q in quality_tags if isinstance(q, str) and q.strip()])

        prompt_parts = [
            base_prompt,
            combination_prompt,
            base_subject,
            face_features,
            eye_style,
            hair_desc,
            outfit_text,
            pose,
            bg,
            light,
            camera_desc,
            mood,
            quality_text,
        ]
        prompt_text = ", ".join([p for p in prompt_parts if isinstance(p, str) and p.strip()]).strip().strip(",")

        cat_label = str(cat.get("label", category_key))
        if is_character:
            title = f"{cat_label} {variant}"
        else:
            title = f"{cat_label} {variant} — {bg}"

        meta = {"combo": combo}

        out.append(
            BuiltPrompt(
                title=title,
                prompt_text=prompt_text,
                negative_text=negative_text,
                meta=meta,
                signature=signature,
            )
        )

    if len(out) < count:
        raise RuntimeError(
            f"No se pudieron generar {count} prompts únicos. Generados={len(out)} (intentos={attempts}). "
            "Amplía pools (identity/camera/wardrobe) o reduce count."
        )

    return out
