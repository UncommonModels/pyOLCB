import socket
import threading
import time

import pytest

from pyolcb.frame import Frame
from pyolcb.gridconnect import (format_frame, parse_frame, GridConnectParser, GridConnectTcpInterface)


def test_format_and_parse():
    f = Frame(0x19170ABC, bytes.fromhex("020157000099"))
    text = format_frame(f)
    assert text == ":X19170ABCN020157000099;"
    assert parse_frame(text) == f
    assert parse_frame(":X19490ABCN;") == Frame(0x19490ABC)


def test_parse_rejects_invalid():
    assert parse_frame(":S123N;") is None           # standard frame
    assert parse_frame(":X19490ABCN0;") is None     # odd number of hex digits
    assert parse_frame(":X19490ABCN" + "00" * 9 + ";") is None
    assert parse_frame(":X3FFFFFFFN;") is None      # more than 29 bits
    assert parse_frame("X19490ABCN;") is None


def test_parser_handles_pieces_junk_and_case():
    p = GridConnectParser()
    assert p.feed(b"console says hi\r\n:X1949") == []
    frames = p.feed(b"0abcN;\r\n:x19170abcn020157000099;junk")
    assert frames == [Frame(0x19490ABC), Frame(0x19170ABC, bytes.fromhex("020157000099"))]


def test_parser_colon_restarts_and_overlong_is_dropped():
    p = GridConnectParser()
    assert p.feed(":X1949:X19490ABCN;") == [Frame(0x19490ABC)]
    assert p.feed(":X19490ABCN" + "0" * 40 + ";:X19490ABDN;") == [Frame(0x19490ABD)]


class _Server:
    """A one-connection-at-a-time GridConnect TCP peer."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]

    def accept(self):
        self.listener.settimeout(5)
        conn, _ = self.listener.accept()
        conn.settimeout(2)
        return conn


def test_tcp_interface_roundtrip_and_reconnect():
    server = _Server()
    received = []
    states = []
    iface = GridConnectTcpInterface("127.0.0.1", server.port, retry_interval=0.1)
    iface.register_listener(received.append)
    iface.register_state_listener(states.append)
    try:
        conn = server.accept()
        assert iface.wait_connected(2)
        conn.sendall(b":X19490ABCN;\r\n")
        assert iface.send(Frame(0x19170123, bytes(6)))
        data = conn.recv(100)
        assert data.startswith(b":X19170123N000000000000;")
        deadline = time.time() + 2
        while not received and time.time() < deadline:
            time.sleep(0.01)
        assert received == [Frame(0x19490ABC)]

        conn.close()   # drop the link: the interface must come back by itself
        conn = server.accept()
        deadline = time.time() + 2
        while states.count(True) < 2 and time.time() < deadline:
            time.sleep(0.01)
        assert states[:3] == [True, False, True]
        assert iface.send(Frame(0x19490123))
        assert conn.recv(100).startswith(b":X19490123N;")
        conn.close()
    finally:
        iface.close()
        server.listener.close()


def test_serial_interface_over_a_pty():
    """GridConnect serial, through a pseudo-terminal standing in for a USB port."""
    pytest.importorskip("serial")
    import os
    import select
    from pyolcb.gridconnect import GridConnectSerialInterface
    master, slave = os.openpty()
    received = []
    iface = GridConnectSerialInterface(os.ttyname(slave), retry_interval=0.1)
    iface.register_listener(received.append)
    try:
        assert iface.wait_connected(3), iface.last_error
        # A FemtoLCC console prints notices on the same line as the frames.
        os.write(master, b"USB: GridConnect host found\r\n:X19490ABCN;\r\n")
        deadline = time.time() + 3
        while not received and time.time() < deadline:
            time.sleep(0.01)
        assert received == [Frame(0x19490ABC)]
        assert iface.send(Frame(0x19170123, bytes(6)))
        data = b""
        while b";" not in data and select.select([master], [], [], 3)[0]:
            data += os.read(master, 100)
        assert data.startswith(b":X19170123N000000000000;")
    finally:
        iface.close()
        os.close(master)
        os.close(slave)


def test_browse_mdns_finds_an_advertised_hub():
    zeroconf = pytest.importorskip("zeroconf")
    from pyolcb.gridconnect import browse_mdns, MDNS_SERVICE
    zc = zeroconf.Zeroconf()
    info = zeroconf.ServiceInfo(MDNS_SERVICE, "pytest hub." + MDNS_SERVICE,
                                addresses=[socket.inet_aton("127.0.0.1")], port=12099,
                                server="pytest-hub.local.")
    zc.register_service(info)
    try:
        found = browse_mdns(2.0)
    finally:
        zc.unregister_service(info)
        zc.close()
    assert {"name": "pytest hub", "port": 12099} in [{"name": s["name"], "port": s["port"]} for s in found]


def test_send_while_disconnected_returns_false():
    iface = GridConnectTcpInterface("127.0.0.1", 1, start=False)
    assert not iface.connected
    assert iface.send(Frame(0x19490123)) is False
