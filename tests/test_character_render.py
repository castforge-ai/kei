"""The characters as meshes and drawings: rigid parts, closed outward surfaces, the two silhouettes, the glow."""
import json
import math

import pytest

from kei import hands
from kei.characters import CHARACTERS, load_character, rest_pose
from kei.characters.mesh import character_mesh, pose_mesh, shape_mesh, widths
from kei.render import (CHARACTER_VIEWS, draw_character_views, draw_silhouette, render_shot)
from kei.rig import ALL_BONES, PARENTS, skeleton
from test_sheet import decode


@pytest.fixture(scope="module", params=CHARACTERS)
def ch(request):
    return load_character(request.param)


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_every_shape_mesh_faces_outward_and_is_closed(ch):
    for s in ch.shapes:
        v, n, t = shape_mesh(s)
        assert t and len(v) == len(n)
        key = [tuple(round(x, 9) for x in p) for p in v]
        edges = set()
        for tri in t:
            a, b, c = (v[i] for i in tri)
            face = cross(sub(b, a), sub(c, a))
            if dot(face, face) < 1e-24:
                continue
            avg = tuple(sum(n[i][k] for i in tri) for k in range(3))
            assert dot(face, avg) > 0, (s.bone, s.kind)
            for i, j in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                edges.add((key[i], key[j]))
        # closed: every directed edge has its reverse (by position: the C's flat sides keep their own corners)
        assert all((j, i) in edges for i, j in edges), (s.bone, s.kind)


def test_a_part_moves_rigidly_with_its_bone(ch):
    """Every bone bent 90 deg: each vertex keeps its place in its bone's frame (no part floats off its joint)."""
    pose = {**rest_pose(ch), "spine": [1.0, 0.4, 0.3], "neck": [0.6, 0, 0], "armL": [1.57, 0.3, 0.5],
            "armR": [0.4, 1.57, 0], "elbowL": [1.57, 0.5], "elbowR": [1.57, 0], "handL": [1.0, 0.3],
            "footL": [-0.15, 0.4, 0.35, 0.3, 0], "kneeR": 0.4, "rollR": [1.57, 0, 0.6], "toeL": 0.6,
            "fingersL": hands.preset("fist"), "fingersR": hands.preset("ok"), "head": [0.5, 0.3, 1.0]}
    mesh = character_mesh(ch)
    posed = pose_mesh(ch, pose)
    B = skeleton(pose, ch.proportions)
    for part, world in zip(mesh, posed):
        X, Y, Z = B[part.bone].frame
        h = B[part.bone].head
        for lv, wv in zip(part.verts, world.verts):
            back = tuple(dot(sub(wv, h), e) for e in (X, Y, Z))
            assert math.dist(back, lv) < 1e-9, part.bone


def test_each_joint_shape_stays_on_its_joint_in_a_bend(ch):
    pose = {**rest_pose(ch), "armR": [1.57, 0, 0], "elbowR": [1.57, 0], "spine": [1.57, 0, 0]}
    B = skeleton(pose, ch.proportions)
    for part, world in zip(character_mesh(ch), pose_mesh(ch, pose)):
        if part.material == "joint":
            centre = tuple(sum(v[k] for v in world.verts) / len(world.verts) for k in range(3))
            assert math.dist(centre, B[part.bone].head) < 0.003, part.bone


def test_the_shoulder_to_hip_ratios_tell_the_two_apart():
    kei, keira = widths(load_character("kei")), widths(load_character("keira"))
    assert kei["ratio"] > 1.2
    assert keira["ratio"] < 1.0
    assert abs(kei["shoulder"] - 0.47) < 0.01 and abs(keira["shoulder"] - 0.33) < 0.01
    assert 0.33 < kei["hip"] < 0.38 and 0.35 < keira["hip"] < 0.40


def black(px):
    return px[0] < 128


def test_the_black_silhouettes_differ_in_the_torso_band():
    size = 240
    a, b = (decode(draw_silhouette(load_character(n), size=size)) for n in CHARACTERS)
    w, h, pa = a
    _, _, pb = b
    rows = [y for y in range(h) if any(black(pa(x, y)) for x in range(w))]
    top, bottom = rows[0], rows[-1]
    # the torso band: from the shoulders (about 0.2 of the height down) to the hips (about 0.48 down)
    band = range(top + int(0.2 * (bottom - top)), top + int(0.48 * (bottom - top)))
    differ = union = 0
    for y in band:
        for x in range(w):
            p, q = black(pa(x, y)), black(pb(x, y))
            union += p or q
            differ += p != q
    assert union and differ / union > 0.15


def colours(png):
    w, h, px = decode(png)
    return [px(x, y) for y in range(h) for x in range(w)]


def warm(c):
    """An emission orange: red high, blue low, clearly saturated."""
    return c[0] > 200 and c[0] - c[2] > 110 and c[1] < 200


def test_the_glow_shows_and_off_really_is_off(ch):
    pose = rest_pose(ch)
    lit = colours(draw_character_views(ch, pose, size=300, views=("front",), emission=1.0))
    off = colours(draw_character_views(ch, pose, size=300, views=("front",), emission=0.0))
    assert sum(map(warm, lit)) > 20
    assert sum(map(warm, off)) == 0


def test_the_body_reads_ivory_and_the_joints_charcoal(ch):
    seen = colours(draw_character_views(ch, rest_pose(ch), size=200, views=("front",)))
    ivory = [c for c in seen if abs(c[0] - 0xE9) < 30 and abs(c[1] - 0xDC) < 30 and abs(c[2] - 0xC7) < 30]
    charcoal = [c for c in seen if abs(c[0] - 0x3B) < 25 and abs(c[1] - 0x35) < 25 and abs(c[2] - 0x30) < 25]
    assert len(ivory) > 500 and len(charcoal) > 50


def test_the_left_right_overlay_is_optional(ch):
    plain = set(colours(draw_character_views(ch, rest_pose(ch), size=160, views=("front",))))
    tinted = set(colours(draw_character_views(ch, rest_pose(ch), size=160, views=("front",), overlay=True)))
    blue = lambda c: c[2] > c[0] + 25
    assert not any(map(blue, plain))
    assert any(map(blue, tinted))


def test_the_views_and_their_layout(ch):
    assert CHARACTER_VIEWS == ("front", "side", "back", "three quarter", "top")
    png = draw_character_views(ch, rest_pose(ch), size=120)
    w, h, _ = decode(png)
    assert (w, h) == (5 * 120, 120)


def test_front_and_back_mirror(ch):
    """The back view is the front view seen from behind: the outline is the same, flipped left to right."""
    size = 160
    f = decode(draw_silhouette(ch, size=size, view="front"))
    b = decode(draw_silhouette(ch, size=size, view="back"))
    w, h, pf = f
    _, _, pb = b
    same = total = 0
    for y in range(h):
        for x in range(w):
            p, q = black(pf(x, y)), black(pb(w - 1 - x, y))
            total += p or q
            same += p and q
    assert same / total > 0.95


def test_kei_render_character_draws_the_rest_views_and_the_silhouette(tmp_path, capsys):
    from kei.cli import main
    assert main(["render", "--character", "keira", "--out", str(tmp_path), "--size", "100"]) == 0
    w, h, _ = decode((tmp_path / "keira_rest.png").read_bytes())
    assert (w, h) == (5 * 100, 100)
    assert (tmp_path / "keira_silhouette.png").is_file()
    assert "keira_rest.png" in capsys.readouterr().out


def test_kei_render_an_unknown_character_exits_1(tmp_path, capsys):
    from kei.cli import main
    assert main(["render", "--character", "bob", "--out", str(tmp_path)]) == 1
    assert "bob" in "".join(capsys.readouterr())


def test_kei_render_without_a_shot_or_a_character_exits_1(capsys):
    from kei.cli import main
    assert main(["render"]) == 1
    assert "shot" in "".join(capsys.readouterr())


def test_render_shot_with_a_character(tmp_path):
    shot = {"rig": "v4", "fps": 12, "frames": 2,
            "keys": [{"f": 0, "root": [0, 0.915, 0], "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]},
                     {"f": 2, "root": [0, 0.9, 0.05], "armR": [1.0, 0.2, 0], "fingersR": hands.preset("point"),
                      "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]}]}
    src = tmp_path / "shot.json"
    src.write_text(json.dumps(shot), encoding="utf-8")
    r = render_shot(src, tmp_path / "out", "linear", size=100, character="kei")
    assert len(r["frames"]) == 3
    w, h, _ = decode(r["frames"][0].read_bytes())
    assert (w, h) == (5 * 100, 100)


def _surface_z(parts, x, y):
    """The front-most z of the body at (x, y), seen along the world z axis."""
    best = None
    for p in parts:
        if p.material == "emission":
            continue
        for a, b, c in p.tris:
            (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = p.verts[a], p.verts[b], p.verts[c]
            if max(x0, x1, x2) < x or min(x0, x1, x2) > x or max(y0, y1, y2) < y or min(y0, y1, y2) > y:
                continue
            det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(det) < 1e-15:
                continue
            l0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / det
            l1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / det
            l2 = 1 - l0 - l1
            if min(l0, l1, l2) < 0:
                continue
            z = l0 * z0 + l1 * z1 + l2 * z2
            best = z if best is None else max(best, z)
    return best


def mark_face_points(mark):
    """Points over the C's front face: its corners, and points inside each of its triangles."""
    front = [i for i, n in enumerate(mark.normals) if n[2] > 0.8]
    keep = set(front)
    pts = [mark.verts[i] for i in front]
    for t in mark.tris:
        if set(t) <= keep:
            a, b, c = (mark.verts[i] for i in t)
            for w in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6), (0.5, 0.5, 0),
                      (0, 0.5, 0.5), (0.5, 0, 0.5)):
                pts.append(tuple(w[0] * a[k] + w[1] * b[k] + w[2] * c[k] for k in range(3)))
    return pts


FLUSH = 0.0025       # metres: the most the C's front face stands in front of the chest (one pixel at 700 px)


def test_the_chest_c_is_inset_flush(ch):
    """The C's front face lies on the chest: everywhere in front of it (so it shows), nowhere more than FLUSH."""
    parts = pose_mesh(ch, rest_pose(ch))
    mark = next(p for p in parts if p.material == "emission")
    pts = mark_face_points(mark)
    assert len(pts) >= 30
    for x, y, z in pts:
        s = _surface_z(parts, x, y)
        assert s is not None and 0 < z - s <= FLUSH, (ch.name, round(x, 3), round(y, 3), round(z - s, 4))


def _seg_dist(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    ap = [p[i] - a[i] for i in range(3)]
    ll = sum(x * x for x in ab)
    t = 0.0 if ll < 1e-12 else max(0.0, min(1.0, sum(ab[i] * ap[i] for i in range(3)) / ll))
    return math.dist(p, [a[i] + ab[i] * t for i in range(3)])


# Shapes that sit nearer another bone at rest by design: the pelvis bone has no length, and the pec plate lies over
# the chest's front, nearer the clavicles' line than the spine_05 segment inside it.
BINDING_EXCEPTIONS = {("pelvis", ""), ("spine_05", "pec plate")}


def wrong_bindings(ch) -> list[str]:
    """At rest, every shape lies nearer its own bone's segment than any other bone's (within 1 cm), so a shape bound
    to the wrong bone is named: it would float away from its joint as soon as that bone bends."""
    pose = rest_pose(ch)
    B = skeleton(pose, ch.proportions)
    out = []
    for p in pose_mesh(ch, pose, B):
        note = ch.shapes[p.shape].note
        if any(p.bone == b and note.startswith(n) for b, n in BINDING_EXCEPTIONS):
            continue
        c = [sum(v[k] for v in p.verts) / len(p.verts) for k in range(3)]
        own = _seg_dist(c, B[p.bone].head, B[p.bone].tail)
        best = min(ALL_BONES, key=lambda n: _seg_dist(c, B[n].head, B[n].tail))
        if best != p.bone and own - _seg_dist(c, B[best].head, B[best].tail) > 0.01:
            out.append(f"{p.bone} {note!r} lies nearer {best}")
    return out


def test_every_shape_is_bound_to_the_bone_it_sits_on(ch):
    assert wrong_bindings(ch) == []


def test_a_shape_on_the_wrong_bone_is_caught():
    """The check fails on a real mistake: the toe cap (written in rest space) bound to the calf instead of the ball."""
    from kei.characters import parse_character, raw
    import copy
    data = copy.deepcopy(raw("kei"))
    toe = next(s for s in data["shapes"] if s.get("note", "").startswith("toe cap"))
    toe["bone"] = "calf_{s}"
    found = wrong_bindings(parse_character(data, "kei"))
    assert any("toe cap" in f for f in found)


def _edge_mix(png):
    """The share of the figure's edge pixels (next to the white page) that blend toward white: 0 when the edge is a
    hard outline, well above it when the figure is drawn with anti-aliasing."""
    w, h, px = decode(png)
    white = (250, 250, 250)   # the page
    edge = mixed = 0
    for y in range(20, h - 1):
        for x in range(1, w - 1):
            c = px(x, y)
            if c == white or c[0] < 60:
                continue
            if any(px(x + dx, y + dy) == white for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                edge += 1
                mixed += min(c) > 170
    return mixed / max(1, edge)


def test_the_figure_is_drawn_smooth_with_blended_edges(ch):
    # The author, 2026-11-02: can we have a render that doesn't look pixelated?
    pose = rest_pose(ch)
    assert _edge_mix(draw_character_views(ch, pose, size=200, views=("side",), supersample=1)) < 0.1
    assert _edge_mix(draw_character_views(ch, pose, size=200, views=("side",))) > 0.15


def test_a_smooth_frame_stays_quick_enough_for_a_ten_second_loop(ch):
    import time
    t = time.time()
    draw_character_views(ch, rest_pose(ch), size=360, views=("side",))
    assert time.time() - t < 5
