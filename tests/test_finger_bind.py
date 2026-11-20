"""Fitted models: the fingers past the palm get their skin, and an import reports a finger bone with none."""
from kei.models.bind import FINGER_REACH, _nearest, finger_weights


SEGS = [("lowerarm_l", (0.0, 1.0, 0.0), (0.25, 1.0, 0.0)), ("hand_l", (0.25, 1.0, 0.0), (0.35, 1.0, 0.0)),
        ("thumb_02_l", (0.30, 1.0, 0.05), (0.34, 1.0, 0.07)), ("index_01_l", (0.35, 1.0, 0.02), (0.38, 1.0, 0.02))]


def test_a_point_past_the_palm_goes_to_the_nearest_finger_even_beyond_its_reach():
    p = (0.33, 1.0, 0.085)                      # 2 cm off the thumb bone: past FINGER_REACH, still the thumb
    assert FINGER_REACH < 0.02
    assert _nearest(p, SEGS, 1.0)[0][1] == "thumb_02_l"


def test_a_point_on_the_palm_stays_on_the_hand():
    assert _nearest((0.27, 1.0, 0.0), SEGS, 1.0)[0][1] == "hand_l"


def test_finger_weights_count_rigid_and_skinned_vertices():
    class P:
        def __init__(self, bone, verts, skin=None):
            self.bone, self.verts, self.skin = bone, verts, skin
    w = finger_weights([P("index_01_l", [(0, 0, 0)] * 3),
                        P("hand_l", [(0, 0, 0)], [[("thumb_02_l", 0.5, None, None), ("hand_l", 0.5, None, None)]])])
    assert w["index_01_l"] == 3 and w["thumb_02_l"] == 0.5 and w["thumb_03_l"] == 0
