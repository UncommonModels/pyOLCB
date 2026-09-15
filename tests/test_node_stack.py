"""Node behaviour on an in-memory bus: alias allocation, discovery, SNIP, PIP and events."""

import time

import pytest

import pyolcb
from pyolcb import protocols
from pyolcb.frame import Frame, VAR_AMD, VAR_AME, VAR_RID
from pyolcb.exceptions import InteractionRejected
from tests.loopback import LoopbackBus, LoopbackInterface


def make_node(bus, node_id, **kwargs):
    return pyolcb.Node(pyolcb.Address(node_id), LoopbackInterface(bus), **kwargs)


def test_alias_allocation_sequence():
    bus = LoopbackBus()
    iface = LoopbackInterface(bus)
    node = pyolcb.Node(pyolcb.Address("02.01.57.FF.00.01"), iface)
    assert node.permitted
    alias = node.get_alias()
    kinds = [f.arbitration_id >> 12 for f in iface.sent[:7]]
    assert [k >> 12 for k in kinds[:4]] == [0x17, 0x16, 0x15, 0x14]
    assert iface.sent[4] == Frame.control(VAR_RID, alias)
    assert iface.sent[5] == Frame.control(VAR_AMD, alias, bytes.fromhex("020157FF0001"))
    assert iface.sent[6] == Frame.message(0x100, alias, bytes.fromhex("020157FF0001"))


def test_alias_conflict_during_claim_picks_another():
    bus = LoopbackBus()
    blocker = LoopbackInterface(bus)
    iface = LoopbackInterface(bus)

    class Clash:
        """Answers every CID with a frame from the alias being claimed."""
        def deliver(self, frame):
            if frame.is_cid and not getattr(self, "done", False):
                self.done = True
                blocker.send(Frame.control(VAR_RID, frame.source_alias))
    bus.attach(Clash())
    node = pyolcb.Node(pyolcb.Address("02.01.57.FF.00.03"), iface)
    cids = [f.source_alias for f in iface.sent if f.is_cid]
    assert len(set(cids)) == 2, "should have tried a second alias"
    assert node.get_alias() == cids[-1]


def test_discovery_snip_pip_between_nodes():
    bus = LoopbackBus()
    info = pyolcb.SimpleNodeInfo("Uncommon Models", "Widget", "1", "2.0", "Yard", "East end")
    remote = make_node(bus, "05.01.01.01.8C.01", snip=info,
                       protocols=protocols.Datagram_Protocol + protocols.Simple_Node_Information_Protocol)
    local = make_node(bus, "05.01.01.01.8C.00")
    local.send_global(0x490)
    bus.drain()
    time.sleep(0.05)
    assert local.node_id_of(remote.get_alias()) == 0x050101018C01
    assert local.simple_node_info(0x050101018C01) == info
    pip = local.protocol_support_inquiry(0x050101018C01)
    assert protocols.Datagram_Protocol in pip
    assert "SNIP" in pip.names()


def test_resolve_alias_with_ame():
    bus = LoopbackBus()
    remote = make_node(bus, "05.01.01.01.8C.01")
    local = make_node(bus, "05.01.01.01.8C.00")
    local.aliases.clear()
    assert local.resolve_alias(0x050101018C01) == remote.get_alias()


def test_unknown_request_is_rejected():
    bus = LoopbackBus()
    remote = make_node(bus, "05.01.01.01.8C.01")   # no SNIP configured
    local = make_node(bus, "05.01.01.01.8C.00")
    with pytest.raises(InteractionRejected) as e:
        local.simple_node_info(remote.address)
    assert e.value.code == 0x1043


def test_identify_events_and_produce():
    bus = LoopbackBus()
    remote = make_node(bus, "05.01.01.01.8C.01")
    remote.add_produced_event(0x0501010101010001, pyolcb.EventState.VALID)
    remote.add_consumed_event(0x0501010101010002)
    seen = []
    local = make_node(bus, "05.01.01.01.8C.00")
    local.add_frame_listener(lambda f, out: seen.append(f) if not out else None)
    local.identify_events(remote.get_alias())
    bus.drain()
    time.sleep(0.05)
    mtis = {(f.mti, int.from_bytes(f.data, "big")) for f in seen}
    assert (0x544, 0x0501010101010001) in mtis
    assert (0x4C7, 0x0501010101010002) in mtis

    got = []
    remote.add_consumer(pyolcb.Event(0x0501010101010002), lambda m: got.append(m.data))
    local.produce_event(0x0501010101010002)
    bus.drain()
    time.sleep(0.05)
    assert got == [bytes.fromhex("0501010101010002")]


def test_local_consumer_sees_own_production():
    bus = LoopbackBus()
    node = make_node(bus, "05.01.01.01.8C.00")
    got = []
    node.add_consumer(1, lambda m: got.append(m.data))
    node.produce(1)
    assert got == [bytes.fromhex("050101018C000001")]


def test_ame_answered():
    bus = LoopbackBus()
    node = make_node(bus, "05.01.01.01.8C.00")
    probe = LoopbackInterface(bus)
    seen = []
    probe.register_listener(seen.append)
    probe.send(Frame.control(VAR_AME, 0x001))
    bus.drain()
    time.sleep(0.05)
    assert Frame.control(VAR_AMD, node.get_alias(), bytes.fromhex("050101018C00")) in seen
