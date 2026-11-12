"""Task 7 of plan 6: kei maya shelf writes the Kei host files for the user to install; Kei installs nothing."""
import subprocess
import sys

from kei.cli import main


def test_the_shelf_step_writes_the_host_files_and_prints_the_user_setup_line(tmp_path, capsys):
    out = tmp_path / "maya_setup"
    assert main(["maya", "shelf", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    for name in ("kei_host.py", "kei_tools.py", "kei_math.py", "kei_proc.py", "kei_control_rig.py", "kei_start.py"):
        assert (out / name).is_file(), name
    assert "import maya.utils, kei_host; maya.utils.executeDeferred(kei_host.start)" in text
    assert "MAYA_DISABLE_CER=1" in text
    assert "installs nothing" in text


def test_the_written_files_import_flat_outside_the_kei_package(tmp_path, capsys):
    out = tmp_path / "maya_setup"
    main(["maya", "shelf", "--out", str(out)])
    code = "import kei_host, kei_tools; assert kei_host.Host and 'set_keys' in kei_tools.TOOLS"
    r = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(out)!r}); {code}"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
