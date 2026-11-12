"""In mayapy: open a keyed scene and read the world position (metres, y up) of some vertices of some meshes on every
frame from start to end, as they play deformed by their skin."""
from run_job import script_main


def main(args, cmds):
    import maya.api.OpenMaya as om
    import kei_tools
    cmds.file(args["scene"], open=True, force=True)
    f, up = kei_tools.unit_per_m(), kei_tools.up_axis()
    fns = {}
    for mesh in args["meshes"]:
        sel = om.MSelectionList()
        sel.add(mesh)
        dag = sel.getDagPath(0)
        dag.extendToShape()
        fns[mesh] = om.MFnMesh(dag)
    frames = []
    for fr in range(int(args["start"]), int(args["end"]) + 1):
        cmds.currentTime(fr, update=True)
        row = {}
        for mesh, idx in args["meshes"].items():
            pts = fns[mesh].getPoints(om.MSpace.kWorld)
            row[mesh] = [kei_tools.to_metres([pts[i].x, pts[i].y, pts[i].z], f, up) for i in idx]
        frames.append({"f": fr, "points": row})
    return {"frames": frames}


script_main(main)
