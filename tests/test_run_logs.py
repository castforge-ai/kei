"""Every seat run is kept in .kei/runs/, and the history records its file, seconds and prompt size."""
from kei.conductor import run_shot
from kei.seats import FakeSeat
from test_conductor import CFG, Recorder, shot
from test_conductor_critic import PASS, critic


def test_the_animator_and_critic_runs_are_kept_with_their_timing(tmp_path):
    root = shot(tmp_path)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[critic("c1", lambda t, p: PASS)])
    runs = root / ".kei" / "runs"
    assert (runs / "brief-animator-1.prompt.txt").is_file() and (runs / "brief-animator-1.out.txt").is_file()
    assert list(runs.glob("critic-c1-*.prompt.txt")), "the critics' runs too"
    from kei.state import load_state
    first = next(h for h in load_state(root).history if h["stage"] == "brief")
    assert first["run"] == ".kei/runs/brief-animator-1" and first["prompt_chars"] > 100 and "seconds" in first
