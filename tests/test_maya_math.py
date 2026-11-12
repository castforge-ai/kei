"""The rotation and axis maths the Maya adapter shares between Kei's side and Maya's side (no Maya needed)."""
import math
import random

import pytest

from kei.apps.maya_side import kei_math as km


ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for ra, rb in zip(a, b) for x, y in zip(ra, rb))


@pytest.mark.parametrize("order", ORDERS)
def test_euler_round_trips_in_every_rotate_order(order):
    rnd = random.Random(7)
    for _ in range(200):
        angles = [rnd.uniform(-math.pi, math.pi), rnd.uniform(-1.4, 1.4), rnd.uniform(-math.pi, math.pi)]
        R = km.euler_matrix(angles, order)
        back = km.matrix_euler(R, order)
        assert _close(km.euler_matrix(back, order), R)


@pytest.mark.parametrize("order", ORDERS)
def test_euler_order_applies_the_first_axis_first(order):
    """Maya's order "xyz" turns about x first, then y, then z, each about the parent's axes."""
    a = [0.3, -0.2, 0.5]
    by_axis = dict(zip("xyz", a))
    R = km.identity()
    for ax in order:
        R = km.mul(km.axis_matrix(ax, by_axis[ax]), R)
    assert _close(km.euler_matrix(a, order), R)


def test_euler_at_gimbal_lock_still_gives_the_same_matrix():
    R = km.euler_matrix([0.4, math.pi / 2, -0.3], "xyz")
    assert _close(km.euler_matrix(km.matrix_euler(R, "xyz"), "xyz"), R)


def test_near_angles_choose_the_closest_equivalent():
    """Euler angles for a key stay near the key before, so a curve does not jump by 360 degrees."""
    R = km.euler_matrix([3.1, 0.2, 0.0], "xyz")
    back = km.matrix_euler(R, "xyz", near=[-3.15, 0.2, 0.0])
    assert abs(back[0] - (3.1 - 2 * math.pi)) < 1e-9


def test_mirror_turns_kei_world_into_a_right_handed_world():
    """Kei's world has x on the character's right; Maya's right-handed world puts the right on -x."""
    assert km.mirror_point((0.1, 0.9, 0.2)) == (-0.1, 0.9, 0.2)
    F = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert _close(km.mirror_frame(F), km.identity())
    R = km.mirror_frame(((0, 0, -1), (0, 1, 0), (1, 0, 0)))    # X, Y, Z columns of a 90 deg turn about y
    assert abs(km.det(R) - 1) < 1e-12


def test_local_transform_of_a_child_in_its_parent():
    P = km.euler_matrix([0, 0, math.pi / 2], "xyz")
    C = km.mul(P, km.euler_matrix([0.2, 0, 0], "xyz"))
    t, L = km.local(P, (1, 2, 3), C, (1, 3, 3))
    assert _close(L, km.euler_matrix([0.2, 0, 0], "xyz"))
    assert all(abs(x - y) < 1e-12 for x, y in zip(t, (1, 0, 0)))
