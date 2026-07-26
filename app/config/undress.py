UNDRESS_GARMENTS = (
    "dress",
    "tank top",
    "bra",
    "bikini top",
    "panties",
    "t-shirt",
    "skirt",
    "blouse",
    "shorts",
    "jeans",
    "stockings",
    "jacket",
    "attire",
    "shirt and pants",
)

UNDRESS_PROMPT_TEMPLATE = (
    "A seductive woman {garment_actions}, exposing her naked breasts and nude body.\n"
    "She seductively swaying rhythmically from side to side, her body twisting to reveal each "
    "contour and curve in a hypnotic display."
)


def format_undress_garments(garments: list[str] | tuple[str, ...]) -> str:
    """Return a complete undressing action for every selected garment."""
    cleaned = [garment.strip() for garment in garments if garment.strip()]
    if not cleaned:
        cleaned = [UNDRESS_GARMENTS[0]]

    actions = [
        f"effortlessly tears apart her {garment} then pulls it down to fall away"
        for garment in cleaned
    ]
    if len(actions) == 1:
        return actions[0]
    if len(actions) == 2:
        return " and ".join(actions)
    return f"{', '.join(actions[:-1])}, and {actions[-1]}"


def build_undress_prompt(garments: list[str] | tuple[str, ...]) -> str:
    """Build an Undress prompt containing every checked garment."""
    return UNDRESS_PROMPT_TEMPLATE.format(
        garment_actions=format_undress_garments(garments)
    )
