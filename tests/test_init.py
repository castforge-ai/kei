"""kei init writes kei.toml where Kei is going to run, never over an existing one, and the example ships in the package."""
import importlib.util
from pathlib import Path

from kei.cli import main
from kei.config import example_config, load_config


def test_init_writes_a_kei_toml_that_loads_and_never_overwrites(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "kei.toml").read_bytes() == example_config().read_bytes()
    assert load_config(tmp_path / "kei.toml").animator.cmd
    (tmp_path / "kei.toml").write_text("# mine\n", encoding="utf-8")
    capsys.readouterr()
    assert main(["init"]) == 0
    assert (tmp_path / "kei.toml").read_text(encoding="utf-8") == "# mine\n"
    assert "already here" in capsys.readouterr().out


def test_init_says_which_agent_commands_are_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert main(["init"]) == 0
    assert "not found on your PATH" in capsys.readouterr().out


def test_the_example_is_found_inside_the_package_when_it_is_there(tmp_path, monkeypatch):
    spec = importlib.util.find_spec("kei")
    inside = Path(spec.origin).parent / "kei.example.toml"
    assert example_config() == inside or example_config().name == "kei.example.toml"
    assert example_config().is_file()


def test_the_wheel_ships_the_example_inside_kei():
    import tomllib
    root = Path(__file__).resolve().parent.parent
    cfg = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    inc = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert inc == {"kei.example.toml": "kei/kei.example.toml"}


def test_python_dash_m_kei_runs_the_same_command(tmp_path):
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "kei", "characters"], cwd=tmp_path, capture_output=True, text=True)
    assert out.returncode == 0 and "built in:" in out.stdout


def test_a_dotted_app_setting_is_written_into_its_existing_table(tmp_path, monkeypatch):
    """Every apps.maya.* and apps.unreal.* setting, on the file kei init writes (the tables are already there)."""
    import tomllib
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    for key, value in (("apps.unreal.url", "http://127.0.0.1:50000/mcp"), ("apps.unreal.session", "open"),
                       ("apps.unreal.project", "C:/Projects/MyGame"), ("apps.unreal.mesh", "/Game/SKM_Manny"),
                       ("apps.unreal.control_rig", "/Game/CR_Body"), ("apps.maya.session", "open"),
                       ("apps.app", "unreal")):
        assert main(["settings", "set", key, value]) == 0, key
    data = tomllib.loads((tmp_path / "kei.toml").read_text(encoding="utf-8"))
    assert data["apps"]["app"] == "unreal" and data["apps"]["maya"]["session"] == "open"
    assert data["apps"]["unreal"] == {"session": "open", "project": "C:/Projects/MyGame",
                                      "url": "http://127.0.0.1:50000/mcp", "mesh": "/Game/SKM_Manny",
                                      "control_rig": "/Game/CR_Body"}


def test_version_flag_prints_the_package_version(capsys):
    import pytest
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0 and capsys.readouterr().out.startswith("kei-animator ")
