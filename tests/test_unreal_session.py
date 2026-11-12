"""Task 4 of plan 7: finding open Unreal Editors, the question, and the kept choice. Fake probes, no editor."""
import json

import pytest

from kei.apps.maya_session import Question, Target
from kei.apps.unreal_session import (Editor, choose_target, find_editors, load_target, locate, pick_character,
                                     save_target, answer_choice, candidate_urls)

MANNY = {"name": "Manny", "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
         "control_rig": "/Game/Characters/Mannequins/Rigs/CR_Mannequin_Body"}
QUINN = {"name": "Quinn", "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple",
         "control_rig": "/Game/Characters/Mannequins/Rigs/CR_Mannequin_Body"}
A = "http://127.0.0.1:50001/mcp"
B = "http://127.0.0.1:50002/mcp"


def probe_of(table):
    return lambda url: table.get(url)


def info(project, level="ThirdPersonMap", characters=(MANNY,)):
    return {"project": project, "level": level, "characters": list(characters)}


def test_find_editors_keeps_each_url_that_answers_and_drops_the_rest():
    eds = find_editors([A, B, "http://127.0.0.1:50003/mcp"], probe_of({A: info("Alpha"), B: info("Beta")}))
    assert [(e.url, e.project, e.level) for e in eds] == [(A, "Alpha", "ThirdPersonMap"), (B, "Beta", "ThirdPersonMap")]


def test_find_editors_probes_a_url_once():
    seen = []
    find_editors([A, A], lambda u: seen.append(u) or info("Alpha"))
    assert seen == [A]


def test_none_gives_a_question_with_kei_s_own_rig_and_the_setup_step():
    q = choose_target([], "ask")
    assert isinstance(q, Question)
    assert "No Unreal Editor" in q.text and "kei unreal setup" in q.text
    assert [c["kind"] for c in q.choices] == ["retry", "kei"]
    assert "Kei's own rig" in q.text


def test_one_editor_with_the_open_setting_is_chosen_without_a_question():
    ed = find_editors([A], probe_of({A: info("Alpha")}))
    t = choose_target(ed, "open")
    assert isinstance(t, Target) and t.kind == "open" and t.session.url == A


def test_one_editor_with_the_ask_setting_is_a_question_never_a_silent_pick():
    ed = find_editors([A], probe_of({A: info("Alpha")}))
    q = choose_target(ed, "ask")
    assert isinstance(q, Question)
    assert [c["kind"] for c in q.choices] == ["open", "kei"]
    assert "Alpha" in q.text and "ThirdPersonMap" in q.text and "Manny" in q.text


def test_two_editors_are_listed_with_kei_s_own_rig_as_a_third_choice():       # Review Focus 6
    eds = find_editors([A, B], probe_of({A: info("Alpha"), B: info("Beta", "Arena", (MANNY, QUINN))}))
    for setting in ("ask", "open"):
        q = choose_target(eds, setting)
        assert isinstance(q, Question)
        assert [c["n"] for c in q.choices] == [1, 2, 3]
        assert [c["kind"] for c in q.choices] == ["open", "open", "kei"]
        assert "Alpha" in q.text and "Beta" in q.text and "Arena" in q.text and "Quinn" in q.text
        assert "Kei's own rig" in q.choices[2]["text"]


def test_an_editor_with_no_control_rig_character_is_listed_but_never_picked_by_the_open_setting():
    ed = find_editors([A], probe_of({A: info("Alpha", characters=())}))
    q = choose_target(ed, "open")
    assert isinstance(q, Question) and "no character with a Control Rig" in q.text


def test_a_bad_setting_is_refused():
    with pytest.raises(ValueError, match="apps.unreal.session"):
        choose_target([], "background")


def test_the_answer_is_a_number_and_an_out_of_range_number_is_refused():
    eds = find_editors([A, B], probe_of({A: info("Alpha"), B: info("Beta")}))
    q = choose_target(eds, "ask")
    assert answer_choice(q.choices, "2")["url"] == B
    assert answer_choice(q.choices, "3.")["kind"] == "kei"
    for bad in ("0", "4", "x"):
        with pytest.raises(ValueError, match="1 to 3"):
            answer_choice(q.choices, bad)


def test_the_choice_is_kept_by_url_and_project_and_never_a_token(tmp_path):
    eds = find_editors([A], probe_of({A: info("Alpha")}))
    q = choose_target(eds, "ask")
    save_target(tmp_path, {**q.choices[0], "token": "secret"})
    data = json.loads((tmp_path / "unreal" / "target.json").read_text())
    assert data == {"kind": "open", "url": A, "project": "Alpha"}
    assert load_target(tmp_path) == data
    assert load_target(tmp_path / "other") is None


def test_the_kept_choice_is_found_again_by_a_fresh_probe_and_a_changed_project_is_not_it():
    target = {"kind": "open", "url": A, "project": "Alpha"}
    assert locate(target, probe_of({A: info("Alpha")})).url == A
    assert locate(target, probe_of({A: info("Other")})) is None      # another project now answers on that port
    assert locate(target, probe_of({})) is None


def test_candidate_urls_are_the_config_url_and_the_port_the_project_wrote(tmp_path):
    f = tmp_path / "Saved" / "Claireon" / "MCPServer.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"port": 51000}))
    assert candidate_urls(A, str(tmp_path)) == [A, "http://127.0.0.1:51000/mcp"]
    assert candidate_urls(None, str(tmp_path)) == ["http://127.0.0.1:51000/mcp"]
    assert candidate_urls(A, A) == [A]
    assert candidate_urls(None, None) == []


def test_pick_character_takes_the_only_one_or_the_one_the_config_names():
    solo = Editor(A, "Alpha", "L", [MANNY])
    assert pick_character(solo, None, None)["name"] == "Manny"
    duo = Editor(A, "Alpha", "L", [MANNY, QUINN])
    assert pick_character(duo, QUINN["mesh"], None)["name"] == "Quinn"
    with pytest.raises(ValueError, match=r"several characters.*Manny.*Quinn.*\[apps.unreal\] mesh"):
        pick_character(duo, None, None)
    with pytest.raises(ValueError, match="no character"):
        pick_character(Editor(A, "Alpha", "L", []), None, None)
    with pytest.raises(ValueError, match="/Game/Nope"):
        pick_character(duo, "/Game/Nope", None)


def test_the_real_probe_asks_the_editor_through_kei_s_probe_script():
    from fakes.fake_claireon import FakeClaireon
    from kei.apps.unreal_session import probe_editor
    got = {"project": "Alpha", "level": "ThirdPersonMap", "characters": [MANNY], "engine": "5.8.3"}
    with FakeClaireon({"probe": lambda inp: got}) as fake:
        info = probe_editor(fake.url)
        assert info["project"] == "Alpha" and info["characters"] == [MANNY]
        assert fake.scripts == ["probe"]
    assert probe_editor("http://127.0.0.1:1/mcp", timeout=1) is None


def test_config_reads_the_unreal_keys_and_refuses_bad_ones(tmp_path):
    import textwrap
    from kei.config import ConfigError, load_config_text
    base = textwrap.dedent('''
        [animator]
        cmd = ["x"]
        [apps]
        app = "unreal"
        [apps.unreal]
        ''')
    cfg = load_config_text(base + 'session = "open"\nurl = "http://127.0.0.1:5000/mcp"\nmesh = "/Game/M"\n', tmp_path / "k.toml")
    assert (cfg.app, cfg.unreal_session, cfg.unreal_url, cfg.unreal_mesh) == ("unreal", "open", "http://127.0.0.1:5000/mcp", "/Game/M")
    assert load_config_text(base, tmp_path / "k.toml").unreal_session == "ask"
    for bad, key in (('session = "background"\n', "apps.unreal.session"), ('url = "http://10.0.0.2:5000/mcp"\n', "apps.unreal.url"),
                     ('url = 5\n', "apps.unreal.url"), ('project = ""\n', "apps.unreal.project")):
        with pytest.raises(ConfigError, match=key):
            load_config_text(base + bad, tmp_path / "k.toml")
    with pytest.raises(ConfigError, match="apps.app"):
        load_config_text(base.replace('"unreal"', '"blender"'), tmp_path / "k.toml")


def test_the_settings_table_lists_the_unreal_keys_and_reads_a_three_level_key(tmp_path):
    from kei.settings import SETTINGS, current
    keys = {s.key for s in SETTINGS}
    assert {"apps.unreal.session", "apps.unreal.url", "apps.unreal.project", "apps.unreal.mesh",
            "apps.unreal.control_rig"} <= keys
    f = tmp_path / "kei.toml"
    f.write_text('[apps.unreal]\nsession = "open"\n', encoding="utf-8")
    rows = {r["key"]: r for r in current(f)}
    assert rows["apps.unreal.session"]["value"] == "open" and rows["apps.unreal.session"]["source"] == "kei.toml"
    assert rows["apps.unreal.url"]["source"] == "default"


def test_one_mesh_with_two_rigs_is_told_apart_by_its_rig_and_picked_by_control_rig():
    # Found live: the sample mannequin has CR_Mannequin_Body and CR_Mannequin_FootIK on one mesh.
    body = dict(MANNY, control_rig="/Game/Rigs/CR_Mannequin_Body")
    foot = dict(MANNY, control_rig="/Game/Rigs/CR_Mannequin_FootIK")
    e = Editor(A, "Alpha", "L", [foot, body])
    q = choose_target([e])
    assert "CR_Mannequin_Body" in q.text and "CR_Mannequin_FootIK" in q.text
    with pytest.raises(ValueError, match="control_rig"):
        pick_character(e, MANNY["mesh"], None)
    assert pick_character(e, MANNY["mesh"], "/Game/Rigs/CR_Mannequin_Body") is body
