"""Task 7 of plan 7: the one pair of unit and axis functions, with the frame of the character."""
import pytest

from kei.apps.unreal_units import (MANNEQUIN, Frame, frame_from_rest, kei_dir_to_ue, kei_to_ue, ue_dir_to_kei,
                                   ue_to_kei)

PLUS_X = Frame((0.0, -1.0, 0.0), (1.0, 0.0, 0.0))      # a character that faces +X: its left side is on -Y


def test_the_mannequin_frame_left_x_forward_y():
    assert ue_to_kei((10, 20, 30), MANNEQUIN) == pytest.approx((-0.1, 0.3, 0.2))
    assert ue_to_kei((50, 0, 0), MANNEQUIN) == pytest.approx((-0.5, 0, 0))       # its left is Kei's negative x
    assert ue_to_kei((0, 100, 0), MANNEQUIN) == pytest.approx((0, 0, 1))         # forward is Kei +z
    assert ue_to_kei((0, 0, 100), MANNEQUIN) == pytest.approx((0, 1, 0))         # up is Kei +y


def test_a_character_that_faces_plus_x_gives_the_same_kei_numbers_for_the_same_body():
    assert ue_to_kei((10, 20, 30), PLUS_X) == pytest.approx((0.2, 0.3, 0.1))
    assert ue_to_kei((0, -50, 0), PLUS_X) == pytest.approx((-0.5, 0, 0))         # its left (-Y) is Kei's negative x
    assert ue_to_kei((100, 0, 0), PLUS_X) == pytest.approx((0, 0, 1))


def test_the_frame_comes_from_the_rest_pose_of_the_thighs():
    f = frame_from_rest((9.0, 0.0, 92.0), (-9.0, 0.0, 92.0))
    assert f.left == pytest.approx((1, 0, 0)) and f.forward == pytest.approx((0, 1, 0))
    g = frame_from_rest((0.0, -9.0, 92.0), (0.0, 9.0, 92.0))
    assert g.left == pytest.approx((0, -1, 0)) and g.forward == pytest.approx((1, 0, 0))
    h = frame_from_rest((6.4, 6.4, 90.0), (-6.4, -6.4, 90.0))                   # turned 45 degrees: still orthonormal
    assert h.left[0] ** 2 + h.left[1] ** 2 == pytest.approx(1) and h.forward == pytest.approx((-h.left[1], h.left[0], 0))
    with pytest.raises(ValueError):
        frame_from_rest((0, 0, 92), (0, 0, 80))


@pytest.mark.parametrize("frame", [MANNEQUIN, PLUS_X, frame_from_rest((3, 4, 92), (-3, -4, 92))])
@pytest.mark.parametrize("p", [(0, 0, 0), (10, 20, 30), (-153.25, 7.5, 1e3), (0.001, -0.002, 0.003)])
def test_a_round_trip_is_exact_to_a_billionth(p, frame):
    assert kei_to_ue(ue_to_kei(p, frame), frame) == pytest.approx(p, abs=1e-9)
    assert ue_to_kei(kei_to_ue(p, frame), frame) == pytest.approx(p, abs=1e-9)


@pytest.mark.parametrize("frame", [MANNEQUIN, PLUS_X])
def test_the_axes_keep_handedness_and_never_mirror(frame):
    def det(rows):
        (a, b, c), (d, e, f), (g, h, i) = rows
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    cols = [ue_dir_to_kei(v, frame) for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    # Unreal is left-handed (X forward, Y right, Z up) and so is Kei (x right, y up, z forward): the determinant of
    # the map between them is the same as the one of the Unreal-to-Kei cyclic permutation, +1
    assert det(cols) == pytest.approx(1)
    assert kei_dir_to_ue(ue_dir_to_kei((1, 2, 3), frame), frame) == pytest.approx((1, 2, 3))
