"""In mayapy: load an imported character (KEI_CHARACTERS) in a centimetre scene, and report what Maya built: joints,
each mesh's skin weights against the job, its UVs and the file texture on its material."""
from run_job import script_main


def main(args, cmds):
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma
    import kei_tools
    from kei.apps.maya_scene import character_job
    name = args["character"]
    job = character_job(name, texture_dir=args["texture_dir"])
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    kei_tools.call("load_character", {"job": job})
    joints = cmds.ls(name + ":*", type="joint")
    out = {"joints_m": {k.split(":")[-1]: v for k, v in kei_tools.joint_world_metres(joints).items()}, "meshes": {}}
    bones = [b["name"] for b in job["bones"]]
    for m in job["meshes"]:
        node = f"{name}:{m['name']}"
        sel = om.MSelectionList()
        sel.add(f"{name}:{m['name']}_skin")
        sel.add(node)
        sk = oma.MFnSkinCluster(sel.getDependNode(0))
        dag = sel.getDagPath(1)
        dag.extendToShape()
        infl = [p.partialPathName().split(":")[-1] for p in sk.influenceObjects()]
        comp = om.MFnSingleIndexedComponent()
        cobj = comp.create(om.MFn.kMeshVertComponent)
        comp.setCompleteData(len(m["points"]))
        w, k = sk.getWeights(dag, cobj)
        bad = 0
        for v, want in enumerate(m["weights"]):
            row = {infl[i]: w[v * k + i] for i in range(k) if w[v * k + i] > 1e-9}
            exp = {bones[b]: x for b, x in want}
            if set(row) != set(exp) or any(abs(row[b] - exp[b]) > 1e-6 for b in exp):
                bad += 1
        fn = om.MFnMesh(dag)
        pts = fn.getPoints(om.MSpace.kWorld)
        far = max(max(abs(p[i] / 100.0 - q[i]) for i in range(3)) for p, q in zip(pts, m["points"]))
        info = {"vertices": fn.numVertices, "weight_mismatches": bad, "rest_far_m": far, "uvs": fn.numUVs()}
        if m.get("uvs"):
            u, v = fn.getUVs()
            counts, ids = fn.getAssignedUVs()
            info["first_uvs"] = [[u[ids[i]], v[ids[i]]] for i in range(3)]
        sg = (cmds.listConnections(fn.fullPathName(), type="shadingEngine") or [None])[0]
        sh = (cmds.listConnections(sg + ".surfaceShader") or [None])[0] if sg else None
        files = cmds.listConnections(sh + ".baseColor", type="file") or [] if sh else []
        info["shader"] = sh.split(":")[-1] if sh else None
        if files:
            info["file"] = cmds.getAttr(files[0] + ".fileTextureName")
            info["colour_space"] = cmds.getAttr(files[0] + ".colorSpace")
        out["meshes"][m["name"]] = info
    return out


script_main(main)
