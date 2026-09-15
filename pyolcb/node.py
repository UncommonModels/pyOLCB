"""
==============
node
==============

"""

import collections
import queue
import threading
import time
from contextlib import contextmanager

from .address import Address
from .interface import Interface, to_frame
from .message import Message
from .event import Event, EventState, IDENTIFIED_MTI
from .datagram import Datagram
from .frame import (Frame, addressed_frames, datagram_frames, VAR_RID, VAR_AMD, VAR_AME, VAR_AMR,
                    ADDRESSED_ONLY, ADDRESSED_FIRST, ADDRESSED_LAST, FRAME_TYPE_DATAGRAM_ONLY,
                    FRAME_TYPE_DATAGRAM_FIRST, FRAME_TYPE_DATAGRAM_FINAL)
from .snip import SimpleNodeInfo
from .exceptions import (NotPermittedError, ReplyTimeout, UnknownNodeError, InteractionRejected,
                         DatagramRejected)
from . import utilities, message_types, protocols, exceptions

# 12-bit MTIs as they appear in CAN headers.
MTI_INITIALIZATION_COMPLETE = 0x100
MTI_INITIALIZATION_COMPLETE_SIMPLE = 0x101
MTI_VERIFY_NODE_ID_ADDRESSED = 0x488
MTI_VERIFY_NODE_ID_GLOBAL = 0x490
MTI_VERIFIED_NODE_ID = 0x170
MTI_VERIFIED_NODE_ID_SIMPLE = 0x171
MTI_OPTIONAL_INTERACTION_REJECTED = 0x068
MTI_TERMINATE_DUE_TO_ERROR = 0x0A8
MTI_PROTOCOL_SUPPORT_INQUIRY = 0x828
MTI_PROTOCOL_SUPPORT_REPLY = 0x668
MTI_CONSUMER_IDENTIFY = 0x8F4
MTI_PRODUCER_IDENTIFY = 0x914
MTI_EVENTS_IDENTIFY_ADDRESSED = 0x968
MTI_EVENTS_IDENTIFY_GLOBAL = 0x970
MTI_EVENT_REPORT = 0x5B4
MTI_SNIP_REQUEST = 0xDE8
MTI_SNIP_REPLY = 0xA08
MTI_DATAGRAM_OK = 0xA28
MTI_DATAGRAM_REJECTED = 0xA48

# Addressed messages that are answers, never requests: they are handed to
# whoever is waiting for them and never rejected.
_REPLY_MTIS = {MTI_PROTOCOL_SUPPORT_REPLY, MTI_SNIP_REPLY, MTI_OPTIONAL_INTERACTION_REJECTED,
               MTI_TERMINATE_DUE_TO_ERROR, MTI_DATAGRAM_OK, MTI_DATAGRAM_REJECTED,
               0x9C8, 0x1E9, 0x1E8, 0x868, 0x888, 0x8A8, 0x549}

ERROR_UNIMPLEMENTED_MTI = 0x1043
ERROR_UNIMPLEMENTED_DATAGRAM = 0x1042
ERROR_OUT_OF_ORDER = 0x2040

DATAGRAM_OK_REPLY_PENDING = 0x80

# The standard's minimum listen time after the last CID frame.
ALIAS_WAIT = 0.2


class _Waiter:
    """Collects the incoming items a request is waiting for."""

    def __init__(self, predicate):
        self.predicate = predicate
        self.items = queue.Queue()

    def offer(self, item) -> bool:
        try:
            matched = bool(self.predicate(item))
        except Exception:
            matched = False
        if matched:
            self.items.put(item)
        return matched

    def get(self, deadline: float):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise queue.Empty()
        return self.items.get(timeout=remaining)


class Node:
    """
    Implementation of an OpenLCB/LCC :class:`Node`.

    On an interface that is connected, the node claims an alias (Check ID,
    200 ms listen, Reserve ID, Alias Map Definition) and announces itself with
    Initialization Complete before the constructor returns. On a GridConnect
    interface that connects later, or reconnects, it claims a fresh alias each
    time the link comes up.

    Once permitted, the node answers Verify Node ID, Alias Mapping Enquiry,
    Protocol Support Inquiry, Simple Node Information requests (when ``snip``
    is given) and Identify Events, and rejects addressed requests it does not
    implement. It also acts as a client: :meth:`simple_node_info`,
    :meth:`protocol_support_inquiry` and :meth:`datagram_exchange` send a
    request and wait for the answer, and
    :class:`pyolcb.memory_config.MemoryConfiguration` builds on them.

    Parameters
    ----------
    address : Address
        The address (full and optionally a preferred alias) to be associated with the :class:`Node`.
    interfaces : Interface | list[Interface]
        An :class:`Interface` or list thereof to connect the :class:`Node` to.
    snip : SimpleNodeInfo, optional
        Identity strings to answer SNIP requests with.
    protocols : protocols.Protocol, optional
        Protocols to report in Protocol Support Reply.
    allocate_alias : bool
        Claim the alias with the standard handshake (default). ``False`` keeps
        the old behaviour of announcing with a preset alias immediately.
    """
    address = None
    supported_protocols = protocols.Protocol()
    simple = False

    def __init__(self, address: Address, interfaces: Interface | list[Interface],
                 snip: SimpleNodeInfo = None, protocols: protocols.Protocol = None,
                 allocate_alias: bool = True):
        """
        Initialize the :class:`Node` object.

        Parameters
        ----------
        address : Address
            The address (full and alias) to be associated with the :class:`Node`.
        interfaces : int, Interface | list[Interface]
            An :class:`Interface` or list thereof to attach the :class:`Node` to.
        """
        self.address = address
        self.interfaces = []
        self.consumers = {}
        self.produced_events = {}
        self.consumed_events = {}
        self.aliases = {}
        self.snip = snip
        if protocols is not None:
            self.supported_protocols = protocols
        self.datagram_handler = None
        self.unknown_message_processor = lambda *args: None
        self._lock = threading.RLock()
        self._waiters = []
        self._frame_listeners = []
        self._state_listeners = []
        self._datagram_rx = {}
        self._destination_locks = {}
        self._permitted = threading.Event()
        self._claiming = threading.Lock()
        self._candidate = None
        self._conflict = threading.Event()
        self._alias_seed = self._initial_seed()
        self._sent_recently = collections.deque()

        if isinstance(interfaces, Interface):
            self.interfaces.append(interfaces)
        elif isinstance(interfaces, list) and all(isinstance(x, Interface) for x in interfaces):
            self.interfaces += interfaces
        else:
            raise Exception("No Interfaces to attach to")

        for interface in self.interfaces:
            interface.register_connected_device(self.address)
            interface.register_listener(self.process_message)
            interface.register_state_listener(self._interface_state)

        if not allocate_alias:
            if not self.address.has_alias():
                self.address.set_alias(self.address.get_full_address() & 0xFFF)
            self._announce()
        elif any(i.connected for i in self.interfaces):
            self.claim_alias()

    # --- identity ------------------------------------------------------------

    @property
    def node_id(self) -> int:
        return self.address.get_full_address()

    @property
    def permitted(self) -> bool:
        """True once the node has claimed an alias and may send messages."""
        return self._permitted.is_set()

    def wait_permitted(self, timeout: float = None) -> bool:
        """Block until the node holds an alias. Returns ``False`` on timeout."""
        return self._permitted.wait(timeout)

    def get_alias(self) -> int:
        """
        Get the :class:`Node`'s alias.

        Returns
        -------
        int
            Returns the :class:`Node`'s alias as an :class:`int`.
        """
        if self.address.alias is None:
            raise Exception("Alias not set!")
        else:
            return self.address.get_alias()

    def set_alias(self, alias: utilities.byte_options):
        return self.address.set_alias(alias)

    # --- alias allocation ------------------------------------------------------

    def _initial_seed(self) -> int:
        # Seed and step follow OpenMRN's AliasAllocator, as AOLCB does.
        nid = self.address.get_full_address()
        return ((nid >> 30) ^ (nid >> 18) ^ (nid >> 6) ^ ((nid >> 42) | (nid << 6))) & 0xFFF

    def _next_alias(self) -> int:
        nid = self.address.get_full_address()
        while True:
            alias = self._alias_seed
            offset = ((nid >> 36) ^ (nid >> 24) ^ (nid >> 12) ^ nid) & 0xFFFF
            offset = ((offset << 1) | 1) & 0xFFFF
            self._alias_seed = (self._alias_seed + offset) & 0xFFF
            if alias != 0 and alias not in self.aliases:
                return alias

    def claim_alias(self, attempts: int = 16) -> int:
        """
        Claim an alias with the CID/RID/AMD handshake and announce the node.
        Blocks for at least 200 ms. Returns the alias.
        """
        with self._claiming:
            self._permitted.clear()
            preferred = self.address.alias is not None and not hasattr(self, "_claimed_once")
            for _ in range(attempts):
                if preferred:
                    alias = self.address.get_alias()
                    preferred = False
                else:
                    alias = self._next_alias()
                self._conflict.clear()
                self._candidate = alias
                for sequence in (7, 6, 5, 4):
                    self._send_raw(Frame.cid(sequence, self.node_id, alias))
                if self._conflict.wait(ALIAS_WAIT):
                    continue
                self._candidate = None
                self.address.set_alias(alias)
                self._claimed_once = True
                self._send_raw(Frame.control(VAR_RID, alias))
                self._send_raw(Frame.control(VAR_AMD, alias, self.node_id.to_bytes(6, "big")))
                self._announce()
                return alias
            self._candidate = None
            raise exceptions.OlcbError("could not claim an alias")

    def _announce(self):
        mti = MTI_INITIALIZATION_COMPLETE_SIMPLE if self.simple else MTI_INITIALIZATION_COMPLETE
        self._permitted.set()
        self._send_raw(Frame.message(mti, self.get_alias(), self.node_id.to_bytes(6, "big")))
        self._identify_all()
        for listener in list(self._state_listeners):
            try:
                listener(True)
            except Exception:
                pass

    def _interface_state(self, connected: bool):
        if connected:
            # Never block the interface's reader thread: it must keep reading
            # to see alias conflicts during the handshake.
            threading.Thread(target=self._reclaim, name="pyolcb-alias", daemon=True).start()
        elif not any(i.connected for i in self.interfaces):
            self._permitted.clear()
            with self._lock:
                self.aliases.clear()
                self._datagram_rx.clear()
            for listener in list(self._state_listeners):
                try:
                    listener(False)
                except Exception:
                    pass

    def _reclaim(self):
        if self.permitted:
            return   # already claimed (the constructor raced the connect notification)
        try:
            self.claim_alias()
        except Exception:
            pass

    def add_state_listener(self, function: callable):
        """
        Call ``function(True)`` each time the node becomes permitted (after
        every successful alias claim) and ``function(False)`` when every
        interface has lost its connection.
        """
        self._state_listeners.append(function)

    # --- sending ---------------------------------------------------------------

    def add_frame_listener(self, function: callable):
        """
        Call ``function(frame, outgoing)`` for every frame received
        (``outgoing`` False) and every frame this node sends (True). Useful for
        traffic monitors.
        """
        self._frame_listeners.append(function)

    def _notify_frame(self, frame: Frame, outgoing: bool):
        for listener in list(self._frame_listeners):
            try:
                listener(frame, outgoing)
            except Exception:
                pass

    def _remember_sent(self, frame: Frame):
        with self._lock:
            now = time.monotonic()
            while self._sent_recently and now - self._sent_recently[0][0] > 1.0:
                self._sent_recently.popleft()
            self._sent_recently.append((now, frame.arbitration_id, bytes(frame.data)))

    def _send_raw(self, frame: Frame):
        self._remember_sent(frame)
        for interface in self.interfaces:
            interface.send(frame)
        self._notify_frame(frame, True)

    def _is_echo(self, frame: Frame) -> bool:
        """
        True for a copy of a frame we sent ourselves, as a CAN bus opened with
        ``receive_own_messages`` delivers. Without this our own CID frames
        would look like an alias conflict.
        """
        with self._lock:
            for entry in self._sent_recently:
                if entry[1] == frame.arbitration_id and entry[2] == bytes(frame.data):
                    self._sent_recently.remove(entry)
                    return True
        return False

    def send_frame(self, frame: Frame | list[Frame]):
        """Send one or more raw frames. Requires a claimed alias."""
        if not self.permitted:
            raise NotPermittedError("no alias claimed yet")
        for f in ([frame] if isinstance(frame, Frame) else frame):
            self._send_raw(f)

    def send(self, messages: Message | list[Message]):
        """
        Send a :class:`Message` (or sequence thereof) from this :class:`Node` on all registered interfaces.

        Parameters
        ----------
        messages : Message | list[Message]
            The :class:`Message` (or ordered list thereof) to send
        """
        if isinstance(messages, Message):
            messages = [messages]

        if len(self.interfaces) > 0:
            frames = [to_frame(m) for m in messages]
            for frame in frames:
                self._remember_sent(frame)
            results = [[i.send(m) for m in messages] for i in self.interfaces]
            for frame in frames:
                self._notify_frame(frame, True)
            return results
        else:
            raise Exception("No interfaces to send message on")

    def send_global(self, mti: int, payload: bytes = b""):
        """Send a global message (12-bit ``mti``) with up to 8 bytes of payload."""
        self.send_frame(Frame.message(mti, self.get_alias(), payload))

    def send_addressed(self, mti: int, destination: int, payload: bytes = b""):
        """Send an addressed message to ``destination`` (an alias), split into frames as needed."""
        self.send_frame(addressed_frames(mti, self.get_alias(), destination, payload))

    def send_datagram(self, destination: int, data: bytes):
        """Send a datagram to ``destination`` (an alias) without waiting for the acknowledgement."""
        self.send_frame(datagram_frames(self.get_alias(), destination, data))

    # --- events ----------------------------------------------------------------

    def produce(self, event: int | Event):
        """
        Produce an :class:`Event` and send the resulting message on all interfaces.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to produce and send. By default, if an :class:`int` is provided for
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                message = self._event_message(event)
            else:
                message = Event(event, self.address)
        elif isinstance(event, Event):
            if event.source is None:
                event.source = self.address
            message = event
        else:
            raise Exception("Invalid event")
        result = self.send(message)
        self._consume_locally(bytes(message.data))
        return result

    def _event_message(self, event_id: int) -> Message:
        return Message(message_types.Producer_Consumer_Event_Report, event_id.to_bytes(8, "big"), self.address)

    def _consume_locally(self, event_id: bytes):
        # A node's own consumers see the events it produces; the bus does not
        # echo them back.
        consumer = self.consumers.get(event_id)
        if consumer is not None:
            consumer(Message(message_types.Producer_Consumer_Event_Report, event_id, self.address))

    def produce_event(self, event_id: int):
        """Send a Producer/Consumer Event Report for the full 64-bit ``event_id``."""
        self.send_global(MTI_EVENT_REPORT, int(event_id).to_bytes(8, "big"))
        self._consume_locally(int(event_id).to_bytes(8, "big"))

    def add_produced_event(self, event_id: int, state: EventState = EventState.UNKNOWN):
        """Declare an event this node produces, so Identify Events and Identify Producer are answered."""
        self.produced_events[int(event_id)] = state

    def add_consumed_event(self, event_id: int, state: EventState = EventState.UNKNOWN):
        """Declare an event this node consumes, so Identify Events and Identify Consumer are answered."""
        self.consumed_events[int(event_id)] = state

    def remove_produced_event(self, event_id: int):
        self.produced_events.pop(int(event_id), None)

    def remove_consumed_event(self, event_id: int):
        self.consumed_events.pop(int(event_id), None)

    def identify_events(self, destination: int = None):
        """Ask one node (by alias) or, with no destination, every node to identify its events."""
        if destination is None:
            self.send_global(MTI_EVENTS_IDENTIFY_GLOBAL)
        else:
            self.send_addressed(MTI_EVENTS_IDENTIFY_ADDRESSED, destination)

    def identify_producer(self, event_id: int):
        """Ask the producers of ``event_id`` to identify themselves and their state."""
        self.send_global(MTI_PRODUCER_IDENTIFY, int(event_id).to_bytes(8, "big"))

    def identify_consumer(self, event_id: int):
        """Ask the consumers of ``event_id`` to identify themselves and their state."""
        self.send_global(MTI_CONSUMER_IDENTIFY, int(event_id).to_bytes(8, "big"))

    def _identify_all(self):
        alias = self.get_alias()
        consumed = dict(self.consumed_events)
        for event_id in self.consumers:
            consumed.setdefault(int.from_bytes(event_id, "big"), EventState.UNKNOWN)
        for event_id, state in consumed.items():
            self._send_raw(Frame.message(IDENTIFIED_MTI[state][0], alias, event_id.to_bytes(8, "big")))
        for event_id, state in dict(self.produced_events).items():
            self._send_raw(Frame.message(IDENTIFIED_MTI[state][1], alias, event_id.to_bytes(8, "big")))

    def add_consumer(self, event: Event | int, function: callable):
        """
        Register a function to be run on receipt of a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        function : callable
            The function to be called upon receipt of the specified :class:`Event`. Must be able to take no parameters.
        """
        event = self._as_event(event)
        if not event.id in self.consumers:
            self.consumers[event.id] = function
            return self.consumers
        else:
            raise Exception("Consumer already registered")

    def _as_event(self, event: Event | int) -> Event:
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                return Event(event)
            else:
                return Event(event, self.address)
        return event

    def remove_consumer(self, event: Event | int):
        """
        Deregister the function to be run on receipt of a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        """
        event = self._as_event(event)
        if event.id in self.consumers:
            del self.consumers[event.id]
        return self.consumers

    def replace_consumer(self, event: Event | int, function: callable):
        """
        Replace a function that is run on receipt of a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        function : callable
            The function to be called upon receipt of the specified :class:`Event`. Must be able to take no parameters.
        """
        event = self._as_event(event)
        self.remove_consumer(event)
        return self.add_consumer(event, function)

    def consume(self, event: Event | int):
        """
        Run the consumer for a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.

        Returns
        -------
        any
            Returns what the registered consumer function returns.
        """
        event = self._as_event(event)
        if event.id in self.consumers:
            return self.consumers[event.id]()
        else:
            raise Exception("Consumer not registered")

    def get_consumer(self, event: Event | int):
        """
        Get the consumer for a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.

        Returns
        -------
        callable
            Returns the registered consumer function.
        """
        event = self._as_event(event)
        if event.id in self.consumers:
            return self.consumers[event.id]
        else:
            raise Exception("Consumer not registered")

    # --- node identification ---------------------------------------------------

    def verify_node_id(self, address: Address | int = None):
        """
        Send a request to verify aliases on an OpenLCB/LCC network.

        Parameters
        ----------
        address : Address | int = None
            If specified, only request a response for a :class:`Node` with a given alias. Otherwise,
            request responses from each :class:`Node` attached to all registered interfaces.

        """
        if not address is None:
            if isinstance(address, Address):
                address = address.get_alias()
            return self.send(Message(message_types.Verify_Node_ID_Number_Addressed, utilities.process_bytes(2, address), self.address, address))
        else:
            # A node ID in a global Verify restricts the answer to that node,
            # so ask everyone with an empty payload.
            return self.send(Message(message_types.Verify_Node_ID_Number_Global, b"", self.address))

    def verified_node_id(self):
        return self.send(Message(message_types.Verified_Node_ID_Number, bytes(self.address), self.address))

    def alias_of(self, node_id: int) -> int | None:
        """The alias last seen for ``node_id``, or ``None``."""
        with self._lock:
            for alias, nid in self.aliases.items():
                if nid == node_id:
                    return alias
        return None

    def node_id_of(self, alias: int) -> int | None:
        """The node ID last seen for ``alias``, or ``None``."""
        return self.aliases.get(alias)

    def resolve_alias(self, node: Address | int, timeout: float = 1.0) -> int:
        """
        Find the alias of a node given as an :class:`Address` or a 48-bit node
        ID, asking the network with an Alias Mapping Enquiry if it is not yet
        known.
        """
        if isinstance(node, Address):
            if node.has_alias():
                return node.get_alias()
            node = node.get_full_address()
        alias = self.alias_of(node)
        if alias is not None:
            return alias
        if not self.permitted:
            raise NotPermittedError("no alias claimed yet")

        def is_mapping(item):
            f = item[1] if item[0] == "frame" else None
            if f is None or len(f.data) < 6 or int.from_bytes(f.data[:6], "big") != node:
                return False
            return ((f.is_control and f.variable_field == VAR_AMD)
                    or f.mti in (MTI_VERIFIED_NODE_ID, MTI_VERIFIED_NODE_ID_SIMPLE))

        with self._listen(is_mapping) as w:
            self._send_raw(Frame.control(VAR_AME, self.get_alias(), node.to_bytes(6, "big")))
            self.send_global(MTI_VERIFY_NODE_ID_GLOBAL, node.to_bytes(6, "big"))
            try:
                _, frame = w.get(time.monotonic() + timeout)
            except queue.Empty:
                raise UnknownNodeError("no node %012X answered" % node)
        return frame.source_alias

    # --- protocol support and SNIP ----------------------------------------------

    def add_supported_protocol(self, protocol: protocols.Protocol):
        self.supported_protocols += protocol
        return self.supported_protocols

    def get_supported_protocols(self):
        return self.supported_protocols

    def protocol_support_inquiry(self, destination: Address | int, timeout: float = 2.0) -> protocols.Protocol:
        """Ask a node which protocols it supports."""
        dest = self.resolve_alias(destination)
        reply = self.addressed_request(dest, MTI_PROTOCOL_SUPPORT_INQUIRY, b"", MTI_PROTOCOL_SUPPORT_REPLY, timeout)
        return protocols.Protocol.from_bytes(reply)

    # The original, misspelled name.
    def protocol_support_inqury(self, destination: Address | int, timeout: float = 2.0):
        return self.protocol_support_inquiry(destination, timeout)

    def protocol_support_reply(self, destination: int):
        """Send this node's Protocol Support Reply to ``destination`` (an alias)."""
        self.send_addressed(MTI_PROTOCOL_SUPPORT_REPLY, destination, bytes(self.supported_protocols) + b"\x00\x00\x00")

    def simple_node_info(self, destination: Address | int, timeout: float = 3.0) -> SimpleNodeInfo:
        """Ask a node for its Simple Node Information (manufacturer, model, versions, user name)."""
        dest = self.resolve_alias(destination)
        reply = self.addressed_request(dest, MTI_SNIP_REQUEST, b"", MTI_SNIP_REPLY, timeout)
        return SimpleNodeInfo.from_bytes(reply)

    @contextmanager
    def _listen(self, predicate):
        waiter = _Waiter(predicate)
        with self._lock:
            self._waiters.append(waiter)
        try:
            yield waiter
        finally:
            with self._lock:
                self._waiters.remove(waiter)

    def addressed_request(self, destination: int, mti: int, payload: bytes, reply_mti: int,
                          timeout: float = 2.0) -> bytes:
        """
        Send an addressed message to ``destination`` (an alias) and return the
        reassembled payload of the ``reply_mti`` message it answers with.

        Raises :class:`~pyolcb.exceptions.InteractionRejected` if the node
        rejects the request and :class:`~pyolcb.exceptions.ReplyTimeout` if it
        does not answer.
        """
        our = self.get_alias()

        def to_us(item):
            if item[0] != "frame":
                return False
            f = item[1]
            return (f.source_alias == destination and f.destination_alias == our
                    and f.mti in (reply_mti, MTI_OPTIONAL_INTERACTION_REJECTED, MTI_TERMINATE_DUE_TO_ERROR))

        # SNIP replies from older nodes carry no framing flags; they end after
        # the sixth string terminator instead.
        legacy_snip = reply_mti == MTI_SNIP_REPLY
        with self._listen(to_us) as w:
            self.send_addressed(mti, destination, payload)
            deadline = time.monotonic() + timeout
            buffer = b""
            while True:
                try:
                    _, f = w.get(deadline)
                except queue.Empty:
                    raise ReplyTimeout("no reply from alias 0x%03X to MTI 0x%03X" % (destination, mti))
                if f.mti in (MTI_OPTIONAL_INTERACTION_REJECTED, MTI_TERMINATE_DUE_TO_ERROR):
                    body = f.payload
                    rejected_mti = int.from_bytes(body[2:4], "big") if len(body) >= 4 else mti
                    if (rejected_mti & 0xFFF) == mti:
                        code = int.from_bytes(body[:2], "big") if len(body) >= 2 else 0
                        raise InteractionRejected("request 0x%03X rejected, error 0x%04X" % (mti, code), code)
                    continue
                framing = f.framing
                if framing == ADDRESSED_FIRST:
                    buffer = f.payload
                elif framing == ADDRESSED_ONLY and not legacy_snip:
                    return f.payload
                else:
                    buffer += f.payload
                if framing == ADDRESSED_LAST:
                    return buffer
                if framing == ADDRESSED_ONLY and buffer.count(0) >= 6:
                    return buffer

    # --- datagrams ---------------------------------------------------------------

    def set_datagram_handler(self, datagram_handler: callable):
        """
        Register a function to be run on receipt of a :class:`Datagram`.

        Parameters
        ----------
        datagram_handler : callable
            The function to be called upon receipt of a :class:`Datagram` packet. Must take a :class:`Datagram`
            as the first parameter. Return ``False`` to reject the datagram; anything else accepts it.
        """
        self.datagram_handler = datagram_handler
        return self.datagram_handler

    def _destination_lock(self, alias: int) -> threading.Lock:
        with self._lock:
            return self._destination_locks.setdefault(alias, threading.Lock())

    def datagram_exchange(self, destination: Address | int, data: bytes, timeout: float = 3.0,
                          expect_reply: bool = True, reply_filter: callable = None,
                          retries: int = 3) -> bytes | None:
        """
        Send a datagram and wait for it to be acknowledged, then (with
        ``expect_reply``) for the reply datagram, which is acknowledged with
        Datagram Received OK.

        Parameters
        ----------
        destination : Address | int
            The node, as an :class:`Address` or 48-bit node ID.
        data : bytes
            The datagram content, 1 to 72 bytes.
        timeout : float
            Seconds to wait for each answer. A Datagram Received OK that
            announces a longer reply time extends it.
        expect_reply : bool
            Wait for a reply datagram after the acknowledgement.
        reply_filter : callable, optional
            ``reply_filter(data) -> bool`` picks the reply among datagrams from
            the destination.
        retries : int
            How often to resend after a temporary rejection.

        Returns
        -------
        bytes | None
            The reply datagram, ``b""`` when no reply was wanted, or ``None``
            if the node acknowledged without announcing a reply.
        """
        dest = self.resolve_alias(destination)
        with self._destination_lock(dest):
            our = self.get_alias()

            def from_dest(item):
                if item[0] == "frame":
                    f = item[1]
                    return (f.source_alias == dest and f.destination_alias == our
                            and f.mti in (MTI_DATAGRAM_OK, MTI_DATAGRAM_REJECTED,
                                          MTI_OPTIONAL_INTERACTION_REJECTED, MTI_TERMINATE_DUE_TO_ERROR))
                return (expect_reply and item[1] == dest
                        and (reply_filter is None or reply_filter(item[2])))

            with self._listen(from_dest) as w:
                attempt = 0
                self.send_datagram(dest, data)
                deadline = time.monotonic() + timeout
                acknowledged = False
                while True:
                    try:
                        item = w.get(deadline)
                    except queue.Empty:
                        raise ReplyTimeout("no %s from alias 0x%03X" % (
                            "reply" if acknowledged else "acknowledgement", dest))
                    if item[0] == "datagram":
                        return item[2]
                    f = item[1]
                    body = f.payload
                    if f.mti == MTI_DATAGRAM_OK:
                        acknowledged = True
                        flags = body[0] if body else 0
                        if not expect_reply:
                            return b""
                        if not flags & DATAGRAM_OK_REPLY_PENDING:
                            return None
                        exponent = flags & 0x0F
                        if exponent:
                            deadline = max(deadline, time.monotonic() + 2 ** exponent)
                    elif f.mti == MTI_DATAGRAM_REJECTED:
                        code = int.from_bytes(body[:2], "big") if len(body) >= 2 else 0
                        if code & 0x2000 and attempt < retries:
                            attempt += 1
                            time.sleep(0.2 * attempt)
                            self.send_datagram(dest, data)
                            deadline = time.monotonic() + timeout
                            continue
                        raise DatagramRejected("datagram rejected, error 0x%04X" % code, code)
                    else:
                        rejected_mti = int.from_bytes(body[2:4], "big") if len(body) >= 4 else 0
                        if rejected_mti in (0, 0x1C48, 0xC48):
                            code = int.from_bytes(body[:2], "big") if len(body) >= 2 else 0
                            raise InteractionRejected("datagram refused, error 0x%04X" % code, code)

    def _datagram_frame(self, frame: Frame):
        src = frame.source_alias
        kind = frame.frame_type
        if kind == FRAME_TYPE_DATAGRAM_ONLY:
            self._datagram_complete(src, frame.data)
            return
        with self._lock:
            if kind == FRAME_TYPE_DATAGRAM_FIRST:
                self._datagram_rx[src] = bytearray(frame.data)
                return
            buffer = self._datagram_rx.get(src)
            if buffer is None:
                self._send_raw(addressed_frames(MTI_DATAGRAM_REJECTED, self.get_alias(), src,
                                                ERROR_OUT_OF_ORDER.to_bytes(2, "big"))[0])
                return
            buffer.extend(frame.data)
            if kind != FRAME_TYPE_DATAGRAM_FINAL:
                return
            del self._datagram_rx[src]
        self._datagram_complete(src, bytes(buffer))

    def _datagram_complete(self, src: int, data: bytes):
        data = bytes(data)
        claimed = self._offer(("datagram", src, data))
        accept = claimed
        if not claimed and self.datagram_handler is not None:
            try:
                result = self.datagram_handler(Datagram(data, Address(alias=src), self.address))
            except Exception:
                result = False
            accept = result is not False
        elif not claimed and len(data) >= 2 and data[0] == 0x20 and _is_config_reply(data[1]):
            accept = True   # a late answer to a request that already gave up
        if accept:
            self._send_raw(addressed_frames(MTI_DATAGRAM_OK, self.get_alias(), src, b"\x00")[0])
        else:
            self._send_raw(addressed_frames(MTI_DATAGRAM_REJECTED, self.get_alias(), src,
                                            ERROR_UNIMPLEMENTED_DATAGRAM.to_bytes(2, "big"))[0])

    # --- receiving -----------------------------------------------------------------

    def set_unknown_message_processor(self, function: callable):
        """
        Register a function to be run on receipt of a message of unknown type.

        Parameters
        ----------
        function : callable
            The function to be called upon receipt of an unknown message. Must take a :class:`Message` as the first parameter.
        """
        self.unknown_message_processor = function
        return self.unknown_message_processor

    def _offer(self, item) -> bool:
        with self._lock:
            waiters = list(self._waiters)
        claimed = False
        for waiter in waiters:
            if waiter.offer(item):
                claimed = True
        return claimed

    def _track_alias(self, frame: Frame):
        if frame.is_control:
            var = frame.variable_field
            if var == VAR_AMD and len(frame.data) >= 6:
                with self._lock:
                    self.aliases[frame.source_alias] = int.from_bytes(frame.data[:6], "big")
            elif var == VAR_AMR:
                with self._lock:
                    self.aliases.pop(frame.source_alias, None)
        elif frame.mti in (MTI_VERIFIED_NODE_ID, MTI_VERIFIED_NODE_ID_SIMPLE,
                           MTI_INITIALIZATION_COMPLETE, MTI_INITIALIZATION_COMPLETE_SIMPLE) \
                and len(frame.data) >= 6:
            with self._lock:
                self.aliases[frame.source_alias] = int.from_bytes(frame.data[:6], "big")

    def process_message(self, message):
        """
        Handle one received frame (a :class:`Frame` or :class:`can.Message`).
        Interfaces call this for every frame they receive.
        """
        frame = message if isinstance(message, Frame) else Frame.from_can_message(message)
        if frame.source_alias in (self._candidate, self.address.alias and self.address.get_alias()) \
                and self._is_echo(frame):
            return
        self._notify_frame(frame, False)
        self._track_alias(frame)

        # Someone else using the alias we are claiming, or already hold.
        if self._candidate is not None and frame.source_alias == self._candidate:
            self._conflict.set()
            return
        if self.permitted and frame.source_alias == self.address.get_alias():
            if frame.is_cid:
                self._send_raw(Frame.control(VAR_RID, self.get_alias()))
            else:
                self._permitted.clear()
                self._send_raw(Frame.control(VAR_AMR, self.get_alias(), self.node_id.to_bytes(6, "big")))
                threading.Thread(target=self._reclaim, name="pyolcb-alias", daemon=True).start()
            return

        self._offer(("frame", frame))
        if not self.permitted:
            return
        our = self.get_alias()

        if frame.is_control:
            if frame.variable_field == VAR_AME and (
                    not frame.data or int.from_bytes(frame.data[:6], "big") == self.node_id):
                self._send_raw(Frame.control(VAR_AMD, our, self.node_id.to_bytes(6, "big")))
            if frame.variable_field == VAR_AMD and len(frame.data) >= 6 \
                    and int.from_bytes(frame.data[:6], "big") == self.node_id:
                # Duplicate Node ID detected.
                self._send_raw(Frame.message(MTI_EVENT_REPORT, our, (0x0101000000000201).to_bytes(8, "big")))
            return

        if frame.is_datagram:
            if frame.destination_alias == our:
                self._datagram_frame(frame)
            return
        if frame.mti == 0:
            return   # stream frame
        if frame.is_addressed:
            if frame.destination_alias == our:
                self._handle_addressed(frame)
            return
        self._handle_global(frame)

    def _handle_addressed(self, frame: Frame):
        mti = frame.mti
        if mti in _REPLY_MTIS:
            return
        # Answer a multi-frame request once, on its first frame.
        if frame.framing not in (ADDRESSED_ONLY, ADDRESSED_FIRST):
            return
        src = frame.source_alias
        if mti == MTI_VERIFY_NODE_ID_ADDRESSED:
            self._send_raw(Frame.message(MTI_VERIFIED_NODE_ID, self.get_alias(), self.node_id.to_bytes(6, "big")))
        elif mti == MTI_PROTOCOL_SUPPORT_INQUIRY:
            self.protocol_support_reply(src)
        elif mti == MTI_EVENTS_IDENTIFY_ADDRESSED:
            self._identify_all()
        elif mti == MTI_SNIP_REQUEST and self.snip is not None:
            self.send_addressed(MTI_SNIP_REPLY, src, self.snip.to_bytes())
        else:
            message = Message.from_can_message(frame)
            if message is not None:
                self.unknown_message_processor(message)
            body = ERROR_UNIMPLEMENTED_MTI.to_bytes(2, "big") + mti.to_bytes(2, "big")
            self.send_addressed(MTI_OPTIONAL_INTERACTION_REJECTED, src, body)

    def _handle_global(self, frame: Frame):
        mti = frame.mti
        data = frame.data
        if mti == MTI_VERIFY_NODE_ID_GLOBAL:
            if not data or int.from_bytes(data[:6], "big") == self.node_id:
                self._send_raw(Frame.message(MTI_VERIFIED_NODE_ID, self.get_alias(), self.node_id.to_bytes(6, "big")))
        elif mti == MTI_EVENTS_IDENTIFY_GLOBAL:
            self._identify_all()
        elif mti == MTI_CONSUMER_IDENTIFY and len(data) >= 8:
            event_id = int.from_bytes(data[:8], "big")
            state = self.consumed_events.get(event_id)
            if state is None and bytes(data[:8]) in self.consumers:
                state = EventState.UNKNOWN
            if state is not None:
                self._send_raw(Frame.message(IDENTIFIED_MTI[state][0], self.get_alias(), bytes(data[:8])))
        elif mti == MTI_PRODUCER_IDENTIFY and len(data) >= 8:
            state = self.produced_events.get(int.from_bytes(data[:8], "big"))
            if state is not None:
                self._send_raw(Frame.message(IDENTIFIED_MTI[state][1], self.get_alias(), bytes(data[:8])))
        elif mti == MTI_EVENT_REPORT and len(data) >= 8:
            consumer = self.consumers.get(bytes(data[:8]))
            if consumer is not None:
                consumer(Message.from_can_message(frame))
        else:
            message = Message.from_can_message(frame)
            if message is not None:
                self.unknown_message_processor(message)


def _is_config_reply(command: int) -> bool:
    return (command & 0xF0) in (0x10, 0x30, 0x50, 0x70) or command in (0x82, 0x86, 0x87, 0x8A, 0x8D)


class SimpleNode(Node):
    simple = True
    supported_protocols = protocols.Simple_Protocol_Subset

    def __init__(self, address: Address, interfaces: Interface | list[Interface], **kwargs):
        super().__init__(address, interfaces, **kwargs)
