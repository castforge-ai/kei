"""Task 4 of plan 6: find Maya, run a job, read a rig. The Maya half runs tests/maya/check_read.py in mayapy."""
import sys
from pathlib import Path

import pytest

from kei.apps import maya as km_app
from kei.apps.maya import MayaError, find_mayapy, run_job
from kei.apps.maya_side import kei_math as km
from kei.characters import load_character, rest_skeleton
from kei.rig import ALL_BONES

import mayakit


def test_kei_mayapy_wins_and_a_missing_file_is_named(monkeypatch, tmp_path):
    monkeypatch.setenv("KEI_MAYAPY", str(tmp_path / "nope" / "mayapy.exe"))
    with pytest.raises(MayaError, match="nope"):
        find_mayapy({"mayapy": "elsewhere"})


def test_the_config_path_comes_next(monkeypatch, tmp_path):
    monkeypatch.delenv("KEI_MAYAPY", raising=False)
    py = tmp_path / "Maya2031" / "bin" / "mayapy.exe"
    py.parent.mkdir(parents=True)
    py.write_text("")
    assert find_mayapy({"mayapy": str(py)}) == (py, "2031")


def test_the_newest_install_is_found_and_none_is_a_plain_message(monkeypatch, tmp_path):
    monkeypatch.delenv("KEI_MAYAPY", raising=False)
    found = []
    for year in ("2025", "2027"):
        p = tmp_path / f"Maya{year}" / "bin" / "mayapy.exe"
        p.parent.mkdir(parents=True)
        p.write_text("")
        found.append(p)
    monkeypatch.setattr(km_app, "_installs", lambda: found)
    assert find_mayapy() == (found[1], "2027")
    monkeypatch.setattr(km_app, "_installs", lambda: [])
    with pytest.raises(MayaError, match="Maya was not found"):
        find_mayapy()


def test_a_job_that_hangs_stops_with_a_maya_error_not_a_hang(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_MAYA_APP_DIR", str(tmp_path / "app"))
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(30)\n")
    with pytest.raises(MayaError, match="did not finish"):
        run_job(Path(sys.executable), {"calls": []}, timeout=1, script=sleeper)


def test_a_job_that_dies_without_a_result_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_MAYA_APP_DIR", str(tmp_path / "app"))
    dies = tmp_path / "dies.py"
    dies.write_text("import sys\nprint('licence refused', file=sys.stderr)\nsys.exit(3)\n")
    with pytest.raises(MayaError, match="licence refused"):
        run_job(Path(sys.executable), {"calls": []}, timeout=30, script=dies)


def test_every_maya_process_kei_starts_has_crash_reports_and_messages_off(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_MAYA_APP_DIR", str(tmp_path / "app"))
    spy = tmp_path / "spy.py"
    spy.write_text("import json, os, sys\nkeys = ['MAYA_DISABLE_CER', 'MAYA_DISABLE_CIP', 'MAYA_DISABLE_CLIC_IPM', "
                   "'MAYA_APP_DIR']\njson.dump({'ok': True, 'env': {k: os.environ.get(k) for k in keys}}, "
                   "open(sys.argv[2], 'w'))\n")
    env = run_job(Path(sys.executable), {}, timeout=30, script=spy)["env"]
    assert env["MAYA_DISABLE_CER"] == "1" and env["MAYA_DISABLE_CIP"] == "1" and env["MAYA_DISABLE_CLIC_IPM"] == "1"
    assert env["MAYA_APP_DIR"] == str(tmp_path / "app")


def test_a_maya_fatal_error_is_a_failed_job_even_with_a_result(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_MAYA_APP_DIR", str(tmp_path / "app"))
    crash = tmp_path / "crash.py"
    crash.write_text("import json, sys\njson.dump({'ok': True}, open(sys.argv[2], 'w'))\n"
                     "print('Fatal Error. Attempting to save in C:/x.ma')\n")
    with pytest.raises(MayaError, match="crashed"):
        run_job(Path(sys.executable), {}, timeout=30, script=crash)


@pytest.mark.maya
def test_a_maya_job_leaves_no_crash_dump(tmp_path):
    import os
    import tempfile
    temp = Path(os.environ.get("TEMP") or tempfile.gettempdir())
    before = set(temp.glob("MayaCrashLog*"))
    run_job(mayakit.mayapy(), {"calls": [{"tool": "scene_info"}]}, timeout=300)
    assert set(temp.glob("MayaCrashLog*")) == before


# ---------------- in Maya ----------------
@pytest.fixture(scope="module")
def read():
    return mayakit.run_script("check_read.py")


@pytest.mark.maya
def test_read_rig_finds_the_joints_controls_and_units(read):
    r = read["kei_rig"]
    assert r["units"] == "cm" and r["up"] == "y"
    assert {j["name"].split(":")[-1] for j in r["joints"]} >= set(ALL_BONES)
    roles = {c["role"] for c in r["controls"]}
    assert {"body", "fk", "foot_ik", "leg_pv"} <= roles
    foot = next(c for c in r["controls"] if c["name"].endswith("l_foot_ik_ctl"))
    assert "roll" in foot["keyable"] and "scaleX" not in foot["keyable"]
    assert "kei:foot_l" in foot["moves"]


@pytest.mark.maya
def test_read_rig_on_a_bare_skeleton_links_each_joint_to_itself_and_reports_limits(read):
    r = read["test_rig"]
    head = next(c for c in r["controls"] if c["name"].endswith(":head"))
    assert head["limits"]["rotateX"] == [-30.0, 30.0]
    hand = next(c for c in r["controls"] if c["name"].endswith(":hand_r"))
    assert "rotateX" not in hand["keyable"]


@pytest.mark.maya
def test_a_namespaced_twin_keys_the_right_rig(read):
    r = read["twins"]
    assert abs(r["kei2_foot_ty"] - 12.0) < 1e-6 and abs(r["kei_foot_ty"]) < 1e-6


@pytest.mark.maya
def test_a_short_name_used_twice_is_refused_and_the_full_path_is_keyed(read):
    r = read["duplicates"]
    assert "more than one node named 'dup'" in r["short_error"]
    assert r["full_path_keys"] == 1


@pytest.mark.maya
def test_a_locked_channel_is_refused_by_name_and_a_limit_clip_is_reported(read):
    assert "hand_r.rotateX is locked" in read["locked_error"]
    clip = read["clipped"]
    assert clip and clip[0]["asked"] == 45.0 and clip[0]["reached"] == 30.0


@pytest.mark.maya
def test_a_centimetre_z_up_scene_reads_back_in_metres_y_up(read):
    rest = rest_skeleton(load_character("kei"))
    got = read["z_up"]["frames"][0]["pos"]
    for n in ALL_BONES:
        want = km.mirror_point(rest[n].head)
        assert max(abs(a - b) for a, b in zip(got[f"kei:{n}"], want)) < 0.001, n
