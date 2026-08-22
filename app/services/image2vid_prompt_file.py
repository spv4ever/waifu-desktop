from __future__ import annotations

import re


_PROMPT_HEADER = re.compile(r"(?im)^\s*Prompt\s+(\d+)\s*:\s*")


def parse_image2vid_long_prompts(text: str) -> list[str]:
    """Extract numbered prompts from an Image2Vid Long prompts.txt file.

    Project metadata such as ``Seed: ...`` is deliberately ignored. Prompt bodies
    may span multiple lines and are returned in their numeric order.
    """
    text = text.lstrip("\ufeff")
    matches = list(_PROMPT_HEADER.finditer(text))
    if not matches:
        raise ValueError("El archivo no contiene bloques con el formato 'Prompt 1:'.")

    numbered_prompts: list[tuple[int, str]] = []
    seen_numbers: set[int] = set()
    for index, match in enumerate(matches):
        number = int(match.group(1))
        if number in seen_numbers:
            raise ValueError(f"El archivo contiene el Prompt {number} más de una vez.")
        seen_numbers.add(number)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        prompt = text[match.end():end].strip()
        if not prompt:
            raise ValueError(f"El Prompt {number} está vacío.")
        numbered_prompts.append((number, prompt))

    numbered_prompts.sort(key=lambda item: item[0])
    return [prompt for _number, prompt in numbered_prompts]
