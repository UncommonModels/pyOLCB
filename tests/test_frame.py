import pytest

from pyolcb.frame import (Frame, addressed_frames, datagram_frames, parse_id, format_node_id,
                          format_event_id, VAR_AMD, ADDRESSED_ONLY, ADDRESSED_FIRST, ADDRESSED_MIDDLE,
                          ADDRESSED_LAST)
from pyolcb import message_types, Message, Address


def test_message_frame_fields():
    f = Frame(0x19490ABC)
    assert not f.is_control
    assert f.mti == 0x490
    assert f.source_alias == 0xABC
    assert not f.is_addressed
    assert f.destination_alias is None


def test_addressed_frame_fields():
    f = Frame(0x19828123, bytes([0x04, 0x56]))
    assert f.is_addressed
    assert f.destination_alias == 0x456
    assert f.framing == ADDRESSED_ONLY
    assert f.payload == b""


def test_control_frames():
    cid = Frame.cid(7, 0x020157000099, 0x123)
    assert cid.is_control and cid.is_cid
    assert cid.arbitration_id == 0x17020123
    assert Frame.cid(4, 0x020157000099, 0x123).arbitration_id == 0x14099123
    amd = Frame.control(VAR_AMD, 0x123, bytes(6))
    assert amd.arbitration_id == 0x10701123
    assert amd.is_control and not amd.is_cid
    assert amd.mti == 0


def test_datagram_frame_fields():
    f = Frame.datagram(2, 0x456, 0x123, b"\x20\x80")
    assert f.arbitration_id == 0x1A456123
    assert f.is_datagram
    assert f.destination_alias == 0x456
    assert f.mti == 0


def test_addressed_frames_split():
    frames = addressed_frames(0xA08, 0x123, 0x456, bytes(range(14)))
    assert [f.framing for f in frames] == [ADDRESSED_FIRST, ADDRESSED_MIDDLE, ADDRESSED_LAST]
    assert all(f.destination_alias == 0x456 for f in frames)
    assert b"".join(f.payload for f in frames) == bytes(range(14))
    single = addressed_frames(0x828, 0x123, 0x456)
    assert len(single) == 1 and single[0].data == bytes([0x04, 0x56])


def test_datagram_frames_split():
    frames = datagram_frames(0x123, 0x456, bytes(range(20)))
    assert [f.frame_type for f in frames] == [3, 4, 5]
    assert b"".join(f.data for f in frames) == bytes(range(20))
    assert datagram_frames(0x123, 0x456, b"\x20\x80")[0].frame_type == 2
    with pytest.raises(ValueError):
        datagram_frames(1, 2, bytes(73))


def test_ids():
    assert parse_id("02.01.57.00.00.99", 6) == 0x020157000099
    assert parse_id("020157000099", 6) == 0x020157000099
    assert parse_id("02:01:57:00:00:99:00:01", 8) == 0x0201570000990001
    assert format_node_id(0x020157000099) == "02.01.57.00.00.99"
    assert format_event_id(0x0201570000990001) == "02.01.57.00.00.99.00.01"
    with pytest.raises(ValueError):
        parse_id("hello", 8)
    with pytest.raises(ValueError):
        parse_id("01.02.03.04.05.06.07", 6)


def test_frame_matches_can_message_interface():
    f = Frame(0x195B4123, bytes(range(8)))
    m = Message.from_can_message(f)
    assert m.message_type == message_types.Producer_Consumer_Event_Report
    assert m.source == Address(alias=0x123)


def test_message_from_addressed_frame_sets_destination():
    m = Message.from_can_message(Frame(0x19828123, bytes([0x04, 0x56])))
    assert m.destination.get_alias() == 0x456


def test_mti_names():
    assert message_types.name_of(0x490) == "Verify Node ID Number Global"
    assert message_types.name_of(message_types.Datagram_Received_OK) == "Datagram Received OK"
    assert message_types.is_known_mti(message_types.Datagram)
    assert not message_types.is_known_mti(0x0123)
    assert message_types.name_of(0x123) == "MTI 0x123"


def test_datagram_message_header_carries_destination_only():
    src = Address("05.01.01.01.8C.00", 0x123)
    dst = Address("05.01.01.01.8C.01", 0x456)
    assert message_types.Datagram.get_can_header(src, dst) == 0x1A456123
