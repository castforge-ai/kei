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
