"""In mayapy: load Kei and Keira in a centimetre and a metre scene, and report what Maya built."""
from run_job import script_main


def report(cmds, ns):
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma
    import kei_tools
    joints = cmds.ls(ns + ":*", type="joint")
    parents = {}
    for j in joints:
        p = cmds.listRelatives(j, parent=True)
        parents[j.split(":")[-1]] = p[0].split(":")[-1] if p and cmds.nodeType(p[0]) == "joint" else None
    pos = kei_tools.joint_world_metres(joints)
    out = {"joint_parents": parents, "joints_m": {k.split(":")[-1]: v for k, v in pos.items()}}
    # skin: every vertex has one influence at weight 1, the bone the job named
    from kei.apps.maya_scene import character_job
    job = character_job(cmds.getAttr(ns + ":kei_rig.kei_character"))
    names = [b["name"] for b in job["bones"]]
    bad, count = 0, 0
    for m in job["meshes"]:
        if not m["points"]:
            continue
        skin = f"{ns}:{m['name']}_skin"
        sel = om.MSelectionList()
        sel.add(skin)
        sel.add(f"{ns}:{m['name']}")
        sk = oma.MFnSkinCluster(sel.getDependNode(0))
        dag = sel.getDagPath(1)
        dag.extendToShape()
        infl = [p.partialPathName().split(":")[-1] for p in sk.influenceObjects()]
        comp = om.MFnSingleIndexedComponent()
        cobj = comp.create(om.MFn.kMeshVertComponent)
        comp.setCompleteData(len(m["points"]))
        w, k = sk.getWeights(dag, cobj)
        for v, b in enumerate(m["bone"]):
            row = [w[v * k + i] for i in range(k)]
            if abs(row[infl.index(names[b])] - 1) > 1e-6 or abs(sum(row) - 1) > 1e-6:
                bad += 1
        count += len(m["points"])
    out["skin_mismatches"], out["vertex_count"] = bad, count
    mats = {}
    for m in job["materials"]:
        sh = f"{ns}:{m['name']}_mat"
        lin = cmds.getAttr(sh + ".baseColor")[0]
        srgb = [c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in lin]
        mats[m["name"]] = {"colour_srgb": srgb, "emission": cmds.getAttr(sh + ".emission")}
    out["materials"] = mats
    out["top"] = ns + ":kei_rig"
    out["tags"] = {a: cmds.getAttr(f"{ns}:kei_rig.{a}") for a in ("kei_character", "kei_units")}
    return out


def main(args, cmds):
    import kei_tools
    from kei.apps.maya_scene import character_job
    out = {}
    for name in ("kei", "keira"):
        for unit in ("cm", "m"):
            cmds.file(new=True, force=True)
            cmds.currentUnit(linear=unit)
            kei_tools.call("load_character", {"job": character_job(name)})
            out[f"{name}_{unit}"] = report(cmds, name)
    cmds.file(new=True, force=True)
    kei_tools.call("load_character", {"job": character_job("kei", emission=0.0)})
    out["kei_off"] = report(cmds, "kei")
    return out


script_main(main)
