"""In mayapy: a stand-in for the user's open Maya. It builds Kei with its control rig, saves it as the user's scene,
makes an unsaved change, starts the real Kei host and keeps Maya's main thread serving it (in batch the main thread
must pump idle events) until the stop file appears. mayapy host_in_batch.py <folder> <session_root>"""
import os
import sys
import time

folder, root = sys.argv[1], sys.argv[2]
import maya.standalone  # noqa: E402
maya.standalone.initialize(name="python")
import maya.utils  # noqa: E402
from maya import cmds  # noqa: E402

import kei_host  # noqa: E402
import kei_tools  # noqa: E402
from kei.apps.maya_controls import control_rig_job  # noqa: E402
from kei.apps.maya_scene import character_job  # noqa: E402

cmds.file(new=True, force=True)
kei_tools.call("load_character", {"job": character_job("kei")})
kei_tools.call("build_control_rig", {"job": control_rig_job("kei")})
kei_tools.save_as(os.path.join(folder, "user.ma").replace("\\", "/"))
cmds.setAttr("kei:c_body_ctl.translateY", 3.0)          # the user's unsaved change
host = kei_host.Host(kei_tools.TOOLS, maya.utils.executeInMainThreadWithResult, root, kei_host._maya_undo,
                     kei_host._maya_info)
host.start()
stop = os.path.join(folder, "stop")
end = time.time() + 300
while not os.path.exists(stop) and time.time() < end:
    maya.utils.processIdleEvents()
    time.sleep(0.005)
last_undo = cmds.undoInfo(q=True, undoName=True)
for layer in cmds.ls(type="animLayer") or []:     # the user's own value, under Kei's pass layers
    if layer.startswith("kei_"):
        cmds.animLayer(layer, edit=True, mute=True)
with open(os.path.join(folder, "state.txt"), "w") as f:
    f.write(f"{cmds.file(q=True, sceneName=True)}|{cmds.file(q=True, modified=True)}|"
            f"{cmds.getAttr('kei:c_body_ctl.translateY')}|{last_undo}")
host.stop()
maya.standalone.uninitialize()
os._exit(0)
