"""JSON Schemas for Kei's files, made from the code's own constants so they cannot drift from what Kei reads.

SCHEMAS: name -> function returning the schema (JSON Schema 2020-12). kei schema prints one, kei schema --write
writes all of them to docs/schemas/<name>.schema.json, and a test fails when the written files differ from these.
validate(value, schema) -> [problems]: a small checker for the parts of JSON Schema these files use (type, enum,
const, required, properties, additionalProperties, items, minItems, maxItems, minimum, exclusiveMinimum, oneOf,
patternProperties). The real checks stay in the code (kei check, the gates): a schema says the shape, not the craft.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from kei.objects import HOLDERS, LET_GO, SHAPES, TURNS
from kei.render import CAMERA_KEY_FIELDS, CAMERA_KEYS
from kei.rig import CHANNELS, LENGTH_SCALES, STAND
from kei.sample import KEY_FIELDS

DIALECT = "https://json-schema.org/draft/2020-12/schema"
BASE = "https://github.com/castforge-ai/kei/blob/main/docs/schemas/"
NUM = {"type": "number"}


def _channel(name: str) -> dict:
    v = STAND[name]
    if isinstance(v, list):
        return {"type": "array", "items": NUM, "minItems": 1, "maxItems": len(v),
                "description": f"1 to {len(v)} numbers (the rest carry over); the default stand is {v}"}
    if name in LENGTH_SCALES:
        return {**NUM, "exclusiveMinimum": 0, "description": f"a length scale; the default stand is {v}"}
    return {**NUM, "description": f"the default stand is {v}"}


def _key() -> dict:
    props = {c: _channel(c) for c in CHANNELS}
    props.update({
        "f": {**NUM, "description": "the frame of the key"},
        "name": {"type": "string"}, "note": {"type": "string"},
        "tangent": {"enum": ["auto", "flat"], "description": "auto (default) or flat"},
        "function": {"type": "string", "description": "the pose function: contact, down, up, passing..."},
        "kind": {"type": "string", "description": "key, extreme or breakdown"},
    })
    assert set(KEY_FIELDS) <= set(props)
    return {"type": "object", "required": ["f"], "properties": props, "additionalProperties": False}


def _object() -> dict:
    holder = {"enum": [*HOLDERS, *LET_GO]}
    vec3 = {"type": "array", "items": NUM, "minItems": 3, "maxItems": 3}
    return {"type": "object", "required": ["name", "shape", "size", "rest"], "properties": {
        "name": {"type": "string"},
        "shape": {"enum": list(SHAPES)},
        "size": {"type": "array", "items": NUM, "minItems": 1, "maxItems": 3,
                 "description": "box: width, height, depth; cylinder: diameter, height; sphere: diameter. Metres."},
        "rest": {**vec3, "description": "the centre on frame 0"},
        "mass_kg": {**NUM, "minimum": 0},
        "colour": {"type": "string"},
        "yaw_deg": NUM,
        "turn": {"enum": list(TURNS)},
        "attach": {"type": "array", "items": {"type": "object", "required": ["f", "to"],
                                              "properties": {"f": NUM, "to": holder}}},
        "path": {"type": "array", "description": "the object's own keys: {f, pos [x, y, z], yaw_deg}",
                 "items": {"type": "object", "required": ["f"]}},
        "grip": {"type": "object", "description": "each hand's point on the object, in its own space",
                 "patternProperties": {"^[lr]$": vec3}, "additionalProperties": False},
    }}


def shot() -> dict:
    return {"$schema": DIALECT, "$id": BASE + "shot.schema.json", "title": "Kei shot (out_<pass>/shot.json)",
            "description": "A keyed shot on Kei's rig v4. A key may leave out any channel: it carries over from the "
                           "key before. Kei refuses a shot it cannot play with a message (kei check).",
            "type": "object", "required": ["rig", "frames", "keys"], "properties": {
                "rig": {"const": "v4"},
                "fps": {**NUM, "exclusiveMinimum": 0},
                "frames": {"type": "integer", "minimum": 1},
                "loop": {"type": "boolean"},
                "in_place": {"type": "boolean"},
                "tangents": {"enum": ["clamped", "free"]},
                "character": {"type": "string"},
                "props": {"type": "object", "description": "the character's proportions"},
                "note": {"type": "string"},
                "keys": {"type": "array", "minItems": 1, "items": _key()},
                "objects": {"type": "array", "items": _object()},
                "performers": {"type": "array", "description": "Unreal shots only: other characters in the level"},
            }}


def plan() -> dict:
    cam = {k: NUM for k in CAMERA_KEYS}
    cam["follow"] = {"type": "boolean"}
    cam["target_m"] = {"type": "array", "items": NUM, "minItems": 3, "maxItems": 3}
    cam["name"] = {"type": "string"}
    key = {k: NUM for k in CAMERA_KEY_FIELDS}
    key.update({"f": {"type": "integer", "minimum": 0}, "cut": {"type": "boolean"},
                "target_m": cam["target_m"], "sensor_mm": {"type": "array", "items": NUM, "minItems": 2, "maxItems": 2}})
    cam["keys"] = {"type": "array", "minItems": 1, "description": "an animated camera: each key changes some settings "
                   "from frame f; between keys it eases, and a key with cut true starts a new setup",
                   "items": {"type": "object", "required": ["f"], "properties": key}}
    return {"$schema": DIALECT, "$id": BASE + "plan.schema.json", "title": "Kei plan (plan/plan.json)",
            "description": "The key poses of the plan stage and the locked delivery camera. The P7 gate also needs "
                           "PLAN.md's X-sheet.",
            "type": "object", "required": ["keys"], "properties": {
                "keys": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "required": ["f", "function"], "properties": {
                        "f": {"type": "integer"}, "function": {"type": "string"},
                        "kind": {"type": "string"}, "note": {"type": "string"},
                        "drawing": {"type": "string"}, "views": {"type": "object"}}}},
                "camera": {"type": "object", "properties": cam},
                "fps": {**NUM, "exclusiveMinimum": 0}, "frames": {"type": "integer", "minimum": 1},
                "loop": {"type": "boolean"},
            }}


def bundle() -> dict:
    return {"$schema": DIALECT, "$id": BASE + "bundle.schema.json", "title": "Kei lesson bundle (bundle.json)",
            "description": "One shared lesson: lesson.md, cases/fails/shot.json, cases/passes/shot.json, "
                           "numbers.json and this file, with the sha256 of each other file.",
            "type": "object", "required": ["format", "files"], "properties": {
                "format": {"const": 1}, "kei_version": {"type": "string"}, "stage": {"type": "string"},
                "lesson": {"type": "string"},
                "files": {"type": "object", "required": ["lesson.md", "cases/fails/shot.json",
                                                         "cases/passes/shot.json", "numbers.json"],
                          "patternProperties": {".": {"type": "string"}}},
            }}


def notes() -> dict:
    return {"$schema": DIALECT, "$id": BASE + "notes.schema.json", "title": "Kei reviewer notes (<shot>_notes.json)",
            "description": "Saved from a kei pack page; kei note <shot> --from-file brings it in.",
            "type": "object", "required": ["kei_notes", "shot", "pack", "reviewer", "notes"], "properties": {
                "kei_notes": {"const": 1}, "shot": {"type": "string"}, "pack": {"type": "string"},
                "reviewer": {"type": "string"}, "saved": {"type": "string"},
                "notes": {"type": "array", "minItems": 1, "maxItems": 200, "items": {
                    "type": "object", "required": ["text"],
                    "properties": {"text": {"type": "string"}, "frames": {"type": "string"}}}},
            }}


SCHEMAS = {"shot": shot, "plan": plan, "bundle": bundle, "notes": notes}


def dump(name: str) -> str:
    return json.dumps(SCHEMAS[name](), indent=1, ensure_ascii=False) + "\n"


def write_all(folder: Path) -> list[Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name in SCHEMAS:
        p = folder / f"{name}.schema.json"
        p.write_text(dump(name), encoding="utf-8", newline="\n")
        out.append(p)
    return out


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool}


def _is(value, t: str) -> bool:
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPES[t])


def validate(value, schema: dict, where: str = "$") -> list[str]:
    out: list[str] = []
    if "const" in schema and value != schema["const"]:
        return [f"{where}: must be {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{where}: must be one of {schema['enum']}"]
    t = schema.get("type")
    if t and not _is(value, t):
        return [f"{where}: must be {t}"]
    if _is(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{where}: under {schema['minimum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            out.append(f"{where}: must be over {schema['exclusiveMinimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{where}: needs {schema['minItems']} item(s) or more")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{where}: at most {schema['maxItems']} item(s)")
        if "items" in schema:
            for i, v in enumerate(value):
                out += validate(v, schema["items"], f"{where}[{i}]")
    if isinstance(value, dict):
        for r in schema.get("required", []):
            if r not in value:
                out.append(f"{where}: needs {r!r}")
        props, pats = schema.get("properties", {}), schema.get("patternProperties", {})
        for k, v in value.items():
            if k in props:
                out += validate(v, props[k], f"{where}.{k}")
                continue
            pat = next((s for p, s in pats.items() if re.search(p, k)), None)
            if pat is not None:
                out += validate(v, pat, f"{where}.{k}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{where}: unknown field {k!r}")
    return out
