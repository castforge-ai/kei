"""Review findings on plan 6 (I2, I6, I7, set_time, the job result, the rig choice). The Maya half runs
tests/maya/check_review.py in mayapy."""
import math
import sys
from pathlib import Path

import pytest

from kei.apps.maya import MayaError, run_job
from kei.apps.maya_stage import pick_rig

import mayakit


def test_a_malformed_result_is_a_maya_error(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_MAYA_APP_DIR", str(tmp_path / "app"))
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nopen(sys.argv[2], 'w').write('{not json')\n")
    with pytest.raises(MayaError, match="result"):
        run_job(Path(sys.executable), {}, timeout=30, script=bad)


def test_one_kei_rig_is_taken_and_several_resolve_by_character_or_ask():
    one = [{"namespace": "hero", "character": "keira"}]
    assert pick_rig(one, "kei") == one[0]
    two = [{"namespace": "a", "character": "kei"}, {"namespace": "b", "character": "keira"}]
    assert pick_rig(two, "keira") == two[1]
    with pytest.raises(ValueError, match="a .*kei.*b .*keira"):
        pick_rig(two + [{"namespace": "c", "character": "keira"}], "keira")
    with pytest.raises(ValueError, match="no Kei rig"):
        pick_rig([], "kei")


@pytest.fixture(scope="module")
def review(tmp_path_factory):
    d = tmp_path_factory.mktemp("review")
    return mayakit.run_script("check_review.py", dir=str(d))


@pytest.mark.maya
def test_a_hostile_fbx_path_is_refused_and_runs_nothing(review):
    assert review["hostile"].startswith("ToolError") and not review["injected"]


@pytest.mark.maya
def test_a_path_with_a_semicolon_still_exports(review):
    assert review["semicolon_fbx"]


@pytest.mark.maya
def test_the_temp_copy_never_writes_the_open_scene_a_reference_or_a_binary(review):
    assert review["over_scene"].startswith("ToolError") and "open scene" in review["over_scene"]
    assert review["over_ref"].startswith("ToolError") and "reference" in review["over_ref"]
    assert review["not_ma"].startswith("ToolError") and ".ma" in review["not_ma"]
    assert review["user_untouched"]


@pytest.mark.maya
def test_a_scene_in_radians_is_keyed_and_read_in_degrees_and_stays_in_radians(review):
    assert abs(review["radians_value"] - math.pi / 2) < 1e-6
    assert review["angle_unit_after"] == "rad"
    assert review["radians_limit"] == [-30.0, 30.0]


@pytest.mark.maya
def test_a_frame_rate_change_does_not_move_the_scene_s_keys(review):
    assert review["key_times"] == [12.0]


@pytest.mark.maya
def test_the_host_kills_its_script_jobs_when_it_stops(review):
    """Four jobs (three scene events and quit); stop() kills the ones Maya gave an id (batch Maya gives none)."""
    assert review["jobs"] == 4 and review["jobs_left"] == []

