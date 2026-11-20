"""The schemas come from the code, the written copies match, the real files pass them, and the docs name every stage
and status."""
import json
from pathlib import Path

import pytest

from kei.schemas import SCHEMAS, dump, validate
from kei.stages import STAGES
from kei.state import STATUSES

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


@pytest.mark.parametrize("name", list(SCHEMAS))
def test_the_written_schema_is_the_one_the_code_makes(name):
    written = (DOCS / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert written == dump(name), f"run: kei schema --write docs/schemas ({name} is stale)"


def _shots():
    out = []
    for p in [*ROOT.glob("examples/**/shot.json"), *ROOT.glob("tests/fixtures/**/*.json")]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("rig") == "v4":
            out.append(p)
    return out


def test_every_shipped_shot_passes_the_shot_schema():
    shots = _shots()
    assert shots
    for p in shots:
        assert validate(json.loads(p.read_text(encoding="utf-8")), SCHEMAS["shot"]()) == [], p


def test_the_schema_refuses_what_kei_refuses():
    s = SCHEMAS["shot"]()
    assert validate({"rig": "v3", "frames": 1, "keys": [{"f": 0}]}, s)
    assert validate({"rig": "v4", "frames": 0, "keys": [{"f": 0}]}, s)
    assert validate({"rig": "v4", "frames": 4, "keys": [{"f": 0, "wing": 1}]}, s) == ["$.keys[0]: unknown field 'wing'"]
    assert validate({"rig": "v4", "frames": 4, "keys": [{"f": 0, "sq": 0}]}, s)
    assert validate({"rig": "v4", "frames": 4, "keys": [{"f": 0, "root": [0, 1, 0, 9]}]}, s)
    assert validate({"rig": "v4", "frames": 4, "keys": [{"f": 0, "root": [0.1]}]}, s) == []


def test_a_pack_notes_file_passes_the_notes_schema():
    n = {"kei_notes": 1, "shot": "s", "pack": "p", "reviewer": "Sam", "notes": [{"text": "x", "frames": "1-2"}]}
    assert validate(n, SCHEMAS["notes"]()) == []


def test_the_docs_name_every_stage_and_every_status():
    stages = (DOCS / "stages.md").read_text(encoding="utf-8")
    trouble = (DOCS / "troubleshooting.md").read_text(encoding="utf-8")
    assert all(f"`{s.id}`" in stages for s in STAGES)
    assert all(f"`{s}`" in trouble for s in STATUSES)


def test_the_docs_links_resolve():
    import re
    for page in DOCS.glob("*.md"):
        for target in re.findall(r"\]\(([^)#]+)\)", page.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (page.parent / target).exists(), f"{page.name} links to {target}"
