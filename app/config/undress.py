UNDRESS_GARMENTS = (
    "dress",
    "tank top",
    "bra",
    "bikini top",
    "bikini",
    "bikini buttom",
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

UNDRESS_SECONDS_PER_GARMENT = 4.0
UNDRESS_FPS = 24

UNDRESS_PROMPT_TEMPLATE = (
    "A seductive woman {garment_actions}, exposing her naked breasts and nude body.\n"
    "She seductively swaying rhythmically from side to side, her body twisting to reveal each "
    "contour and curve in a hypnotic display."
)


def format_undress_garments(garments: list[str] | tuple[str, ...]) -> str:
    """Return one undressing action with the selected garments comma-separated."""
    cleaned = [garment.strip() for garment in garments if garment.strip()]
    if not cleaned:
        cleaned = [UNDRESS_GARMENTS[0]]

    garment_text = ", ".join(cleaned)
    return f"effortlessly tears apart her {garment_text} then pulls it down to fall away"


def build_undress_prompt(garments: list[str] | tuple[str, ...]) -> str:
    """Build an Undress prompt containing every checked garment."""
    return UNDRESS_PROMPT_TEMPLATE.format(
        garment_actions=format_undress_garments(garments)
    )


def calculate_undress_duration(
    garments: list[str] | tuple[str, ...],
) -> tuple[float, int]:
    """Scale the video duration so every accumulated garment gets four seconds."""
    garment_count = max(sum(bool(garment.strip()) for garment in garments), 1)
    seconds = UNDRESS_SECONDS_PER_GARMENT * garment_count
    # Wan lengths include the initial frame: four seconds at 24 fps is 97 frames.
    frames = int(seconds * UNDRESS_FPS) + 1
    return seconds, frames
