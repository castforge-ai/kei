"""An imported character's base colour texture: raw 8-bit RGB rows (top row first), written once by kei import with
ffmpeg, read here with the standard library. sample() reads it at (u, v), v from the top, with bilinear filtering;
u and v wrap, as texture coordinates do."""
from __future__ import annotations

import math


def load_texture(ch, index: int = 0):
    """(width, height, bytes) of the character's texture index (0, the first), or None when it has none. Cached on
    the character. A texture the character names that is missing, unreadable or not width x height x 3 bytes raises
    CharacterError naming the file: drawn untextured, the fault would pass for the model's own colours."""
    from kei.characters import CharacterError
    cache = ch.__dict__.setdefault("_textures", {})
    if index in cache:
        return cache[index]
    tex = None
    infos = getattr(ch, "textures", None) or ([ch.texture] if getattr(ch, "texture", None) else [])
    info = infos[index] if 0 <= index < len(infos) else None
    if info and ch.folder is not None:
        path = ch.folder / info["file"]
        w, h = int(info["width"]), int(info["height"])
        try:
            data = path.read_bytes()
        except OSError as e:
            raise CharacterError(f"{ch.name}: cannot read its texture {path} ({e}); import the model again") from e
        if not (w > 0 and h > 0 and len(data) == w * h * 3):
            raise CharacterError(f"{ch.name}: its texture {path} holds {len(data)} bytes, not the {w} x {h} x 3 its "
                                 "character.json says; import the model again")
        tex = (w, h, data)
    cache[index] = tex
    return tex


def sample(tex, u: float, v: float) -> tuple[int, int, int]:
    """The texture's colour at (u, v), bilinear between the four nearest texel centres."""
    w, h, data = tex
    x = (u - math.floor(u)) * w - 0.5
    y = (v - math.floor(v)) * h - 0.5
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    x0c, x1c = min(max(x0, 0), w - 1), min(max(x0 + 1, 0), w - 1)
    y0c, y1c = min(max(y0, 0), h - 1), min(max(y0 + 1, 0), h - 1)
    i00, i10 = (y0c * w + x0c) * 3, (y0c * w + x1c) * 3
    i01, i11 = (y1c * w + x0c) * 3, (y1c * w + x1c) * 3
    out = []
    for k in range(3):
        top = data[i00 + k] + (data[i10 + k] - data[i00 + k]) * fx
        bot = data[i01 + k] + (data[i11 + k] - data[i01 + k]) * fx
        out.append(round(top + (bot - top) * fy))
    return tuple(out)
