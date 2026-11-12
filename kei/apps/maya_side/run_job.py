"""Runs one Kei job in mayapy, with no window and no server: mayapy run_job.py <job.json> <result.json>.

A job: {"scene": a file to open (optional), "units": "cm" | "m" | ... and "up": "y" | "z" for a new scene
(optional), "calls": [{"tool", "inputs"}], "save": the file to save the scene as (optional)}.
The result: {"ok": true, "maya_version", "results": [...]} or {"ok": false, "error", "tool"}.

A test script uses script_main(fn): fn(args, cmds) returns a dict, written as {"ok": true, "data": ...}.
"""
from __future__ import annotations

import json
import os
import sys
import traceback


def _start():
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds
    return cmds


def _write(path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _finish(path, data) -> None:
    _write(path, data)
    try:            # without uninitialize, leaving mayapy is a Maya fatal error: a crash dump and a recovered scene
        import maya.standalone
        maya.standalone.uninitialize()
    except Exception:
        pass
    sys.stdout.flush()
    os._exit(0)


def run(job: dict, cmds) -> dict:
    import kei_tools
    if job.get("scene"):
        cmds.file(job["scene"], open=True, force=True)
    else:
        cmds.file(new=True, force=True)
        if job.get("units"):
            cmds.currentUnit(linear=job["units"])
        if job.get("up"):
            cmds.upAxis(axis=job["up"], rotateView=False)
    results = []
    for call in job.get("calls", []):
        try:
            results.append(kei_tools.call(call.get("tool"), call.get("inputs") or {}))
        except Exception as e:      # the job stops at the first failed call and names it
            return {"ok": False, "tool": call.get("tool"), "error": f"{call.get('tool')}: {e}",
                    "trace": traceback.format_exc()[-1500:], "results": results}
    if job.get("save"):
        kei_tools.save_as(job["save"])
    return {"ok": True, "maya_version": cmds.about(version=True), "results": results}


def script_main(fn) -> None:
    jpath, rpath = sys.argv[1], sys.argv[2]
    try:
        with open(jpath, encoding="utf-8") as f:
            job = json.load(f)
        cmds = _start()
        data = fn(job.get("args") or {}, cmds)
        out = {"ok": True, "maya_version": cmds.about(version=True), "data": data}
    except Exception as e:
        out = {"ok": False, "error": repr(e), "trace": traceback.format_exc()[-2500:]}
    _finish(rpath, out)


def main() -> None:
    jpath, rpath = sys.argv[1], sys.argv[2]
    try:
        with open(jpath, encoding="utf-8") as f:
            job = json.load(f)
        out = run(job, _start())
    except Exception as e:
        out = {"ok": False, "error": repr(e), "trace": traceback.format_exc()[-2500:]}
    _finish(rpath, out)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    main()
