"""Task 3 of plan 7: Kei sends only its own editor scripts, checked by SHA-256. No Unreal Editor."""
import ast
import json
import sys
from pathlib import Path

import pytest

from fakes.fake_claireon import FakeClaireon
from kei.apps import unreal as u
from kei.apps.unreal import Claireon, UnrealError, run_script
from kei.apps.unreal_side import file_hash, script_files
from kei.apps.unreal_side.hashes import UNREAL_SIDE_HASHES

ROOT = Path(__file__).resolve().parents[1]


def connected(fake):
    c = Claireon(fake.url)
    c.initialize()
    return c


def test_the_hash_table_matches_the_files():
    on_disk = {p.name: file_hash(p) for p in script_files()}
    assert on_disk == UNREAL_SIDE_HASHES, "a script changed and the table was not updated: " \
                                          "run python tools/update_unreal_hashes.py"


def test_every_script_is_valid_python_and_names_itself():
    for p in script_files():
        text = p.read_text(encoding="utf-8")
        ast.parse(text)
        assert text.startswith(f"# kei_script: {p.stem}\n"), p.name
        assert "kei_run(_main)" in text or p.name == "kei_ue.py", p.name


def test_the_hash_is_the_same_for_crlf_and_lf(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_bytes(b"x = 1\ny = 2\n")
    b.write_bytes(b"x = 1\r\ny = 2\r\n")
    assert file_hash(a) == file_hash(b)


def test_a_hash_mismatch_is_refused_before_any_request(monkeypatch):      # Review Focus 4
    with FakeClaireon() as fake:
        c = connected(fake)
        n = len(fake.requests)
        monkeypatch.setitem(UNREAL_SIDE_HASHES, "ping.py", "0" * 64)
        with pytest.raises(UnrealError, match="hash"):
            run_script(c, "ping.py", {})
        assert len(fake.requests) == n


@pytest.mark.parametrize("name", ["../tests/test_unreal_side_hashes.py", "nothing.py", "ping", "sub/ping.py",
                                  "..\\ping.py", "", "hashes.py"])
def test_a_name_outside_the_folder_or_the_table_is_refused_before_any_request(name):
    with FakeClaireon() as fake:
        c = connected(fake)
        n = len(fake.requests)
        with pytest.raises(UnrealError, match="not one of Kei's editor scripts"):
            run_script(c, name, {})
        assert len(fake.requests) == n


def test_inputs_with_quotes_and_newlines_reach_the_script_intact():
    nasty = {"say": 'he said "hi"\nand \'left\'', "back\\slash": "C:\\a\\b", "n": [1, 2.5, None, True],
             "uni": "caf\u00e9"}
    with FakeClaireon({"ping": lambda inp: {"ok": True, "echo": inp}}) as fake:
        out = run_script(connected(fake), "ping.py", nasty)
        assert fake.inputs[-1] == nasty and out["echo"] == nasty


def test_the_code_sent_is_the_helpers_then_the_script_and_nothing_else():
    with FakeClaireon({"ping": lambda inp: {"ok": True}}) as fake:
        run_script(connected(fake), "ping.py", {"a": 1})
        code = fake.codes[-1]
        helpers = (ROOT / "kei/apps/unreal_side/kei_ue.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        script = (ROOT / "kei/apps/unreal_side/ping.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        folder = str(Path(connected(fake).results_dir))
        assert code == (f"import json\nKEI_INPUT = json.loads('{json.dumps({'a': 1})}')\n"
                        f"KEI_RESULTS_DIR = {folder!r}\n{helpers}\n{script}")


def test_a_script_that_printed_no_result_line_is_an_error_with_the_traceback():
    with FakeClaireon() as fake:
        fake.plain = "Traceback (most recent call last):\n  File x\nNameError: name 'q' is not defined"
        with pytest.raises(UnrealError, match="NameError"):
            run_script(connected(fake), "ping.py", {})


def test_an_error_result_line_carries_the_traceback():
    with FakeClaireon({"ping": lambda inp: {"error": "Traceback...\nValueError: boom"}}) as fake:
        with pytest.raises(UnrealError, match="ValueError: boom"):
            run_script(connected(fake), "ping.py", {})


def test_the_last_result_line_wins_and_crlf_logs_parse():
    with FakeClaireon() as fake:
        fake.plain = 'noise\nKEI_RESULT {"a": 1}\nmore noise\nKEI_RESULT {"a": 2}'
        assert run_script(connected(fake), "ping.py", {}) == {"a": 2}


def test_server_url_reads_the_port_claireon_wrote(tmp_path):
    f = tmp_path / "Saved" / "Claireon" / "MCPServer.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"port": 51234, "pid": 9, "publicPort": 51234, "mode": "direct"}))
    assert u.server_url(tmp_path) == "http://127.0.0.1:51234/mcp"
    assert u.server_url(tmp_path / "none") is None
    f.write_text("{bad")
    assert u.server_url(tmp_path) is None


def test_a_large_result_comes_through_a_token_in_keis_own_folder_and_the_file_is_removed(tmp_path):
    token = "ab" * 16
    f = tmp_path / (token + ".json")
    f.write_text(json.dumps({"big": list(range(5000))}))
    with FakeClaireon() as fake:
        fake.plain = "KEI_RESULT " + json.dumps({"result_token": token})
        client = connected(fake)
        client.results_dir = tmp_path
        out = run_script(client, "ping.py", {})
    assert out == {"big": list(range(5000))} and not f.exists()


@pytest.mark.parametrize("token", ["../" + "a" * 32, "C:/x/" + "a" * 32, "AB" * 16, "a" * 31, "a" * 33,
                                   "//host/share/" + "a" * 32, 12345, None])
def test_a_token_that_is_not_32_hex_is_refused_before_any_file_access(tmp_path, token):
    with FakeClaireon() as fake:
        fake.plain = "KEI_RESULT " + json.dumps({"result_token": token})
        client = connected(fake)
        client.results_dir = tmp_path
        with pytest.raises(UnrealError, match="does not accept"):
            run_script(client, "ping.py", {})


def test_the_old_path_form_is_not_followed(tmp_path):
    f = tmp_path / "Saved" / "Kei" / "results" / ("a" * 32 + ".json")
    f.parent.mkdir(parents=True)
    f.write_text("{}")
    with FakeClaireon() as fake:
        fake.plain = "KEI_RESULT " + json.dumps({"result_file": f.as_posix()})
        out = run_script(connected(fake), "ping.py", {})
    assert out == {"result_file": f.as_posix()} and f.exists()


def test_a_missing_result_file_is_refused(tmp_path):
    with FakeClaireon() as fake:
        fake.plain = "KEI_RESULT " + json.dumps({"result_token": "c" * 32})
        client = connected(fake)
        client.results_dir = tmp_path
        with pytest.raises(UnrealError, match="no result file"):
            run_script(client, "ping.py", {})


def test_a_result_file_over_the_size_cap_is_refused_and_removed(tmp_path, monkeypatch):
    token = "d" * 32
    f = tmp_path / (token + ".json")
    f.write_text(json.dumps({"x": "y" * 100}))
    monkeypatch.setattr(u, "RESULT_FILE_MAX", 10)
    with FakeClaireon() as fake:
        fake.plain = "KEI_RESULT " + json.dumps({"result_token": token})
        client = connected(fake)
        client.results_dir = tmp_path
        with pytest.raises(UnrealError, match="larger"):
            run_script(client, "ping.py", {})
    assert not f.exists()


def test_kei_places_its_character_on_the_level_floor_never_moving_the_level():
    text = (ROOT / "kei/apps/unreal_side/make_sequence.py").read_text(encoding="utf-8")
    assert "PlayerStart" in text and "line_trace_single" in text      # found live: the origin was inside a platform
    assert "get_object_template().skeletal_mesh_component" in text    # only the spawnable's own template moves
    assert "set_actor_location" not in text and "save_current_level" not in text


def test_the_rest_pose_is_the_rigs_initial_pose_not_the_frame_the_editor_shows():
    # Found live: rest read before any control was set is whatever frame Sequencer shows, so the toe lift of a pass
    # was measured against its own frame 0. The rest pose sets every control to its initial value first.
    text = (ROOT / "kei/apps/unreal_side/eval_rig.py").read_text(encoding="utf-8")
    i_rest = text.index("rest = read()")
    assert "h.get_local_transform(k, True)" in text[:i_rest]
