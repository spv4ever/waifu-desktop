import re

# OJO: aquí NO incluimos / ni \ porque vamos a permitir rutas relativas con carpetas.
INVALID_CHARS_SEGMENT = r'[<>:"|?*\x00-\x1F]'

def sanitize_segment(value: str) -> str:
    """
    Limpia un segmento (nombre de carpeta o archivo) para Windows.
    """
    if value is None:
        return ""
    s = str(value).strip()

    # 16:9 -> 16x9
    s = s.replace(":", "x")

    # elimina caracteres inválidos
    s = re.sub(INVALID_CHARS_SEGMENT, "_", s)

    # quita también separadores por si alguien mete barras en el segmento
    s = s.replace("/", "_").replace("\\", "_")

    # colapsa ____
    s = re.sub(r"_+", "_", s)

    return s.strip("._ ")

def sanitize_relpath(path: str) -> str:
    """
    Sanitiza una ruta relativa tipo anime/Waifu/v01/...
    Preserva subcarpetas usando /.
    """
    if not path:
        return ""
    # normaliza a /
    path = str(path).replace("\\", "/").strip().strip("/")

    parts = [p for p in path.split("/") if p]
    clean_parts = [sanitize_segment(p) for p in parts]

    # evita segmentos vacíos
    clean_parts = [p for p in clean_parts if p]
    return "/".join(clean_parts)
