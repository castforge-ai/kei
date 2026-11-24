"""The pipeline gate: every stage of a shot left its proof in the shot folder, in order.

    check(shot_dir, deliver=False) -> (misses, notes)

Each miss starts with the code of the stage it belongs to:
  P1  brief          PLAN.md states the brief and has an "Idea sentence:" line.
  P2  rig            CHARACTER.md has a "## <character>" section per character, each with a "Rig:" line.
  P3  weight         each CHARACTER.md section has "Mass:" and "Class:" light | average | heavy | massive.
  P4  understanding  PLAN.md has an "Understanding score" line with a number.
  P5  references     PLAN.md has "Refs:" naming REFS.md files that exist, 3 vetted rows or more in all (each row with a
                     tier and a verdict), and a "Short look:" line saying what was measured (never "owed").
  P6  study          PLAN.md has a "## Departures" section with a bullet (where the shot leaves its references).
  P7  plan           PLAN.md has an X-sheet table, and the key poses exist as EITHER plan/plan.json ({"keys": [...]},
                     each key with an integer "f" and a "function" that names the pose, a word of 2 letters or more
                     such as "up") plus plan/plan_sheet.png, OR the older trio plan/keys.json + plan/pose_sheet.png +
                     plan/arcs.png. Each miss names the key's frame and says why.
  P8  blocking       out_blocking/ holds two key stills or more (key_f*.png, one per key; keys.png does not count)
                     and blocking.mp4 (or blocking.gif, the playback Kei writes when ffmpeg is missing); GATES.md has
                     "## Blocking gate: pass" with balance, arcs, timing and story lines.
  P9  passes         GATES.md has the breakdowns, spline (naming a curves image that exists), overlap, follow-through
                     and polish gates passed; the newest pass has out_p<n>/principles/principles.json (kei check),
                     newer than its shot.json, and each of its flags is fixed or declared under "## Declared" in
                     GATES.md ("- <flag id>: <reason>").
  ORDER              the plan sheet is older than the blocking video, which is older than the newest pass folder.
  P10 checks         the newest pass out_p<n>/ has body_check/body_check.json, newer than its shot.json, and each of
                     its hard flags is fixed or declared under "## Declared" ("- <check>.<part>.f<frame>: <reason>").
  P11 self-review    the newest pass has SELF_REVIEW_LOG.md whose last verdict line is READY.
  P12 deliver        (deliver=True) video/*.mp4; REVIEW.md "## What I learned" with a bullet; a GROWTH.md names the
                     shot: in the shot folder, beside it, or, for a shot in a character folder, beside that folder.
The order check always runs. No file in the shot folder can switch it off, because the agent writes that folder.
"""
from __future__ import annotations

import glob
import json
import os
import re

CLASSES = ("light", "average", "heavy", "massive")
MIN_FUNCTION = 2   # a pose function is a word: "up" and "down" are pose names, "x" is not


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _section(text, head):
    m = re.search(r"^## %s[^\n]*\n(.*?)(?=^## |\Z)" % re.escape(head), text, re.M | re.S)
    return m.group(1) if m else None


def _gate(gates, name):
    m = re.search(r"^## %s gate: *(\w+)[^\n]*\n(.*?)(?=^## |\Z)" % name, gates or "", re.M | re.S | re.I)
    return (m.group(1).lower(), m.group(2)) if m else (None, "")


def _declared(gates):
    """The principle flag ids declared in GATES.md under "## Declared", one per line with its reason. Every
    "## Declared" section counts, not only the first."""
    ids = []   # a list, not a set: two flags can share an id (left and right foot), one declaration each
    for m in re.finditer(r"^## Declared[^\n]*\n(.*?)(?=^## |\Z)", gates or "", re.M | re.S):
        # a principle id (principle.kind.part.f<n>) or a body check id (check.part.f<n>)
        ids.extend(re.findall(r"^\s*[-*]\s*`?([a-z_]+(?:\.[\w-]+){1,2}\.f\d+)`?\s*[:-]\s*\S", m.group(1), re.M))
    return ids


DECLARED_DRIFT = 3   # frames a flag's start may move after a re-key and still be the flag that was declared
_FLAG_ID = re.compile(r"^(.+)\.f(\d+)$")


def open_flags(flags, gates):
    """The flags not declared in GATES.md. A declaration names a flag by its id, whose last part is the flag's
    first frame. A re-key that moves that frame by up to DECLARED_DRIFT frames keeps the flag declared, and each
    declaration covers one flag only: the exact id first, then the nearest frame."""
    free = {}
    for d in _declared(gates):
        m = _FLAG_ID.match(d)
        if m:
            free.setdefault(m.group(1), []).append(int(m.group(2)))
    out, rest = [], []
    for fl in flags:
        m = _FLAG_ID.match(fl.get("id") or "")
        frames = free.get(m.group(1), []) if m else []
        if m and int(m.group(2)) in frames:
            frames.remove(int(m.group(2)))
        else:
            rest.append((fl, m))
    for fl, m in rest:
        frames = free.get(m.group(1), []) if m else []
        near = sorted(frames, key=lambda f: abs(f - int(m.group(2)))) if m else []
        if near and abs(near[0] - int(m.group(2))) <= DECLARED_DRIFT:
            frames.remove(near[0])
        else:
            out.append(fl)
    return out


def _passes(J):
    found = [p for p in glob.glob(J("out_p*")) if os.path.isdir(p) and re.search(r"out_p(\d+)$", p)]
    return sorted(found, key=lambda p: int(re.search(r"out_p(\d+)$", p).group(1)))


def _function_problem(fn) -> str | None:
    """Why a key's "function" is not a pose name, or None. Short standard names ("up", "down") are pose names."""
    if fn is None:
        return 'has no "function" (the pose function: contact, down, up, passing...)'
    if not isinstance(fn, str):
        return '"function" must be text, not %r' % (fn,)
    name = fn.strip()
    if not name:
        return '"function" is empty: name the pose function (contact, down, up, passing...)'
    if len(name) < MIN_FUNCTION or not re.search(r"[^\W\d_]", name):
        return '"function" %r is not a pose name: use a word of %d letters or more' % (fn, MIN_FUNCTION)
    return None


def _key_misses(keys, frame_key: str, fn_key: str, where: str) -> list[str]:
    """One miss per faulty key, naming the key (its frame, else its place in the list) and why."""
    out = []
    for i, k in enumerate(keys):
        if not isinstance(k, dict):
            out.append("P7 %s key %d is not an object" % (where, i + 1))
            continue
        f = k.get(frame_key)
        if isinstance(f, int) and not isinstance(f, bool):
            name = "f %d" % f
        else:
            name = "key %d" % (i + 1)
            if f is None:
                out.append('P7 %s %s has no frame "%s"' % (where, name, frame_key))
            else:
                out.append('P7 %s %s: "%s" must be an integer frame, not %r' % (where, name, frame_key, f))
        why = _function_problem(k.get(fn_key))
        if why:
            out.append("P7 %s %s %s" % (where, name, why.replace('"function"', '"%s"' % fn_key)))
    return out


def _check_plan(J, miss):
    pj = _read(J("plan", "plan.json"))
    if pj is not None:
        try:
            data = json.loads(pj)
        except ValueError as e:
            miss.append("P7 plan/plan.json is not valid JSON: %s" % e)
            data = None
        if data is not None:
            keys = data.get("keys") if isinstance(data, dict) else None
            if not isinstance(keys, list) or not keys:
                miss.append('P7 plan/plan.json has no "keys" list: each key pose needs an integer "f" and a "function"')
            else:
                miss.extend(_key_misses(keys, "f", "function", "plan/plan.json"))
        if not os.path.exists(J("plan", "plan_sheet.png")):
            miss.append('P7 no plan/plan_sheet.png: give each key in plan/plan.json a "drawing" and Kei draws the sheet')
        return
    kj = _read(J("plan", "keys.json"))
    if kj is None:
        miss.append("P7 no plan/plan.json (the key poses: frame, function, kind, note) and no plan sheet")
        return
    try:
        keys = json.loads(kj)
    except ValueError:
        miss.append("P7 plan/keys.json is not valid JSON")
    else:
        if not isinstance(keys, list) or not keys:
            miss.append("P7 plan/keys.json: every key pose needs a frame and a function")
        else:
            miss.extend(_key_misses(keys, "f", "fn", "plan/keys.json"))
    for f in ("pose_sheet.png", "arcs.png"):
        if not os.path.exists(J("plan", f)):
            miss.append("P7 no plan/%s" % f)


def _growth_files(shot, plan):
    """Where a shot's GROWTH.md entry may be: the shot folder, the folder that holds it, and, when that folder is a
    character folder (it holds a CHARACTER.md, or is named after the shot's Character line), the folder above it,
    where the shared GROWTH.md stays when shots are moved into character folders."""
    shot = os.path.abspath(shot)
    parent = os.path.dirname(shot)
    out = [os.path.join(shot, "GROWTH.md"), os.path.join(parent, "GROWTH.md")]
    named = [n.replace("*", "").strip().lower()
             for n in re.findall(r"^[ \t>*+-]*\**character\**[ \t]*:[ \t]*\**(.*)$", plan, re.M | re.I)]
    if os.path.isfile(os.path.join(parent, "CHARACTER.md")) or os.path.basename(parent).lower() in named:
        out.append(os.path.join(os.path.dirname(parent), "GROWTH.md"))
    return out


def check(shot: str, deliver: bool = False) -> tuple[list[str], list[str]]:
    miss, note = [], []
    J = lambda *p: os.path.join(shot, *p)  # noqa: E731
    plan = _read(J("PLAN.md"))
    if plan is None:
        return ["P1 no PLAN.md in %s" % shot], note
    # P1
    if not re.search(r"brief", plan, re.I):
        miss.append("P1 PLAN.md does not state the brief")
    if not re.search(r"^Idea sentence:\s*\S", plan, re.M | re.I):
        miss.append('P1 PLAN.md has no "Idea sentence:" line')
    # P2, P3
    ch = _read(J("CHARACTER.md"))
    if ch is None:
        miss.append("P2 no CHARACTER.md (the rig evaluation)")
        miss.append("P3 no CHARACTER.md (the weight evaluation)")
    else:
        secs = re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", ch, re.M | re.S)
        if not secs:
            miss.append('P2 CHARACTER.md has no "## <character>" section')
        for name, body in secs:
            name = name.strip()
            if not re.search(r"^\s*-?\s*Rig:\s*\S", body, re.M):
                miss.append('P2 %s: no "Rig:" line' % name)
            if not re.search(r"^\s*-?\s*Mass:\s*\S", body, re.M):
                miss.append('P3 %s: no "Mass:" line' % name)
            m = re.search(r"^\s*-?\s*Class:\s*(\w+)", body, re.M)
            if not m or m.group(1).lower() not in CLASSES:
                miss.append('P3 %s: no "Class:" light, average, heavy or massive' % name)
    # P4
    if not re.search(r"Understanding score[^\n]*?\d", plan, re.I):
        miss.append("P4 PLAN.md has no understanding score with a number")
    # P5
    m = re.search(r"^Refs:\s*(.+)$", plan, re.M)
    if not m:
        miss.append('P5 PLAN.md has no "Refs:" line naming the REFS.md files')
    else:
        rows = 0
        for r in re.findall(r"[\w./\\-]*REFS\.md", m.group(1)):   # a bare REFS.md counts too
            p = r if os.path.isabs(r) else os.path.normpath(J(r))
            t = _read(p)
            if t is None:
                miss.append("P5 %s does not exist" % r)
                continue
            for ln in t.splitlines():
                c = [x.strip() for x in ln.strip().strip("|").split("|")]
                if ln.startswith("|") and len(c) >= 5 and not set(ln) <= set("|-: ") and c[0].lower() != "ref":
                    if re.match(r"^[RABC]\b", c[1]) and re.match(r"^(keep|flag|reject)", c[-1], re.I):
                        rows += 1
        if rows < 3:
            miss.append("P5 %d vetted reference rows (tier and verdict); 3 or more are needed" % rows)
    m = re.search(r"^Short look:\s*(.+)$", plan, re.M)
    if not m or re.search(r"\bowed\b|\bnot done\b|\btodo\b", m.group(1), re.I) or len(m.group(1).strip()) < 25:
        miss.append('P5 PLAN.md has no "Short look:" line saying what was measured ("owed" is not allowed)')
    # P6
    dep = _section(plan, "Departures")
    if not dep or not re.search(r"^\s*- \S", dep, re.M):
        miss.append('P6 PLAN.md has no "## Departures" section with a bullet (where the shot leaves its references)')
    # P7
    if not re.search(r"^\|\s*frames?\s*\|", plan, re.M | re.I):
        miss.append('P7 PLAN.md has no X-sheet table ("| frames |")')
    _check_plan(J, miss)
    # P8
    gates = _read(J("GATES.md"))
    if len(glob.glob(J("out_blocking", "key_f*.png"))) < 2:
        miss.append("P8 out_blocking/ has fewer than two key stills (key_f*.png): blocking needs two keys or more")
    bm = J("out_blocking", "blocking.mp4")
    if not os.path.exists(bm) and os.path.exists(J("out_blocking", "blocking.gif")):
        bm = J("out_blocking", "blocking.gif")
    if not os.path.exists(bm):
        miss.append("P8 no out_blocking/blocking.mp4 or blocking.gif (the stepped keys played back)")
    v, body = _gate(gates, "Blocking")
    if v != "pass":
        miss.append("P8 GATES.md: the blocking gate is %s" % (v or "missing"))
    else:
        for w in ("balance", "arcs", "timing", "story"):
            if not re.search(r"^\s*- %s:\s*\S.{10,}" % w, body, re.M | re.I):
                miss.append('P8 the blocking gate has no "%s:" line' % w)
    # P9
    for g in ("Breakdowns", "Spline", "Overlap", "Follow-through", "Polish"):
        v, body = _gate(gates, g)
        if v != "pass":
            miss.append("P9 GATES.md: the %s gate is %s" % (g.lower(), v or "missing"))
        elif g == "Spline":
            im = re.findall(r"[\w./\\-]+\.png", body)
            if not any(os.path.exists(J(x)) for x in im):
                miss.append("P9 the spline gate names no curves image that exists")
    # P9: the twelve principles on the newest pass, every flag fixed or declared
    passes = _passes(J)
    if passes:
        pj = os.path.join(passes[-1], "principles", "principles.json")
        sj = os.path.join(passes[-1], "shot.json")
        if not (os.path.exists(pj) and (not os.path.exists(sj) or os.path.getmtime(pj) > os.path.getmtime(sj))):
            miss.append("P9 the twelve principles have not been checked on %s: run kei check <shot> %s"
                        % (os.path.basename(passes[-1]), os.path.basename(passes[-1])[4:]))
        else:
            try:
                with open(pj, encoding="utf-8") as f:
                    flags = json.load(f).get("flags") or []
            except ValueError:
                flags = []
            for fl in open_flags(flags, gates):
                miss.append("P9 %s (%s f%s-%s): %s. Fix it, or declare it in GATES.md under \"## Declared\" "
                            "as \"- %s: <reason>\"" % (fl.get("id"), fl.get("principle"), fl["frames"][0],
                                                        fl["frames"][1], fl.get("what"), fl.get("id")))
    # ORDER
    ps = J("plan", "plan_sheet.png") if os.path.exists(J("plan", "plan_sheet.png")) else J("plan", "pose_sheet.png")
    if os.path.exists(ps) and os.path.exists(bm) and os.path.getmtime(ps) > os.path.getmtime(bm):
        miss.append("ORDER the plan sheet is newer than the blocking pass")
    if os.path.exists(bm):
        for p in passes[-1:]:
            if os.path.getmtime(p) < os.path.getmtime(bm):
                miss.append("ORDER %s is older than the blocking pass" % os.path.basename(p))
    # P10, P11: the newest pass
    if not passes:
        miss.append("P10 the checks have not run (no pass yet)")
        miss.append("P11 the self-review is not READY (no pass yet)")
    else:
        latest = passes[-1]
        name = os.path.basename(latest)
        bc, sj = os.path.join(latest, "body_check", "body_check.json"), os.path.join(latest, "shot.json")
        if not (os.path.exists(bc) and (not os.path.exists(sj) or os.path.getmtime(bc) > os.path.getmtime(sj))):
            miss.append("P10 the checks have not run on the latest pass (%s)" % name)
        else:   # the gate reads Kei's measurement, not a line the agent wrote: every hard fault fixed or declared
            from kei.explain import body_id
            try:
                with open(bc, encoding="utf-8") as f:
                    body = json.load(f).get("flags") or []
            except ValueError:
                body = []
            hard = [{**fl, "id": body_id(fl)} for fl in body if fl.get("rule") == "hard" and not fl.get("note")]
            still_open = open_flags(hard, gates)
            for fl in still_open:
                miss.append("P10 %s (f%s-%s): %s. Fix it, or declare it in GATES.md under \"## Declared\" as "
                            "\"- %s: <reason>\"" % (fl["id"], fl["frames"][0], fl["frames"][1], fl.get("what"),
                                                     fl["id"]))
            # a declaration must fit the measurement, and a control that snaps in one frame is a fault on the keys
            from kei.review_rigor import declared_misses, snap_misses
            try:
                with open(bc, encoding="utf-8") as f:
                    whole = json.load(f)
            except ValueError:
                whole = {}
            left = {id(fl) for fl in still_open}
            miss += declared_misses(shot, [fl for fl in hard if id(fl) not in left], whole)
            miss += snap_misses(shot, name[len("out_"):])
        log = _read(os.path.join(latest, "SELF_REVIEW_LOG.md")) or ""
        verdicts = [ln for ln in log.splitlines() if "READY" in ln]
        if not verdicts or "NOT READY" in verdicts[-1]:
            miss.append("P11 the latest self-review is not READY (%s)" % name)
    # P12
    if deliver:
        if not glob.glob(J("video", "*.mp4")):
            miss.append("P12 no video/*.mp4")
        learned = _section(_read(J("REVIEW.md")) or "", "What I learned")
        if not learned or not re.search(r"^\s*- \S", learned, re.M):
            miss.append('P12 REVIEW.md has no "## What I learned" with a bullet')
        name = os.path.basename(os.path.abspath(shot))
        if not any(name in (_read(g) or "") for g in _growth_files(shot, plan)):
            miss.append("P12 no GROWTH.md (in the shot folder or beside it) has an entry for this shot")
    return miss, note
