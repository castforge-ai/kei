import sys
import time

from kei.config import SeatSpec
from kei.seats import CliSeat, FakeSeat, SeatResult


def py(script, timeout_s=30):
    return CliSeat(SeatSpec(name="fake", cmd=[sys.executable, "-c", script], timeout_s=timeout_s))


def test_prompt_reaches_stdin_as_utf8(tmp_path):
    prompt = "Brief : une chute lourde, élan coupé"
    seat = py("import sys; open('got.bin', 'wb').write(sys.stdin.buffer.read())")
    r = seat.run(prompt, tmp_path)
    assert r.exit_code == 0
    assert (tmp_path / "got.bin").read_bytes() == prompt.encode("utf-8")


def test_output_is_captured(tmp_path):
    r = py("print('stage done')").run("x", tmp_path)
    assert r.output.strip() == "stage done"


def test_timeout_returns_124(tmp_path):
    t0 = time.monotonic()
    r = py("import time; time.sleep(10)", timeout_s=1).run("x", tmp_path)
    assert r == SeatResult(124, "timeout after 1 s")
    assert time.monotonic() - t0 < 5


def test_missing_command_returns_127(tmp_path):
    seat = CliSeat(SeatSpec(name="none", cmd=["kei-no-such-cli"]))
    assert seat.run("x", tmp_path) == SeatResult(127, "command not found: kei-no-such-cli")


def test_fake_seat_calls_its_action(tmp_path):
    seat = FakeSeat("fake", lambda prompt, wd: SeatResult(0, prompt.upper()))
    assert seat.run("ok", tmp_path) == SeatResult(0, "OK")
    assert seat.name == "fake"


def test_kei_own_scripts_folder_comes_first_on_the_seat_path(tmp_path, monkeypatch):
    import os
    import sysconfig
    from pathlib import Path
    scripts = os.path.normcase(sysconfig.get_path("scripts"))
    rest = [p for p in os.environ["PATH"].split(os.pathsep) if os.path.normcase(p.rstrip(r"\/")) != scripts]
    monkeypatch.setenv("PATH", os.pathsep.join(rest))   # as when kei runs from a shell that never activated it
    r = py("import os; print(os.environ['PATH'].split(os.pathsep)[0])").run("x", tmp_path)
    first = Path(r.output.strip())
    assert first == Path(sysconfig.get_path("scripts"))
    assert any(first.glob("kei*")), "the kei command lives there"
