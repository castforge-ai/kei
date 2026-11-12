"""The binary FBX writer: node records, typed properties, arrays (compressed above a size), header and footer."""
import struct

import pytest

from fbxread import FOOTER_END, read_fbx
from kei.fbx import COMPRESS_ABOVE, FOOTER_ID, VERSION, Node, P, encode_node, fbx_file


def test_the_header_names_the_format_and_version():
    blob = fbx_file([Node("A", [1])])
    assert blob[:21] == b"Kaydara FBX Binary  \x00"
    assert blob[21:23] == b"\x1a\x00"
    assert struct.unpack_from("<I", blob, 23)[0] == VERSION == 7400


def test_scalar_properties_round_trip_with_their_types():
    props = [P("Y", -3), P("C", True), P("I", -70000), P("F", 0.5), P("D", 1.25), P("L", 2**40), "text", b"\x01\x02",
             7, 2.5, False]
    _, nodes = read_fbx(fbx_file([Node("Values", props)]))
    n = nodes[0]
    assert n.name == "Values"
    assert n.types == "YCIFDLSRIDC"
    assert n.props == [-3, True, -70000, 0.5, 1.25, 2**40, "text", b"\x01\x02", 7, 2.5, False]


def test_a_name_with_the_class_separator_is_kept_byte_for_byte():
    _, nodes = read_fbx(fbx_file([Node("Model", [P("L", 5), "hand_r\x00\x01Model", "LimbNode"])]))
    assert nodes[0].props[1] == "hand_r\x00\x01Model"


def test_small_arrays_are_plain_and_large_ones_compressed():
    small = list(range(4))
    large = [float(k % 7) for k in range(COMPRESS_ABOVE)]
    blob = encode_node(Node("A", [P("i", small), P("d", large), P("f", [0.25] * 3), P("l", [1, -2]),
                                  P("b", [True, False])]), 0)
    pos = 13 + 1
    assert blob[pos:pos + 1] == b"i"
    assert struct.unpack_from("<III", blob, pos + 1) == (4, 0, 16)
    pos += 1 + 12 + 16
    assert blob[pos:pos + 1] == b"d"
    n, enc, clen = struct.unpack_from("<III", blob, pos + 1)
    assert (n, enc) == (COMPRESS_ABOVE, 1) and clen < 8 * COMPRESS_ABOVE
    _, nodes = read_fbx(fbx_file([Node("A", [P("i", small), P("d", large), P("f", [0.25] * 3), P("l", [1, -2]),
                                             P("b", [True, False])])]))
    assert nodes[0].props == [small, large, [0.25] * 3, [1, -2], [True, False]]
    assert nodes[0].types == "idflb"


def test_an_empty_array_is_written_plain():
    _, nodes = read_fbx(fbx_file([Node("A", [P("i", [])])]))
    assert nodes[0].props == [[]]


def test_children_nest_and_every_end_offset_is_right():
    tree = Node("Objects", [], [Node("Model", [P("L", 1), "a\x00\x01Model", "LimbNode"],
                                     [Node("Version", [232]), Node("Properties70", [], [
                                         Node("P", ["Lcl Translation", "Lcl Translation", "", "A", 1.0, 2.0, 3.0])])]),
                                Node("Empty", [])])
    _, nodes = read_fbx(fbx_file([Node("Header", ["x"]), tree]))
    assert [n.name for n in nodes] == ["Header", "Objects"]
    model = nodes[1].find("Model")
    assert model.find("Version").props == [232]
    assert model.find("Properties70").find("P").props[4:] == [1.0, 2.0, 3.0]
    assert nodes[1].find("Empty").props == []


def test_a_node_record_starts_at_the_offset_it_is_given():
    """End offsets are absolute file positions, so a node encoded at 27 ends at 27 + its length."""
    blob = encode_node(Node("A", [1], [Node("B", [2])]), 27)
    end = struct.unpack_from("<I", blob, 0)[0]
    assert end == 27 + len(blob)
    assert blob[-13:] == b"\x00" * 13          # the null record closing the child list


def test_the_footer_is_aligned_and_ends_with_the_magic():
    for payload in (["a"], ["ab" * 9], [b"\x00" * 3]):
        blob = fbx_file([Node("N", payload)])
        assert blob.endswith(FOOTER_END)
        assert len(blob) % 16 == 0
        assert FOOTER_ID in blob
        read_fbx(blob)


def test_a_reader_rejects_a_damaged_length():
    blob = bytearray(fbx_file([Node("A", [1], [Node("B", [2])])]))
    blob[27] ^= 0x01                            # the first node's end offset
    with pytest.raises(ValueError):
        read_fbx(bytes(blob))


def test_an_unknown_type_code_is_refused():
    with pytest.raises(ValueError):
        P("Q", 1)
    with pytest.raises(TypeError):
        fbx_file([Node("A", [object()])])


def test_a_node_can_carry_an_empty_child_list():
    """Some object records carry an empty child list, closed by a null record (Unreal's FBX reader ignored every
    animation curve until the AnimationLayer record had one)."""
    blob = encode_node(Node("AnimationLayer", [P("L", 1), "BaseLayer\x00\x01AnimLayer", ""], listed=True), 0)
    assert blob.endswith(b"\x00" * 13)
    _, nodes = read_fbx(fbx_file([Node("A", [1], listed=True), Node("B", [1])]))
    assert nodes[0].listed and nodes[0].children == []
    assert not nodes[1].listed
