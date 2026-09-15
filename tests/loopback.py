"""
Test helpers: an in-memory bus and a scripted remote node, so node and
Memory Configuration behaviour can be tested without CAN hardware or vcan.
"""

import queue
import threading

from pyolcb.interface import Interface, to_frame
from pyolcb.frame import Frame, addressed_frames, datagram_frames, VAR_AME, VAR_AMD, VAR_RID


class LoopbackBus:
    """Frames sent by one attached party are delivered, in order, to all the others."""

    def __init__(self):
        self.parties = []
        self.log = []
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def attach(self, party):
        self.parties.append(party)

    def transmit(self, sender, frame):
        self._queue.put((sender, frame))

    def drain(self, timeout=2.0):
        """Wait until every queued frame has been delivered."""
        done = threading.Event()
        self._queue.put((None, done))
        return done.wait(timeout)

    def _run(self):
        while True:
            sender, frame = self._queue.get()
            if sender is None:
                frame.set()
                continue
            self.log.append(frame)
            for party in list(self.parties):
                if party is not sender:
                    party.deliver(frame)


class LoopbackInterface(Interface):
    """An :class:`Interface` on a :class:`LoopbackBus`."""

    def __init__(self, bus: LoopbackBus):
        super().__init__()
        self.bus = bus
        self.sent = []
        self._listeners = []
        bus.attach(self)

    @property
    def connected(self) -> bool:
        return True

    def send(self, message):
        frame = to_frame(message)
        self.sent.append(frame)
        self.bus.transmit(self, frame)
        return True

    def register_listener(self, function):
        self._listeners.append(function)

    def deliver(self, frame):
        for listener in list(self._listeners):
            listener(frame)


class FakeConfigNode:
    """
    A remote node scripted at frame level: answers Verify Node ID, AME and the
    Memory Configuration commands against an in-memory dictionary of spaces.
    """

    def __init__(self, bus: LoopbackBus, node_id: int, alias: int, spaces: dict[int, bytearray],
                 read_only=(0xFF,), reply_pending=True):
        self.bus = bus
        self.node_id = node_id
        self.alias = alias
        self.spaces = spaces
        self.read_only = set(read_only)
        self.reply_pending = reply_pending
        self.received = []
        self.reject_next = None   # error code to reject the next datagram with
        self.drop_ack = False
        self.commits = 0
        self.resets = 0
        self._rx = {}
        bus.attach(self)

    def send(self, frame):
        self.bus.transmit(self, frame)

    def announce(self):
        self.send(Frame.control(VAR_RID, self.alias))
        self.send(Frame.control(VAR_AMD, self.alias, self.node_id.to_bytes(6, "big")))
        self.send(Frame.message(0x100, self.alias, self.node_id.to_bytes(6, "big")))

    def deliver(self, frame: Frame):
        if frame.is_control and frame.variable_field == VAR_AME:
            if not frame.data or int.from_bytes(frame.data[:6], "big") == self.node_id:
                self.send(Frame.control(VAR_AMD, self.alias, self.node_id.to_bytes(6, "big")))
            return
        if frame.mti == 0x490 and (not frame.data or int.from_bytes(frame.data[:6], "big") == self.node_id):
            self.send(Frame.message(0x170, self.alias, self.node_id.to_bytes(6, "big")))
            return
        if not frame.is_datagram or frame.destination_alias != self.alias:
            return
        src = frame.source_alias
        if frame.frame_type == 2:
            self._datagram(src, frame.data)
        elif frame.frame_type == 3:
            self._rx[src] = bytearray(frame.data)
        else:
            self._rx[src].extend(frame.data)
            if frame.frame_type == 5:
                self._datagram(src, bytes(self._rx.pop(src)))

    def _ack(self, dest, flags):
        for f in addressed_frames(0xA28, self.alias, dest, bytes([flags])):
            self.send(f)

    def _reply(self, dest, data):
        for f in datagram_frames(self.alias, dest, data):
            self.send(f)

    def _datagram(self, src, data):
        data = bytes(data)
        self.received.append(data)
        if self.reject_next is not None:
            code, self.reject_next = self.reject_next, None
            for f in addressed_frames(0xA48, self.alias, src, code.to_bytes(2, "big")):
                self.send(f)
            return
        if self.drop_ack:
            return
        command = data[1]
        if command & 0xFC == 0x40:
            space = data[6]
            address = int.from_bytes(data[2:6], "big")
            count = data[7]
            self._ack(src, 0x80 if self.reply_pending else 0)
            memory = self.spaces.get(space)
            if memory is None or address >= len(memory):
                self._reply(src, bytes([0x20, 0x58]) + data[2:7] + (0x1081 if memory is None else 0x1082)
                            .to_bytes(2, "big"))
                return
            self._reply(src, bytes([0x20, 0x50]) + data[2:7] + bytes(memory[address:address + count]))
        elif command & 0xFC == 0x00:
            space = data[6]
            address = int.from_bytes(data[2:6], "big")
            if space in self.read_only or space not in self.spaces:
                for f in addressed_frames(0xA48, self.alias, src, (0x1083).to_bytes(2, "big")):
                    self.send(f)
                return
            payload = data[7:]
            self.spaces[space][address:address + len(payload)] = payload
            self._ack(src, 0)
        elif command == 0x84:
            space = data[2]
            self._ack(src, 0x80)
            memory = self.spaces.get(space)
            if memory is None:
                self._reply(src, bytes([0x20, 0x86, space]))
            else:
                self._reply(src, bytes([0x20, 0x87, space]) + (len(memory) - 1).to_bytes(4, "big")
                            + bytes([1 if space in self.read_only else 0]))
        elif command == 0x80:
            self._ack(src, 0x80)
            self._reply(src, bytes([0x20, 0x82, 0x6E, 0x00, 0xE2, 0xFF, 0xFB]))
        elif command == 0xA8:
            self.commits += 1
            self._ack(src, 0)
        elif command == 0xA9:
            self.resets += 1
            self._ack(src, 0)
        else:
            for f in addressed_frames(0xA48, self.alias, src, (0x1041).to_bytes(2, "big")):
                self.send(f)
