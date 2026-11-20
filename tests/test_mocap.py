"""A BVH capture as measured reference: read, matched to Kei's bones, measured, and never turned into keys."""
import json
import math

import pytest

from kei.cli import main
from kei.mocap import MocapError, bone_map, import_reference, read_bvh, to_bones, world_positions

LEG = """    JOINT {s}UpLeg
    {{
      OFFSET {x} -9 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT {s}Leg
      {{
        OFFSET 0 -42 0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT {s}Foot
        {{
          OFFSET 0 -41 0
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT {s}ToeBase
          {{
            OFFSET 0 -7 13
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {{
              OFFSET 0 0 6
            }}
          }}
        }}
      }}
    }}
"""
ARM = """          JOINT {s}Shoulder
          {{
            OFFSET {x1} 8 0
            CHANNELS 3 Zrotation Xrotation Yrotation
            JOINT {s}Arm
            {{
              OFFSET {x2} 0 0
              CHANNELS 3 Zrotation Xrotation Yrotation
              JOINT {s}ForeArm
              {{
                OFFSET 0 -28 0
                CHANNELS 3 Zrotation Xrotation Yrotation
                JOINT {s}Hand
                {{
                  OFFSET 0 -26 0
                  CHANNELS 3 Zrotation Xrotation Yrotation
                  End Site
                  {{
                    OFFSET 0 -8 0
                  }}
                }}
              }}
            }}
          }}
"""
HEAD = """HIERARCHY
ROOT Hips
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
""" + LEG.format(s="Left", x=9) + LEG.format(s="Right", x=-9) + """    JOINT Spine
    {
      OFFSET 0 10 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT Spine1
      {
        OFFSET 0 18 0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT Neck
        {
          OFFSET 0 24 0
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT Head
          {
            OFFSET 0 10 0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
              OFFSET 0 15 0
            }
          }
""" + ARM.format(s="Left", x1=3, x2=14) + ARM.format(s="Right", x1=-3, x2=-14) + """        }
      }
    }
}
"""
JOINTS = 1 + 2 * 4 + 4 + 2 * 4      # 21 joints, 3 rotations each, plus the root's 3 positions


def walk_bvh(path, frames=48, fps=24, unit=1.0):
    lines = [HEAD.replace("OFFSET", "OFFSET").strip(), "MOTION", f"Frames: {frames}", f"Frame Time: {1 / fps:.6f}"]
    for f in range(frames):
        t = f / fps
        swing = 25 * math.sin(2 * math.pi * t)
        row = [0.0, 96.0 + 2 * math.cos(4 * math.pi * t), 120.0 * t]     # forward along +z at 1.2 m/s
        rot = [0.0] * (3 * JOINTS)
        rot[3 * 1 + 1] = swing          # LeftUpLeg X rotation
        rot[3 * 5 + 1] = -swing         # RightUpLeg X rotation
        lines.append(" ".join(f"{v * (unit if i < 3 else 1):.4f}" for i, v in enumerate(row + rot)))
    text = "\n".join(lines) + "\n"
    if unit != 1.0:
        import re
        text = re.sub(r"OFFSET (\S+) (\S+) (\S+)",
                      lambda m: "OFFSET " + " ".join(f"{float(x) * unit:g}" for x in m.groups()), text)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_bvh_reads_and_forward_kinematics_place_the_joints(tmp_path):
    b = read_bvh(walk_bvh(tmp_path / "w.bvh"))
    assert len(b.joints) == JOINTS and len(b.motion) == 48 and b.frame_time == pytest.approx(1 / 24, abs=1e-6)
    p = world_positions(b)[0]
    assert p["LeftFoot"][1] == pytest.approx(96 + 2 - 9 - 42 - 41, abs=1e-6)
    assert p["Head_end"][1] > p["Head"][1]


def test_names_from_common_rigs_match_the_mannequin_bones():
    m = bone_map(["mixamorig:Hips", "mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot",
                  "mixamorig:LeftToeBase", "mixamorig:LeftShoulder", "mixamorig:LeftArm", "mixamorig:LeftForeArm",
                  "mixamorig:LeftHand", "mixamorig:Neck", "mixamorig:Head", "LHipJoint"])
    assert m["thigh_l"] == "mixamorig:LeftUpLeg" and m["calf_l"] == "mixamorig:LeftLeg"
    assert m["upperarm_l"] == "mixamorig:LeftArm" and m["lowerarm_l"] == "mixamorig:LeftForeArm"
    assert m["pelvis"] == "mixamorig:Hips" and m["neck_01"] == "mixamorig:Neck"


def test_units_are_guessed_and_the_floor_sits_under_the_ankle(tmp_path):
    for unit, scale in (("cm", 1.0), ("m", 0.01), ("in", 1 / 2.54)):
        bones, _, got, _ = to_bones(read_bvh(walk_bvh(tmp_path / f"{unit}.bvh", unit=scale)))
        assert got == unit
        lowest = min(min(f["foot_l"][2], f["foot_r"][2]) for f in bones)
        assert lowest == pytest.approx(8.0, abs=0.01)
        assert 150 < bones[0]["head"][2] < 190


def test_import_writes_the_reference_with_kei_sides_and_travel(tmp_path):
    got = import_reference(tmp_path, walk_bvh(tmp_path / "walk.bvh"), licence="CC0", source="made for the test")
    out = got["folder"]
    for f in ("joints.json", "measures.json", "sheet.png", "SOURCE.md", "REF_ROW.md"):
        assert (out / f).is_file()
    frames = json.loads((out / "joints.json").read_text())
    j0, j1 = frames[0]["joints"], frames[-1]["joints"]
    assert j0["thigh_l"][0] < 0 < j0["thigh_r"][0]                  # Kei's x is the character's right
    assert j1["pelvis"][2] - j0["pelvis"][2] == pytest.approx(1.2 * 47 / 24, rel=0.02)   # forward is +z
    m = got["measures"]
    assert m["fps"] == pytest.approx(24, abs=0.01) and 1.1 < m["speed_m_s"] < 1.3 and 3 < m["pelvis_bob_cm"] < 5
    assert "CC0" in (out / "SOURCE.md").read_text() and "never traced" in (out / "SOURCE.md").read_text()
    assert "| walk | capture (CC0) |" in (out / "REF_ROW.md").read_text()


def test_no_licence_no_import_and_other_formats_are_refused(tmp_path):
    with pytest.raises(MocapError, match="licence"):
        import_reference(tmp_path, walk_bvh(tmp_path / "w.bvh"), licence=" ")
    c3d = tmp_path / "x.c3d"
    c3d.write_bytes(b"\x00")
    with pytest.raises(MocapError, match="BVH"):
        import_reference(tmp_path, c3d, licence="CC0")


def test_a_skeleton_without_arms_names_the_missing_bones(tmp_path):
    p = tmp_path / "legs.bvh"
    walk_bvh(p)
    text = p.read_text().replace("LeftHand", "LeftPaw")
    p.write_text(text)
    with pytest.raises(MocapError, match="hand_l"):
        to_bones(read_bvh(p))


def test_a_leading_t_pose_frame_is_dropped_and_contacts_come_from_height_and_speed():
    from kei.mocap import _contacts, _t_pose
    t = {"upperarm_l": [20, 0, 140], "lowerarm_l": [48, 0, 140], "hand_l": [74, 0, 141],
         "upperarm_r": [-20, 0, 140], "lowerarm_r": [-48, 0, 140], "hand_r": [-74, 0, 139]}
    down = {**t, "lowerarm_l": [22, 0, 112], "hand_l": [23, 0, 86]}
    assert _t_pose(t) and not _t_pose(down)
    frames = [{"joints": {"foot_l": [0, 0.08 + (0.1 if 10 <= i < 20 else 0), 0.001 * i + (0.05 * i if 10 <= i < 20 else 0)]}}
              for i in range(30)]
    frames[25]["joints"]["foot_l"][1] = 0.2       # one noisy frame inside a contact... a real lift is longer
    assert _contacts(frames, "l", 24) == ["f0-9", "f20-29"]


def test_the_command(tmp_path, capsys):
    assert main(["ref", "import", str(tmp_path), str(walk_bvh(tmp_path / "walk.bvh")), "--licence", "CC0"]) == 0
    out = capsys.readouterr().out
    assert "refs" in out and "never traced" in out
