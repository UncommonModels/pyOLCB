import socket
import threading
from enum import Enum
from .message import Message
from .address import Address
from .frame import Frame

try:  # python-can is only needed for real CAN buses
    import can
except ImportError:  # pragma: no cover - depends on the environment
    can = None


class InterfaceType(Enum):
    CAN = 0
    TCP = 1
    SERIAL = 2


class Interface:
    """
    A connection to an OpenLCB/LCC network.

    The base class wraps a python-can bus. GridConnect over TCP and over a
    serial line are provided by :class:`pyolcb.gridconnect.GridConnectTcpInterface`
    and :class:`pyolcb.gridconnect.GridConnectSerialInterface`, which share this
    API: :meth:`send` a :class:`Message` or :class:`Frame`, and
    :meth:`register_listener` to be called with every received frame.

    Parameters
    ----------
    connection : can.BusABC
        The python-can bus to use.
    """
    phy = None
    connection = None

    def __init__(self, connection=None) -> None:
        self.network = []
        self._state_listeners = []
        if can is not None and isinstance(connection, can.BusABC):
            self.connection = connection
            self.phy = InterfaceType.CAN
        elif isinstance(connection, socket.socket):
            raise NotImplementedError(
                "Use pyolcb.gridconnect.GridConnectTcpInterface(host, port) for GridConnect over TCP")
        elif connection is not None:
            raise NotImplementedError("Unsupported connection type %r" % type(connection))

    @property
    def connected(self) -> bool:
        """True while frames can be sent. A CAN bus is always connected."""
        return self.connection is not None

    def send(self, message: Message | Frame):
        """
        Send a :class:`Message` or a raw :class:`Frame`.
        """
        frame = to_frame(message)
        if self.phy == InterfaceType.CAN:
            can_message = can.Message(arbitration_id=frame.arbitration_id,
                                      data=frame.data, is_extended_id=True)
            return self.connection.send(can_message)
        raise NotImplementedError()

    def register_connected_device(self, address: Address):
        if address not in self.network:
            self.network.append(address)
        return self.network

    def register_listener(self, function: callable):
        """
        Register a function to be called with every frame received. On a CAN
        bus the argument is a :class:`can.Message`; on GridConnect interfaces it
        is a :class:`Frame`. Both have ``arbitration_id`` and ``data``.
        """
        if self.phy == InterfaceType.CAN:
            can.Notifier(self.connection, [function])

    def register_state_listener(self, function: callable):
        """
        Register a function to be called with ``True`` when the interface
        (re)connects and ``False`` when it loses its connection. A node uses
        this to claim a fresh alias after every reconnect.
        """
        self._state_listeners.append(function)

    def _notify_state(self, connected: bool):
        for listener in list(self._state_listeners):
            try:
                listener(connected)
            except Exception:  # a listener must never kill the transport
                pass

    def list_connected_devices(self):
        return self.network

    def close(self):
        """Release the connection."""
        if self.phy == InterfaceType.CAN and self.connection is not None:
            self.connection.shutdown()


def to_frame(message: Message | Frame) -> Frame:
    """Convert a :class:`Message`, :class:`Frame` or :class:`can.Message` into a :class:`Frame`."""
    if isinstance(message, Frame):
        return message
    if isinstance(message, Message):
        return Frame(message.get_can_header(), message.data or b"")
    if hasattr(message, "arbitration_id"):
        return Frame.from_can_message(message)
    raise TypeError("Cannot send %r" % type(message))
