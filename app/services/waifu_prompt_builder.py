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
        "combination_prompt",
        "manual_prompt",
        "base_subject",
        "face_features", "eye_style",
        "hair_color", "hair_style", "hair_detail",
        "camera_focal", "camera_framing", "camera_angle",
        "mood",
        "top", "bottom", "dress", "extra", "footwear",
        "pose", "background", "lighting",
        "custom_groups_signature",
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


def _pick_fixed_from_list(items: list[str] | None, fallback: str) -> str:
    if not items:
        return fallback
    items2 = [x for x in items if isinstance(x, str) and x.strip()]
    if not items2:
        return fallback
    return items2[0]


def _pick_fixed_from_grouped_dict(grouped: dict[str, list[str]] | None, fallback: str) -> str:
    if not grouped:
        return fallback
    for _, values in grouped.items():
        if isinstance(values, list):
            items = [x for x in values if isinstance(x, str) and x.strip()]
            if items:
                return items[0]
    return fallback


def _extract_group_values(root: dict[str, Any] | None, group_key: str) -> list[str]:
    if not root or not group_key:
        return []
    parts = [part.strip() for part in group_key.split(".") if part.strip()]
    if not parts:
        return []
    current: Any = root
    for part in parts:
        if not isinstance(current, dict):
            return []
        current = current.get(part)
    if isinstance(current, list):
        return [str(item) for item in current if isinstance(item, (str, int, float)) and str(item).strip()]
    return []


def _normalize_iteration_groups(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        return set()
    return {item.lower() for item in items}


def _merge_nested_dict(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base or {})
    if not isinstance(override, dict):
        return merged
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dict(merged.get(key), value)
        else:
            merged[key] = value
    return merged


def _select_list(base: list[str] | None, override: Any) -> list[str]:
    if isinstance(override, list):
        return override
    return list(base or [])


def _character_variations(raw: dict[str, Any], character_key: str) -> dict[str, Any]:
    for prefix in ("characters", "character"):
        scoped = raw.get(prefix)
        if not isinstance(scoped, dict):
            continue
        data = scoped.get(character_key)
        if isinstance(data, dict):
            return data
    return {}


def _build_combination_prompt(
    rng: random.Random,
    combo_cfg: list[str] | dict[str, Any] | None,
    *,
    pick_count: int | None = None,
) -> str:
    if not combo_cfg:
        return ""
    if isinstance(combo_cfg, list):
        items = [item for item in combo_cfg if isinstance(item, str) and item.strip()]
        if not items:
            return ""
        if pick_count is None:
            pick_count = rng.randint(1, len(items))
        else:
            pick_count = max(1, min(pick_count, len(items)))
        return ", ".join(rng.sample(items, pick_count)).strip()
    if isinstance(combo_cfg, dict):
        parts = [str(combo_cfg.get("prompt", "")).strip()]
        options = combo_cfg.get("options", [])
        if isinstance(options, list):
            choices = [
                item.strip()
                for item in options
                if isinstance(item, str) and item.strip()
            ]
            if choices:
                configured_count = combo_cfg.get("pick_count", 1)
                try:
                    option_count = int(configured_count)
                except (TypeError, ValueError):
                    option_count = 1
                option_count = max(1, min(option_count, len(choices)))
                parts.extend(rng.sample(choices, option_count))
        return ", ".join(part for part in parts if part).strip()
    raise ValueError("Combinación inválida")


def _apply_nsfw_prefix(prompt: str) -> str:
    parts = [p.strip() for p in str(prompt or "").split(",") if p.strip()]
    parts = [p for p in parts if p.lower() != "nsfw"]
    return ", ".join(["nsfw", *parts]).strip().strip(",")


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
    nsfw_tag_count: int | None = None,
    manual_prompt: str | None = None,
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
    manual_prompt_text = str(manual_prompt or "").strip()
    kind = str(cat.get("kind", "category"))
    is_character = kind == "character"
    character_variations = _character_variations(catalog.raw, category_key) if is_character else {}
    raw_iteration_groups = cat.get("iteration_groups") or []
    iteration_groups = _normalize_iteration_groups(raw_iteration_groups)
    has_iteration_groups = bool(iteration_groups)
    standard_iteration_groups = {
        "identity",
        "outfit",
        "pose",
        "background",
        "lighting",
        "camera",
        "mood",
    }
    custom_iteration_groups: list[str] = []
    if isinstance(raw_iteration_groups, str):
        raw_parts = [part.strip() for part in raw_iteration_groups.split(",") if part.strip()]
    elif isinstance(raw_iteration_groups, list):
        raw_parts = [str(part).strip() for part in raw_iteration_groups if str(part).strip()]
    else:
        raw_parts = []
    for group_key in raw_parts:
        if group_key.lower() not in standard_iteration_groups:
            custom_iteration_groups.append(group_key)

    if has_iteration_groups:
        iterate_identity = "identity" in iteration_groups
        iterate_outfit = "outfit" in iteration_groups
        iterate_pose = "pose" in iteration_groups
        iterate_background = "background" in iteration_groups
        iterate_lighting = "lighting" in iteration_groups
        iterate_camera = "camera" in iteration_groups
        iterate_mood = "mood" in iteration_groups
    else:
        iterate_identity = not is_character
        iterate_outfit = True
        iterate_pose = True
        iterate_background = not is_character
        iterate_lighting = True
        iterate_camera = True
        iterate_mood = True

    include_identity = iterate_identity or not has_iteration_groups
    include_outfit = iterate_outfit or not has_iteration_groups
    include_pose = iterate_pose or not has_iteration_groups
    include_background = iterate_background or not has_iteration_groups
    include_lighting = iterate_lighting or not has_iteration_groups
    include_camera = iterate_camera or not has_iteration_groups
    include_mood = iterate_mood or not has_iteration_groups

    combinations = _merge_nested_dict(catalog.combinations or {}, character_variations.get("combinations"))
    combination_prompt = ""
    combo_cfg: list[str] | dict[str, Any] | None = None
    if combination_key:
        combo_cfg = combinations.get(combination_key)
        if not isinstance(combo_cfg, (list, dict)):
            raise ValueError(f"Combinación inválida: {combination_key}")
        pick_count = nsfw_tag_count if combination_key == "nsfw" else None
        combination_prompt = _build_combination_prompt(rng, combo_cfg, pick_count=pick_count)
        if combination_key == "nsfw":
            combination_prompt = _apply_nsfw_prefix(combination_prompt)

    negative_text = str(catalog.raw.get("negative_prompt") or "").strip()
    if not negative_text:
        negative_text = "low quality, blurry, bad anatomy, extra fingers, watermark, text"

    # Pools: wardrobe
    wardrobe = _merge_nested_dict(catalog.wardrobe or {}, character_variations.get("wardrobe"))
    tops = wardrobe.get("tops", []) or []
    bottoms = wardrobe.get("bottoms", []) or []
    dresses = wardrobe.get("dresses", []) or []
    extras = wardrobe.get("extras", []) or []

    # Pools: grouped dicts
    pose_grouped = _merge_nested_dict(catalog.pose or {}, character_variations.get("pose"))
    bg_grouped = _merge_nested_dict(catalog.background or {}, character_variations.get("background"))
    light_grouped = _merge_nested_dict(catalog.lighting or {}, character_variations.get("lighting"))

    # Footwear dict
    footwear = _merge_nested_dict(catalog.footwear or {}, character_variations.get("footwear"))

    # Identity
    identity = _merge_nested_dict(catalog.raw.get("identity", {}) or {}, character_variations.get("identity"))
    face_features_list = identity.get("face_features", []) or []
    eye_styles_list = identity.get("eye_styles", []) or []
    hair = identity.get("hair", {}) or {}
    hair_colors = hair.get("colors", []) or []
    hair_styles = hair.get("styles", []) or []
    hair_details = hair.get("details", []) or []

    # Camera
    camera = _merge_nested_dict(catalog.raw.get("camera", {}) or {}, character_variations.get("camera"))
    focal_lengths = camera.get("focal_lengths", []) or []
    framings = camera.get("framing", []) or []
    angles = camera.get("angle", []) or []

    # Mood
    mood_list = _select_list(catalog.raw.get("mood", []) or [], character_variations.get("mood"))

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
        if combo_cfg is not None:
            pick_count = nsfw_tag_count if combination_key == "nsfw" else None
            combination_prompt = _build_combination_prompt(rng, combo_cfg, pick_count=pick_count)
            if combination_key == "nsfw":
                combination_prompt = _apply_nsfw_prefix(combination_prompt)

        # Ratio
        ratio_key = ratios_plan[len(out)]
        ratio_obj = catalog.ratios.get(ratio_key) or {}
        ratio_tag = str(ratio_obj.get("tag", ratio_key.replace(":", "x")))
        ratio_w = int(ratio_obj.get("width") or 1024)
        ratio_h = int(ratio_obj.get("height") or 1024)

        # Outfit logic
        top = bottom = dress = ""
        if include_outfit and iterate_outfit:
            use_dress = rng.random() < 0.35
            if use_dress and dresses:
                dress = rng.choice(dresses)
            else:
                top = _pick_from_list(rng, tops, "")
                bottom = _pick_from_list(rng, bottoms, "")
            extra = _pick_from_list(rng, extras, "") if extras and rng.random() < 0.45 else ""
        elif include_outfit:
            if dresses:
                dress = _pick_fixed_from_list(dresses, "")
            else:
                top = _pick_fixed_from_list(tops, "")
                bottom = _pick_fixed_from_list(bottoms, "")
            extra = _pick_fixed_from_list(extras, "") if extras else ""
        else:
            top = bottom = dress = extra = ""

        # Pose / background / lighting
        if include_pose and iterate_pose:
            pose = _pick_from_grouped_dict(rng, pose_grouped, "standing")
        elif include_pose:
            pose = _pick_fixed_from_grouped_dict(pose_grouped, "standing")
        else:
            pose = ""

        if include_background and iterate_background:
            bg = _pick_from_grouped_dict(rng, bg_grouped, "simple background")
        elif include_background and is_character:
            bg = ""
        elif include_background:
            bg = _pick_fixed_from_grouped_dict(bg_grouped, "simple background")
        else:
            bg = ""

        if include_lighting and iterate_lighting:
            light = _pick_from_grouped_dict(rng, light_grouped, "soft natural lighting")
        elif include_lighting:
            light = _pick_fixed_from_grouped_dict(light_grouped, "soft natural lighting")
        else:
            light = ""

        if small_batch:
            # Evita repetir dentro del batch: reintenta esa pieza 1 vez
            if iterate_background and bg in used_bg:
                bg = _pick_from_grouped_dict(rng, bg_grouped, bg)
            if iterate_pose and pose in used_pose:
                pose = _pick_from_grouped_dict(rng, pose_grouped, pose)
            if iterate_lighting and light in used_light:
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

        if include_outfit and iterate_outfit:
            footwear_pick = _pick_from_list(rng, footwear_pool, "sneakers")
        elif include_outfit:
            footwear_pick = _pick_fixed_from_list(footwear_pool, "sneakers")
        else:
            footwear_pick = ""

        # Identity (anti sameface)
        if include_identity and iterate_identity:
            face_features = _pick_from_list(rng, face_features_list, "distinct facial features")
            eye_style = _pick_from_list(rng, eye_styles_list, "expressive eyes")
            hair_color = _pick_from_list(rng, hair_colors, "chestnut brown")
            hair_style = _pick_from_list(rng, hair_styles, "long wavy hair")
            hair_detail = _pick_from_list(rng, hair_details, "loose strands framing the face")
        elif include_identity and is_character:
            face_features = ""
            eye_style = ""
            hair_color = ""
            hair_style = ""
            hair_detail = ""
        elif include_identity:
            face_features = _pick_fixed_from_list(face_features_list, "distinct facial features")
            eye_style = _pick_fixed_from_list(eye_styles_list, "expressive eyes")
            hair_color = _pick_fixed_from_list(hair_colors, "chestnut brown")
            hair_style = _pick_fixed_from_list(hair_styles, "long wavy hair")
            hair_detail = _pick_fixed_from_list(hair_details, "loose strands framing the face")
        else:
            face_features = ""
            eye_style = ""
            hair_color = ""
            hair_style = ""
            hair_detail = ""

        hair_key = f"{hair_color}|{hair_style}|{hair_detail}"

        if small_batch and iterate_identity:
            if face_features in used_face:
                face_features = _pick_from_list(rng, face_features_list, face_features)
            if hair_key in used_hair:
                hair_color = _pick_from_list(rng, hair_colors, hair_color)
                hair_style = _pick_from_list(rng, hair_styles, hair_style)
                hair_detail = _pick_from_list(rng, hair_details, hair_detail)
                hair_key = f"{hair_color}|{hair_style}|{hair_detail}"

        if any([hair_color, hair_style, hair_detail]):
            hair_desc = f"{hair_color} {hair_style}, {hair_detail}".strip().strip(",")
        else:
            hair_desc = ""

        # Camera
        if include_camera and iterate_camera:
            camera_focal = _pick_from_list(rng, focal_lengths, "50mm look")
            camera_framing = _pick_from_list(rng, framings, "three-quarter shot")
            camera_angle = _pick_from_list(rng, angles, "eye-level angle")
        elif include_camera:
            camera_focal = _pick_fixed_from_list(focal_lengths, "50mm look")
            camera_framing = _pick_fixed_from_list(framings, "three-quarter shot")
            camera_angle = _pick_fixed_from_list(angles, "eye-level angle")
        else:
            camera_focal = ""
            camera_framing = ""
            camera_angle = ""
        camera_desc = f"{camera_framing}, {camera_angle}, {camera_focal}".strip().strip(",")

        # Mood
        if include_mood and iterate_mood:
            mood = _pick_from_list(rng, mood_list, "calm mood")
        elif include_mood:
            mood = _pick_fixed_from_list(mood_list, "calm mood")
        else:
            mood = ""

        custom_group_values: list[str] = []
        custom_group_signature_parts: list[str] = []
        custom_group_map: dict[str, str] = {}
        for group_key in custom_iteration_groups:
            values = _extract_group_values(character_variations, group_key)
            if not values:
                values = _extract_group_values(catalog.raw, group_key)
            if not values:
                continue
            pick = _pick_from_list(rng, values, "")
            if not pick:
                continue
            custom_group_values.append(pick)
            custom_group_signature_parts.append(f"{group_key}:{pick}")
            custom_group_map[group_key] = pick
        custom_groups_signature = "|".join(custom_group_signature_parts)

        outfit_parts = [p for p in [top, bottom, dress, extra, footwear_pick] if p]
        if include_outfit:
            outfit_text = ", ".join(outfit_parts) if outfit_parts else "casual outfit"
        else:
            outfit_text = ""

        combo: dict[str, Any] = {
            "category": category_key,
            "variant": variant,
            "combination_key": combination_key,
            "combination_prompt": combination_prompt,
            "manual_prompt": manual_prompt_text,
            "ratio_key": ratio_key,
            "ratio_tag": ratio_tag,
            "width": ratio_w,
            "height": ratio_h,
            "base_subject": base_subject,
            "custom_groups": custom_group_map,
            "custom_groups_signature": custom_groups_signature,

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
            if iterate_background and bg:
                used_bg.add(bg)
            if iterate_pose and pose:
                used_pose.add(pose)
            if iterate_lighting and light:
                used_light.add(light)
            if iterate_identity and face_features:
                used_face.add(face_features)
            if iterate_identity and hair_key.strip("|"):
                used_hair.add(hair_key)

        quality_text = ", ".join([q for q in quality_tags if isinstance(q, str) and q.strip()])

        prompt_parts = [
            combination_prompt,
            base_prompt,
            manual_prompt_text,
            base_subject,
            *custom_group_values,
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
