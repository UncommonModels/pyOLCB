"""
==============
gridconnect
==============

GridConnect, the ASCII encoding of CAN frames that OpenLCB uses over TCP
(port 12021 by convention, advertised over mDNS as ``_openlcb-can._tcp``) and
over USB serial adapters::

    :X19490ABCN;                   Verify Node ID, alias 0xABC, no data
    :X19170ABCN020157000099;       Verified Node ID 02.01.57.00.00.99

``:X`` then the 29-bit identifier in hex, ``N`` then up to eight data bytes in
hex, and ``;``. Whitespace between frames is ignored.

:class:`GridConnectTcpInterface` and :class:`GridConnectSerialInterface` are
:class:`~pyolcb.interface.Interface` implementations that read in a background
thread and reconnect by themselves when the link drops.
"""

import re
import socket
import threading
import time
from .frame import Frame
from .interface import Interface, InterfaceType, to_frame

DEFAULT_TCP_PORT = 12021
MDNS_SERVICE = "_openlcb-can._tcp.local."

# The longest body we accept between ':' and ';': 'X', 8 digits, 'N', 16 digits.
_BODY_MAX = 32
_BODY = re.compile(r"^[Xx]([0-9A-Fa-f]{1,8})[Nn]((?:[0-9A-Fa-f]{2}){0,8})$")


def format_frame(frame: Frame) -> str:
    """Encode a frame as GridConnect text, without a line ending."""
    frame = to_frame(frame)
    return ":X%08XN%s;" % (frame.arbitration_id, bytes(frame.data).hex().upper())


def parse_frame(text: str) -> Frame | None:
    """
    Decode one GridConnect frame such as ``:X19490ABCN;``. Returns ``None`` for
    anything that is not a valid extended data frame.
    """
    text = text.strip()
    if not (text.startswith(":") and text.endswith(";")):
        return None
    match = _BODY.match(text[1:-1])
    if not match:
        return None
    can_id = int(match.group(1), 16)
    if can_id > 0x1FFFFFFF:
        return None
    return Frame(can_id, bytes.fromhex(match.group(2)))


class GridConnectParser:
    """
    Incremental GridConnect decoder.

    Feed it whatever arrives on the wire, in pieces of any size. Follows the
    same rules as AOLCB's parser: a ``:`` always starts a new frame (abandoning
    a partial one), text outside ``:`` ... ``;`` is skipped, and malformed or
    overlong frames are dropped. That makes it safe on a serial console that
    mixes human-readable messages with frames.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._body = []
        self._in_frame = False

    def feed(self, data: bytes | str) -> list[Frame]:
        """Consume ``data`` and return every complete frame it finished."""
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("ascii", errors="replace")
        frames = []
        for c in data:
            if c == ":":
                self._body = []
                self._in_frame = True
            elif not self._in_frame:
                continue
            elif c == ";":
                self._in_frame = False
                match = _BODY.match("".join(self._body))
                if match:
                    can_id = int(match.group(1), 16)
                    if can_id <= 0x1FFFFFFF:
                        frames.append(Frame(can_id, bytes.fromhex(match.group(2))))
            elif len(self._body) >= _BODY_MAX:
                self._in_frame = False
            else:
                self._body.append(c)
        return frames


class GridConnectInterface(Interface):
    """
    Base for GridConnect transports: a reader thread, listener fan-out and
    automatic reconnection. Subclasses implement :meth:`_open`, :meth:`_read`,
    :meth:`_write` and :meth:`_close_link`.

    Parameters
    ----------
    reconnect : bool
        Keep trying to (re)connect when the link fails. When ``False`` the
        interface stops after the first disconnect.
    retry_interval : float
        Seconds between reconnection attempts (doubling up to 30 s).
    start : bool
        Start connecting immediately. Otherwise call :meth:`start`.
    """
    phy = InterfaceType.TCP

    def __init__(self, reconnect: bool = True, retry_interval: float = 1.0, start: bool = True):
        super().__init__()
        self.reconnect = reconnect
        self.retry_interval = retry_interval
        self.last_error = None
        self._listeners = []
        self._link = None
        self._write_lock = threading.RLock()
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._parser = GridConnectParser()
        if start:
            self.start()

    # --- Interface API -----------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def wait_connected(self, timeout: float = None) -> bool:
        """Block until the link is up. Returns ``False`` on timeout."""
        return self._connected.wait(timeout)

    def register_listener(self, function: callable):
        self._listeners.append(function)

    def remove_listener(self, function: callable):
        if function in self._listeners:
            self._listeners.remove(function)

    def send(self, message) -> bool:
        """
        Send a :class:`Frame` or :class:`Message`. Returns ``False`` (and
        drops the frame) while disconnected.
        """
        text = (format_frame(message) + "\r\n").encode("ascii")
        with self._write_lock:
            link = self._link
            if link is None or not self._connected.is_set():
                return False
            try:
                self._write(link, text)
                return True
            except (OSError, ValueError) as e:
                self.last_error = str(e)
                self._drop(link)
                return False

    def start(self):
        """Start the reader thread, which connects and keeps reconnecting."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gridconnect-%s" % self.describe(),
                                        daemon=True)
        self._thread.start()

    def close(self):
        """Disconnect and stop reconnecting."""
        self._stop.set()
        link = self._link
        if link is not None:
            self._drop(link)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def describe(self) -> str:
        """A short human-readable description of the endpoint."""
        return "gridconnect"

    # --- subclass hooks ----------------------------------------------------

    def _open(self):
        raise NotImplementedError()

    def _read(self, link) -> bytes:
        """Return received bytes, ``b''`` when nothing arrived, raise on a dead link."""
        raise NotImplementedError()

    def _write(self, link, data: bytes):
        raise NotImplementedError()

    def _close_link(self, link):
        raise NotImplementedError()

    # --- internals ---------------------------------------------------------

    def _drop(self, link):
        with self._write_lock:
            if self._link is link:
                self._link = None
        try:
            self._close_link(link)
        except Exception:
            pass

    def _run(self):
        delay = self.retry_interval
        while not self._stop.is_set():
            try:
                link = self._open()
            except Exception as e:  # any failure to open is retried
                self.last_error = str(e)
                if not self.reconnect:
                    return
                self._stop.wait(delay)
                delay = min(delay * 2, 30.0)
                continue
            delay = self.retry_interval
            self.last_error = None
            self._parser.reset()
            with self._write_lock:
                self._link = link
            self._connected.set()
            self._notify_state(True)
            try:
                while not self._stop.is_set() and self._link is link:
                    data = self._read(link)
                    if data:
                        for frame in self._parser.feed(data):
                            for listener in list(self._listeners):
                                try:
                                    listener(frame)
                                except Exception:
                                    pass
            except Exception as e:
                self.last_error = str(e) or type(e).__name__
            self._connected.clear()
            self._drop(link)
            self._notify_state(False)
            if not self.reconnect:
                return
            self._stop.wait(self.retry_interval)


class GridConnectTcpInterface(GridConnectInterface):
    """
    GridConnect over TCP, as served by an OpenLCB hub, a FemtoLCC node's WiFi
    link, JMRI's hub or OpenMRN's ``hub`` program.

    Parameters
    ----------
    host : str
        Host name or address.
    port : int
        TCP port, 12021 by default.
    """
    phy = InterfaceType.TCP

    def __init__(self, host: str, port: int = DEFAULT_TCP_PORT, connect_timeout: float = 5.0, **kwargs):
        self.host = host
        self.port = int(port)
        self.connect_timeout = connect_timeout
        super().__init__(**kwargs)

    def describe(self) -> str:
        return "tcp:%s:%d" % (self.host, self.port)

    def _open(self):
        sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.settimeout(0.2)
        return sock

    def _read(self, link) -> bytes:
        try:
            data = link.recv(4096)
        except socket.timeout:
            return b""
        if not data:
            raise ConnectionError("connection closed by peer")
        return data

    def _write(self, link, data: bytes):
        link.sendall(data)

    def _close_link(self, link):
        try:
            link.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        link.close()


class GridConnectSerialInterface(GridConnectInterface):
    """
    GridConnect over a serial port: a USB-LCC adapter, or a FemtoLCC board's
    USB console, which switches to bridging LCC traffic when it sees the first
    GridConnect frame from the computer. Requires pyserial.

    RTS and DTR are held low so that opening the port does not reset an ESP32
    through its USB-serial auto-reset circuit.

    Parameters
    ----------
    port : str
        Device, e.g. ``/dev/ttyACM0`` or ``COM3``.
    baudrate : int
        Line speed; USB CDC adapters ignore it.
    """
    phy = InterfaceType.SERIAL

    def __init__(self, port: str, baudrate: int = 115200, **kwargs):
        self.port = port
        self.baudrate = int(baudrate)
        super().__init__(**kwargs)

    def describe(self) -> str:
        return "serial:%s" % self.port

    def _open(self):
        import serial  # pyserial, imported lazily so TCP users do not need it
        link = serial.Serial()
        link.port = self.port
        link.baudrate = self.baudrate
        link.timeout = 0.2
        link.write_timeout = 2
        link.rts = False
        link.dtr = False
        link.open()
        return link

    def _read(self, link) -> bytes:
        waiting = link.in_waiting
        return link.read(waiting if waiting else 1)

    def _write(self, link, data: bytes):
        link.write(data)
        link.flush()

    def _close_link(self, link):
        link.close()


def list_serial_ports() -> list[dict]:
    """Serial ports pyserial can see, as ``{"device", "description"}`` dicts."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [{"device": p.device, "description": p.description or ""}
            for p in sorted(list_ports.comports(), key=lambda p: p.device)]


def browse_mdns(timeout: float = 2.0) -> list[dict]:
    """
    Find GridConnect TCP hubs advertised over mDNS as ``_openlcb-can._tcp``.
    Needs the optional ``zeroconf`` package; returns ``[]`` without it.
    Each result is ``{"name", "host", "port", "addresses"}``.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return []

    found = {}

    class _Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
            if info is not None:
                addresses = info.parsed_addresses() if hasattr(info, "parsed_addresses") else []
                found[name] = {
                    "name": name.replace("." + type_, ""),
                    "host": (info.server or "").rstrip("."),
                    "port": info.port,
                    "addresses": addresses,
                }

        def update_service(self, zc, type_, name):
            self.add_service(zc, type_, name)

        def remove_service(self, zc, type_, name):
            found.pop(name, None)

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, MDNS_SERVICE, _Listener())
        time.sleep(timeout)
    finally:
        zc.close()
    return sorted(found.values(), key=lambda s: s["name"])


def mdns_available() -> bool:
    """True if the optional ``zeroconf`` package is installed."""
    try:
        import zeroconf  # noqa: F401
        return True
    except ImportError:
        return False
