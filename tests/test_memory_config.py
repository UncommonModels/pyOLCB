import pytest

import pyolcb
from pyolcb import memory_config as mc
from pyolcb.exceptions import MemoryConfigError, DatagramRejected, ReplyTimeout
from tests.loopback import LoopbackBus, LoopbackInterface, FakeConfigNode

REMOTE_ID = 0x050101018C99


def test_request_encoding():
    assert mc.read_request(0xFF, 0x40, 64) == bytes([0x20, 0x40, 0, 0, 0, 0x40, 0xFF, 64])
    assert mc.write_request(0xFB, 1, b"ab") == bytes([0x20, 0x00, 0, 0, 0, 1, 0xFB]) + b"ab"
    assert mc.factory_reset_request(REMOTE_ID) == bytes([0x20, 0xAA]) + REMOTE_ID.to_bytes(6, "big")
    with pytest.raises(ValueError):
        mc.read_request(0xFF, 0, 65)


def test_reply_matching():
    request = mc.read_request(0xFD, 0x80, 8)
    assert mc.is_reply_to(request, bytes([0x20, 0x50, 0, 0, 0, 0x80, 0xFD]) + bytes(8))
    assert mc.is_reply_to(request, bytes([0x20, 0x51, 0, 0, 0, 0x80]) + bytes(8))  # short form
    assert not mc.is_reply_to(request, bytes([0x20, 0x50, 0, 0, 0, 0x81, 0xFD]) + bytes(8))
    assert mc.is_reply_to(mc.space_info_request(0xFF), bytes([0x20, 0x87, 0xFF, 0, 0, 1, 0, 1]))
    assert not mc.is_reply_to(mc.space_info_request(0xFF), bytes([0x20, 0x87, 0xFD, 0, 0, 1, 0, 1]))


def test_parse_replies():
    space, address, data = mc.parse_read_reply(bytes([0x20, 0x53, 0, 0, 0, 0x10]) + b"xyz")
    assert (space, address, data) == (0xFF, 0x10, b"xyz")
    with pytest.raises(MemoryConfigError) as e:
        mc.parse_read_reply(bytes([0x20, 0x58, 0, 0, 0, 0, 0x10, 0x10, 0x81]))
    assert e.value.code == 0x1081
    info = mc.parse_space_info_reply(bytes([0x20, 0x87, 0xFF, 0, 0, 2, 0x7F, 0x01]))
    assert info.present and info.read_only and info.size == 0x280
    info = mc.parse_space_info_reply(bytes([0x20, 0x87, 0xFD, 0, 0, 0, 0xFF, 0x02, 0, 0, 0, 0x80]))
    assert info.lowest == 0x80 and not info.read_only and info.size == 0x80
    assert not mc.parse_space_info_reply(bytes([0x20, 0x86, 0xF0])).present
    options = mc.parse_options_reply(bytes([0x20, 0x82, 0x6E, 0x00, 0xE2, 0xFF, 0xFB]))
    assert options["unaligned_reads"] and options["highest_space"] == 0xFF


def test_describe():
    assert mc.describe(mc.read_request(0xFF, 0x40, 64)) == "Read space 0xFF CDI @ 0x40, 64 bytes"
    assert mc.describe(bytes([0x20, 0xA8])) == "Update complete"
    assert "Write space 0xFB" in mc.describe(mc.write_request(0xFB, 1, b"A"))
    assert mc.describe(b"\x30\x01") == "datagram 30 01"


@pytest.fixture
def setup():
    bus = LoopbackBus()
    cdi = b"<cdi><segment space='253'><int size='2'><name>X</name></int></segment></cdi>\x00"
    spaces = {0xFF: bytearray(cdi), 0xFD: bytearray(200), 0xFB: bytearray(128)}
    remote = FakeConfigNode(bus, REMOTE_ID, 0x555, spaces)
    node = pyolcb.Node(pyolcb.Address("05.01.01.01.8C.00"), LoopbackInterface(bus))
    remote.announce()
    bus.drain()
    return bus, remote, node


def test_read_write_roundtrip(setup):
    bus, remote, node = setup
    client = pyolcb.MemoryConfiguration(node, REMOTE_ID, timeout=1)
    assert client.read_cdi().startswith("<cdi>")
    data = bytes(range(150))
    client.write(0xFD, 10, data)
    assert bytes(remote.spaces[0xFD][10:160]) == data
    # 150 bytes take three 64-byte writes and three reads
    assert client.read(0xFD, 10, 150) == data
    client.update_complete()
    assert remote.commits == 1
    assert client.options()["highest_space"] == 0xFF


def test_read_stops_at_end_of_space(setup):
    _, remote, node = setup
    client = pyolcb.MemoryConfiguration(node, REMOTE_ID, timeout=1)
    assert len(client.read(0xFB, 100, 64)) == 28


def test_errors(setup):
    _, remote, node = setup
    client = pyolcb.MemoryConfiguration(node, REMOTE_ID, timeout=1)
    with pytest.raises(MemoryConfigError) as e:
        client.read(0x10, 0, 4)
    assert e.value.code == 0x1081
    with pytest.raises(DatagramRejected) as e:
        client.write(0xFF, 0, b"x")
    assert e.value.code == 0x1083
    # A temporary rejection is retried transparently.
    remote.reject_next = 0x2020
    assert client.read(0xFB, 0, 2) == b"\x00\x00"
    remote.drop_ack = True
    with pytest.raises(ReplyTimeout):
        pyolcb.MemoryConfiguration(node, REMOTE_ID, timeout=0.3).read(0xFB, 0, 2)
