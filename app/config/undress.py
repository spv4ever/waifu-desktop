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
    "A seductive woman effortlessly tears apart her {garment}, then pulls it down to fall away, "
    "exposing her naked breasts and nude body. Masturbating, showing her pussy, \n"
    "She seductively swaying rhythmically from side to side, her body twisting to reveal each "
    "contour and curve in a hypnotic display."
)


def format_undress_garments(garments: list[str] | tuple[str, ...]) -> str:
    """Return a natural-language list suitable for the Undress prompt."""
    cleaned = [garment.strip() for garment in garments if garment.strip()]
    if not cleaned:
        return UNDRESS_GARMENTS[0]
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return " and ".join(cleaned)
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def build_undress_prompt(garments: list[str] | tuple[str, ...]) -> str:
    """Build an Undress prompt containing every checked garment."""
    return UNDRESS_PROMPT_TEMPLATE.format(garment=format_undress_garments(garments))
