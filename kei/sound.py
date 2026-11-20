"""Shots timed to sound: a sound or dialogue track in the shot, read frame by frame, so its beats can drive the timing.

add_sound(shot, path, fps, frames, offset, words) -> dict
  Copies the track into <shot>/sound/ (a WAV is read as it is; any other file is turned into a WAV with ffmpeg when
  it is installed) and writes:
    sound/sound.json   the track, the fps, the offset (the sound frame that plays on frame 0), and per shot frame:
                       "level" (0 to 1, the loudness of that frame), "beats" (frames where the sound hits: a sharp rise
                       to a local peak) and "phrases" ([[first, last, words], ...]: stretches of sound between
                       silences; the words come from --words, one line per phrase, in order).
    sound/waveform.png the level per frame with a tick per 4 frames, the beats in red and the phrases as bars. The
                       live page and the report show it with the other sheets.
    sound/XSHEET.md    one row per frame: the level as a bar, the beat mark and the phrase words, the sound column of
                       an exposure sheet, for the plan stage to time against.
snap(shot dict, beats, within, frames) is kei keys snap: each key moves to the nearest beat at most within frames
  away, keeping the keys in order and never moving a key onto another. The loop's last key stays on the last frame.
Kei reads PCM WAV with the standard library. It plays nothing and sends the sound nowhere.
"""
from __future__ import annotations

import array
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

from kei.sheet import _Canvas

SOUND_DIR = "sound"
SILENCE = 0.08       # a frame under this share of the loudest frame is silence
MERGE_GAP = 6        # silences shorter than this many frames do not split a phrase
MIN_PHRASE = 3
BEAT_RISE = 0.18     # a beat rises at least this share of the loudest frame over the three frames before it
BEAT_GAP = 4         # beats closer than this are one beat


class SoundError(ValueError):
    """The sound cannot be read or placed. The message says why and what to do."""


def _to_wav(src: Path, dst: Path) -> Path:
    if src.suffix.lower() == ".wav":
        shutil.copyfile(src, dst)
        return dst
    ff = shutil.which("ffmpeg")
    if ff is None:
        raise SoundError(f"{src.name} is not a WAV and ffmpeg is not installed: install ffmpeg, or give a .wav file")
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "22050",
                        "-sample_fmt", "s16", str(dst)], capture_output=True, text=True)
    if r.returncode != 0 or not dst.is_file():
        raise SoundError(f"ffmpeg could not read {src.name}: {(r.stderr or '').strip()[:200]}")
    return dst


def read_levels(wav: Path, fps: float) -> list[float]:
    """The RMS loudness of each frame of the track, scaled so the loudest frame is 1."""
    try:
        with wave.open(str(wav), "rb") as w:
            width, ch, rate, n = w.getsampwidth(), w.getnchannels(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError, OSError) as e:
        raise SoundError(f"{wav.name} is not a PCM WAV Kei can read: {e}") from e
    if width == 2:
        samples = array.array("h", raw)
    elif width == 1:
        samples = array.array("h", ((b - 128) * 256 for b in raw))
    elif width == 4:
        samples = array.array("i", raw)
    else:
        raise SoundError(f"{wav.name} has {8 * width}-bit samples: Kei reads 8, 16 or 32 bit PCM")
    if ch > 1:
        samples = array.array(samples.typecode, samples[::ch])
    per = rate / fps
    count = max(1, math.ceil(len(samples) / per))
    out = []
    for f in range(count):
        part = samples[int(f * per):int((f + 1) * per)]
        out.append(math.sqrt(sum(x * x for x in part) / len(part)) if len(part) else 0.0)
    top = max(out) or 1.0
    return [round(v / top, 4) for v in out]


def beats(levels: list[float]) -> list[int]:
    out: list[int] = []
    for f in range(len(levels)):
        before = levels[max(0, f - 3):f] or [0.0]
        if levels[f] - min(before) < BEAT_RISE:
            continue
        near = levels[max(0, f - 2):f + 3]
        if levels[f] < max(near):
            continue
        if out and f - out[-1] < BEAT_GAP:
            continue
        out.append(f)
    return out


def phrases(levels: list[float]) -> list[list[int]]:
    loud = [v >= SILENCE for v in levels]
    runs, start = [], None
    for f, on in enumerate(loud + [False]):
        if on and start is None:
            start = f
        elif not on and start is not None:
            runs.append([start, f - 1])
            start = None
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] - 1 < MERGE_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] + 1 >= MIN_PHRASE]


def waveform_png(levels: list[float], hits: list[int], spans: list[list], px: int = 6, h: int = 140) -> bytes:
    w = max(1, len(levels)) * px + 20
    cv = _Canvas(w, h)
    base, top = h - 30, 16
    for f, v in enumerate(levels):
        x = 10 + f * px
        y = base - int(v * (base - top))
        for xx in range(x, x + px - 1):
            cv.line(xx, base, xx, y, (90, 110, 140), False)
        if f % 4 == 0:
            cv.line(x, base + 2, x, base + (8 if f % 24 == 0 else 5), (120, 120, 120), False)
    for f in hits:
        x = 10 + f * px
        for xx in range(x, x + max(2, px - 2)):
            cv.line(xx, top - 2, xx, base, (200, 40, 30), False)
    for p in spans:
        x0, x1 = 10 + p[0] * px, 10 + (p[1] + 1) * px - 1
        cv.line(x0, h - 16, x1, h - 16, (40, 130, 80), True)
        if len(p) > 2 and p[2]:
            cv.text(x0, h - 11, p[2], (40, 130, 80), max(0, x1 - x0))
    cv.text(10, 2, "sound: level per frame, beats in red, phrases in green", (40, 40, 40), w - 20)
    return cv.png()


def xsheet(levels: list[float], hits: list[int], spans: list[list]) -> str:
    words_at = {p[0]: (p[2] if len(p) > 2 else "") for p in spans}
    inside = {f for p in spans for f in range(p[0], p[1] + 1)}
    lines = ["# Sound X-sheet", "", "Written by kei sound: one row per frame of the shot. Time key poses against the "
             "beats (B) and the phrases.", "", "| Frame | Level | Beat | Phrase |", "|---|---|---|---|"]
    for f, v in enumerate(levels):
        bar = "#" * round(v * 10)
        phrase = words_at.get(f, "") or ("..." if f in inside else "")
        lines.append(f"| {f} | {bar or '.'} | {'B' if f in hits else ''} | {phrase.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def add_sound(shot: Path, path: Path, fps: float, frames: int | None = None, offset: int = 0,
              words: list[str] = ()) -> dict:
    shot, path = Path(shot), Path(path)
    if not path.is_file():
        raise SoundError(f"no sound file {path}")
    if not (fps and fps > 0):
        raise SoundError("the shot needs a frame rate to time sound against")
    if offset < 0:
        raise SoundError("--offset is the sound frame that plays on frame 0: 0 or more")
    d = shot / SOUND_DIR
    d.mkdir(parents=True, exist_ok=True)
    wav = _to_wav(path, d / (path.stem + ".wav"))
    levels = read_levels(wav, fps)[offset:]
    if frames:
        levels = (levels + [0.0] * frames)[:frames + 1]
    hits = beats(levels)
    spans = phrases(levels)
    for i, w in enumerate(words):
        if i < len(spans) and w.strip():
            spans[i].append(w.strip())
    data = {"file": f"{SOUND_DIR}/{wav.name}", "source": path.name, "fps": fps, "offset": offset,
            "frames": len(levels), "level": levels, "beats": hits, "phrases": spans}
    (d / "sound.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    (d / "waveform.png").write_bytes(waveform_png(levels, hits, spans))
    (d / "XSHEET.md").write_text(xsheet(levels, hits, spans), encoding="utf-8", newline="\n")
    return data


def load(shot: Path) -> dict | None:
    try:
        data = json.loads((Path(shot) / SOUND_DIR / "sound.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def snap(shot: dict, hits: list[int], within: int, frames: tuple[int, int] | None = None) -> tuple[dict, int]:
    """Each key moved to the nearest beat at most within frames away; returns the new keys' shot and how many moved."""
    import copy
    out = copy.deepcopy(shot)
    keys = sorted(out["keys"], key=lambda k: k["f"])
    taken = {k["f"] for k in keys}
    moved = 0
    last = out["frames"]
    start = [k["f"] for k in keys]
    owner = {b: min(range(len(keys)), key=lambda i: (abs(start[i] - b), i)) for b in hits}   # each beat's nearest key
    for i, k in enumerate(keys):
        f = k["f"]
        if frames and not (frames[0] <= f <= frames[1]):
            continue
        if out.get("loop") and f >= last:
            continue
        lo = keys[i - 1]["f"] if i else -1
        hi = keys[i + 1]["f"] if i + 1 < len(keys) else last + 1
        near = [b for b in hits if owner[b] == i and abs(b - f) <= within and lo < b < hi and b not in taken
                and 0 <= b <= last]
        if not near:
            continue
        b = min(near, key=lambda x: (abs(x - f), x))
        if b == f:
            continue
        taken.discard(f)
        taken.add(b)
        k["f"] = b
        moved += 1
    out["keys"] = keys
    return out, moved
