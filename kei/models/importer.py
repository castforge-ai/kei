"""kei import: an outside model becomes a character Kei animates.

An unrigged humanoid: stood up and scaled to the height (kei.models.fit.normalise), refused when it is not a
two-legged figure, fitted (landmarks, then fit_rig) and bound by piece (kei.models.bind.bind_mesh).

A rigged humanoid: its bone names map to Kei's (map_bones, plus the person's --map pairs); its mapped joints are the
fit's marks (the toes, heels and arm ends come from the mesh), so Kei's rig is set up on the model's own skeleton, and
the model's own weights are carried over (bind_rigged; a mesh with no skin, a hat or a
weapon, follows the joint it hangs from). Its height is its own unless --height says otherwise. Without
the bones Kei needs (CORE), the import stops and names them, so the person can map them or import it as unrigged.

Either way the character is written unconfirmed (kei.characters.imported) with fit.png, its fit sheet, and a shot on
it asks the person to look at that sheet first.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from kei.characters import CharacterError, characters_dir, imported_characters, load_imported, raw
from kei.characters.imported import check_name, write_character
from kei.models.bind import bind_mesh, bind_rigged, map_bones
from kei.models.fit import STACK_RANGE, Sections, fit_rig, humanoid_or_raise, landmarks, normalise, stack_head
from kei.models.model import Model, ModelError, read_model, remove_temp_files
from kei.rig import ALL_BONES, skeleton

CORE = ("pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r",
        "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "head")


def _rigged_marks(model: Model, mapping: dict, S: Sections, H: float) -> dict:
    kei = {k: j.head for j in model.joints for n, k in mapping.items() if n == j.name}
    missing = [b for b in CORE if b not in kei]
    if missing:
        raise ModelError(f"{model.source}: Kei could not find these bones in the model's skeleton: "
                         f"{', '.join(missing)}. Map them with --map <model bone>=<kei bone>, or import the model "
                         "as unrigged with --unrigged")
    lefts = [kei[n][0] for n in CORE if n.endswith("_l")]
    if sum(lefts) / len(lefts) >= 0:          # Kei's world: the character's left is -x
        raise ModelError(f"{model.source}: the model's left bones sit on its right side (the file is mirrored, or "
                         "its bones are named for the other side); fix the names or the file's axes, or import it "
                         "with --unrigged")
    marks = {n: kei[n] for n in ("thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "upperarm_l",
                                 "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "head")}
    neck = kei.get("neck_01") or kei.get("neck_02")
    marks["neck_01"] = neck or tuple(kei["head"][k] + (kei.get("spine_05", kei["pelvis"])[k] - kei["head"][k]) * 0.4
                                     for k in range(3))
    for side, s in (("l", -1), ("r", 1)):
        ankle = marks[f"foot_{side}"]
        sole = S.runs(0.01 * H, 0.008 * H, s)
        marks[f"toe_{side}"] = (ankle[0], 0.0, max((r[3] for r in sole), default=ankle[2] + 0.12 * H))
        marks[f"heel_{side}"] = (ankle[0], 0.0, min((r[2] for r in sole), default=ankle[2] - 0.035 * H))
        tip = kei.get(f"middle_03_{side}")
        hand, elbow = marks[f"hand_{side}"], marks[f"lowerarm_{side}"]
        marks[f"hand_{side}_end"] = tip or tuple(hand[k] + (hand[k] - elbow[k]) * 0.7 for k in range(3))
    return marks


MAX_TEXTURE = 2048        # pixels: the longer side of a texture Kei keeps
# The texture is untrusted: ffmpeg reads it as one local image of the type its extension names, never as a playlist,
# a concat list or a URL that would make it open other files or the network.
IMAGE_DEMUXER = {".png": ["png_pipe"], ".jpg": ["jpeg_pipe"], ".jpeg": ["jpeg_pipe"], ".bmp": ["bmp_pipe"],
                 ".webp": ["webp_pipe"], ".tif": ["tiff_pipe"], ".tiff": ["tiff_pipe"], ".dds": ["dds_pipe"],
                 ".psd": ["psd_pipe"], ".tga": ["image2", "-pattern_type", "none"]}


def _image_input(src) -> list[str]:
    """ffmpeg's input options for the texture src: the file protocol only, and the image demuxer of its type."""
    demuxer = IMAGE_DEMUXER.get(Path(src).suffix.lower())
    if demuxer is None:
        raise ModelError(f"{src}: Kei reads textures of these types only: "
                         f"{', '.join(sorted(IMAGE_DEMUXER))}; save the texture as PNG and import again")
    return ["-protocol_whitelist", "file", "-f", *demuxer, "-i", str(src)]


def convert_texture(src, folder, file: str = "texture.rgb") -> dict:
    """A base colour image converted once, with ffmpeg, to raw 8-bit RGB rows (file, texture.rgb for the first) in
    the character's folder, its longer side at most MAX_TEXTURE pixels. Returns {"file", "width", "height"}."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ModelError("the model has a texture, and Kei converts textures with ffmpeg, which is not installed; "
                         "install ffmpeg (it also makes Kei's videos) and import again")
    source = _image_input(src)
    probe = subprocess.run(["ffprobe", "-v", "error", *source, "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "json"], capture_output=True, text=True)
    try:
        st = json.loads(probe.stdout)["streams"][0]
        w, h = int(st["width"]), int(st["height"])
        if w <= 0 or h <= 0:
            raise ValueError(f"an image of {w} x {h} pixels")
    except (ValueError, KeyError, IndexError) as e:
        raise ModelError(f"{src}: ffmpeg cannot read the texture ({probe.stderr.strip()[:200] or e})") from e
    k = min(1.0, MAX_TEXTURE / max(w, h))
    w, h = max(1, round(w * k)), max(1, round(h * k))
    out = Path(folder) / file
    Path(folder).mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *source, "-vf", f"scale={w}:{h}:flags=lanczos",
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", str(out)], capture_output=True,
                       text=True)
    if r.returncode != 0 or not out.is_file() or out.stat().st_size != w * h * 3:
        raise ModelError(f"{src}: ffmpeg could not convert the texture ({r.stderr.strip()[:200]})")
    return {"file": file, "width": w, "height": h}


def import_model(path, name: str, height: float | None = None, maps: dict | None = None,
                 unrigged: bool = False) -> tuple[Path, dict]:
    """Import the model at path as the character name. Returns (the character's folder, the fit report).
    Raises ModelError or CharacterError, naming what to do."""
    check_name(name)
    if height is None:
        height = _same_model_height(path, name)       # a new import of the same model keeps its height
    model = read_model(path)
    try:
        return _import(model, path, name, height, maps, unrigged)
    finally:
        remove_temp_files(model)          # the model's embedded images, converted or not


def _same_model_height(path, name: str) -> float | None:
    """The height of the character name's last import when it was imported from the same model file, else None: a
    different model under the same name is measured again (or asks for --height), never given the old height."""
    if name not in imported_characters():
        return None
    try:
        data = raw(name)
        old = (data.get("source") or {}).get("file")
        if old and Path(old).resolve() == Path(path).resolve():
            return float(data["height"])
    except (CharacterError, KeyError, TypeError, ValueError, OSError):
        pass
    return None


def _publish(stage: Path, folder: Path) -> None:
    """The staged import's files renamed into the character's folder, character.json last; then the old import's
    texture files the new one does not name are removed."""
    files = sorted(stage.iterdir(), key=lambda p: p.name == "character.json")
    for f in files:
        os.replace(f, folder / f.name)
    keep = {f.name for f in files}
    for old in folder.glob("texture*.rgb"):
        if old.name not in keep:
            old.unlink()


def _import(model: Model, path, name: str, height, maps, unrigged: bool) -> tuple[Path, dict]:
    rigged = model.rigged and not unrigged
    if rigged:
        mapping, unmapped = map_bones([j.name for j in model.joints])
        for theirs, ours in (maps or {}).items():
            if ours not in ALL_BONES:
                raise ModelError(f"--map {theirs}={ours}: {ours!r} is not one of Kei's bones")
            mapping = {k: v for k, v in mapping.items() if v != ours}
            mapping[theirs] = ours
        if height is None:
            ys = [v[1] for v in model.all_verts()]
            height = max(ys) - min(ys)
        model = normalise(model, height)
    else:
        if height is None:
            raise ModelError(f"{path}: the model has no skeleton, so Kei cannot tell its size; give its height in "
                             "metres with --height (for example --height 1.71)")
        model = normalise(model, height)
    if not 1.0 < height < 2.5:
        raise ModelError(f"--height {height}: Kei animates characters from 1 to 2.5 m tall")
    S = Sections(model)
    humanoid_or_raise(model, S)
    if rigged:
        marks = _rigged_marks(model, mapping, S, height)
        marks["_snapped"] = []
    else:
        marks = landmarks(model)
    proportions, rest, report = fit_rig(marks, height)
    rest["neck"] = [stack_head(model, proportions, rest, height), 0, 0]
    report["rest_spine"], report["rest_neck"] = rest["spine"][0], rest["neck"][0]
    bones = skeleton(rest, proportions)
    if rigged:
        parts = bind_rigged(model, mapping, bones=bones, height=height)
        report["skeleton"] = "the model's own"
        report["unmapped"] = unmapped
    else:
        parts = [p for m in model.meshes for p in bind_mesh(m, bones, height)]
        report["skeleton"] = "fitted to the mesh"
    report["warnings"] = list(model.warnings)
    if rest["neck"][0] in STACK_RANGE:
        report["warnings"].append(
            f"the fit could not stack the head over the shoulders: the neck's rest pitch stopped at its limit "
            f"({rest['neck'][0]} rad), so a shot may play the head too far {'forward' if rest['neck'][0] > 0 else 'back'}"
            "; look at the neutral stance panel of fit.png before you approve the fit")
    report["parts"] = {"rigid": sum(1 for p in parts if p.skin is None), "smooth": sum(1 for p in parts if p.skin)}
    from kei.models.bind import finger_weights
    report["fingers"] = finger_weights(parts)          # the skin each finger bone moves
    bare = sorted(n for n, w in report["fingers"].items() if w == 0)
    if bare:
        report["warnings"].append(
            f"{len(bare)} finger bone(s) move no skin: {', '.join(bare)}. Those fingers stay rigid in every shot; "
            "look at the hands on fit.png before you approve the fit")
    source = {"file": str(path), "skeleton": report["skeleton"], "height": round(height, 4)}
    sources = []                     # one texture per base colour image, in the order the parts name them
    for p in parts:
        if p.uvs and p.texture and p.texture not in sources:
            sources.append(p.texture)
    # Every new file is written to a staging folder inside the character's folder and renamed into place only when
    # all of them are written and the fit sheet is drawn: a failure leaves the old import whole.
    folder = characters_dir() / name
    new = not folder.exists()
    stage = folder / f".import-{uuid.uuid4().hex[:12]}"
    stage.mkdir(parents=True)
    done = False
    try:
        _write(stage, model, path, name, height, proportions, rest, parts, source, report, sources)
        _publish(stage, folder)
        done = True
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if new and not done:
            shutil.rmtree(folder, ignore_errors=True)
    return folder, report


def _write(stage: Path, model: Model, path, name: str, height: float, proportions, rest, parts, source: dict,
           report: dict, sources: list) -> None:
    """The import's files in the staging folder: the textures, character.json, mesh.json and fit.png."""
    textures = [convert_texture(s, stage, "texture.rgb" if i == 0 else f"texture_{i}.rgb")
                for i, s in enumerate(sources)]
    index = {s: i for i, s in enumerate(sources)}
    parts = [dataclasses.replace(p, uvs=p.uvs if p.texture in index else None, texture=index.get(p.texture))
             for p in parts]
    texture = (textures[0] if len(textures) == 1 else textures) if textures else None
    if sources:
        named = [s if s not in model.temp_files else f"an image embedded in {Path(path).name}" for s in sources]
        source["texture"] = named[0] if len(named) == 1 else named
    write_character(characters_dir(), name, name.replace("_", " ").title(), height, proportions, rest, parts, source,
                    report, texture=texture, folder=stage)
    from kei.render import draw_fit_sheet
    (stage / "fit.png").write_bytes(draw_fit_sheet(load_imported(stage, name)))


def joint_errors_text(report: dict) -> str:
    """The fit's joint errors, worst first, in centimetres."""
    errs = sorted(report.get("errors", {}).items(), key=lambda kv: -kv[1])
    return ", ".join(f"{n} {e * 100:.1f} cm" for n, e in errs[:4]) + (f" (largest {report['largest'] * 100:.1f} cm)"
                                                                      if "largest" in report else "")

