"""
==============
memory_config
==============

Memory Configuration protocol: reading and writing a node's configuration,
CDI and identity through datagrams whose first byte is 0x20.

The codec functions build requests and decode replies without any I/O, and
:class:`MemoryConfiguration` runs them against a remote node through
:meth:`pyolcb.Node.datagram_exchange`::

    mc = MemoryConfiguration(node, 0x020157000099)
    cdi = mc.read_cdi()
    mc.write(SPACE_ACDI_USER, 1, b"Yard throat\\0")
    mc.update_complete()
"""

from .exceptions import MemoryConfigError, ReplyTimeout

DATAGRAM_CONFIGURATION = 0x20

SPACE_CDI = 0xFF
SPACE_ALL_MEMORY = 0xFE
SPACE_CONFIG = 0xFD
SPACE_ACDI_SYS = 0xFC     # read-only: manufacturer, model, versions
SPACE_ACDI_USER = 0xFB    # read-write: user name and description
SPACE_FDI = 0xFA
SPACE_TRAIN_FUNCTIONS = 0xF9

SPACE_NAMES = {
    SPACE_CDI: "CDI", SPACE_ALL_MEMORY: "All memory", SPACE_CONFIG: "Configuration",
    SPACE_ACDI_SYS: "ACDI manufacturer", SPACE_ACDI_USER: "ACDI user",
    SPACE_FDI: "FDI", SPACE_TRAIN_FUNCTIONS: "Train functions",
}

CMD_WRITE = 0x00
CMD_WRITE_UNDER_MASK = 0x08
CMD_WRITE_REPLY = 0x10
CMD_WRITE_FAILED = 0x18
CMD_WRITE_STREAM = 0x20
CMD_READ = 0x40
CMD_READ_REPLY = 0x50
CMD_READ_FAILED = 0x58
CMD_READ_STREAM = 0x60
CMD_OPTIONS = 0x80
CMD_OPTIONS_REPLY = 0x82
CMD_INFO = 0x84
CMD_INFO_REPLY = 0x86      # | 1 when the space is present
CMD_LOCK = 0x88
CMD_LOCK_REPLY = 0x8A
CMD_UNIQUE_ID = 0x8C
CMD_UNIQUE_ID_REPLY = 0x8D
CMD_UNFREEZE = 0xA0
CMD_FREEZE = 0xA1
CMD_UPDATE_COMPLETE = 0xA8
CMD_RESET = 0xA9
CMD_FACTORY_RESET = 0xAA

# The most data one read or write datagram carries.
MAX_TRANSFER = 64

# ACDI user space layout (0xFB): version byte, 63-byte name, 64-byte description.
USER_NAME_OFFSET = 1
USER_NAME_SIZE = 63
USER_DESCRIPTION_OFFSET = 64
USER_DESCRIPTION_SIZE = 64


def _space_from_command(command: int, body: bytes) -> tuple[int, int]:
    """(space, header length) of a read/write style command."""
    code = command & 0x03
    if code == 1:
        return SPACE_CONFIG, 6
    if code == 2:
        return SPACE_ALL_MEMORY, 6
    if code == 3:
        return SPACE_CDI, 6
    return (body[6] if len(body) > 6 else 0), 7


def read_request(space: int, address: int, count: int) -> bytes:
    """A read of ``count`` (1-64) bytes, always in the explicit-space form."""
    if not 1 <= count <= MAX_TRANSFER:
        raise ValueError("a read is 1 to 64 bytes")
    return bytes([DATAGRAM_CONFIGURATION, CMD_READ]) + int(address).to_bytes(4, "big") + bytes([space, count])


def write_request(space: int, address: int, data: bytes) -> bytes:
    """A write of up to 64 bytes, in the explicit-space form."""
    if not 1 <= len(data) <= MAX_TRANSFER:
        raise ValueError("a write is 1 to 64 bytes")
    return bytes([DATAGRAM_CONFIGURATION, CMD_WRITE]) + int(address).to_bytes(4, "big") + bytes([space]) + bytes(data)


def options_request() -> bytes:
    return bytes([DATAGRAM_CONFIGURATION, CMD_OPTIONS])


def space_info_request(space: int) -> bytes:
    return bytes([DATAGRAM_CONFIGURATION, CMD_INFO, space])


def update_complete_request() -> bytes:
    return bytes([DATAGRAM_CONFIGURATION, CMD_UPDATE_COMPLETE])


def reset_request() -> bytes:
    return bytes([DATAGRAM_CONFIGURATION, CMD_RESET])


def factory_reset_request(node_id: int) -> bytes:
    """Factory reset must name the target node, so a stray datagram cannot wipe the wrong one."""
    return bytes([DATAGRAM_CONFIGURATION, CMD_FACTORY_RESET]) + int(node_id).to_bytes(6, "big")


def lock_request(node_id: int) -> bytes:
    """Reserve a node for configuration (node ID 0 releases it)."""
    return bytes([DATAGRAM_CONFIGURATION, CMD_LOCK]) + int(node_id).to_bytes(6, "big")


def is_reply_to(request: bytes, reply: bytes) -> bool:
    """True if ``reply`` is the Memory Configuration answer to ``request``."""
    if len(reply) < 2 or reply[0] != DATAGRAM_CONFIGURATION or len(request) < 2:
        return False
    command = request[1]
    answer = reply[1]
    if command < 0x80:
        kind = command & 0xFC
        if kind == CMD_READ:
            ok = (answer & 0xF8) in (CMD_READ_REPLY, CMD_READ_FAILED)
        elif kind == CMD_WRITE:
            ok = (answer & 0xF8) in (CMD_WRITE_REPLY, CMD_WRITE_FAILED)
        else:
            return False
        return ok and reply[2:6] == request[2:6]
    if command == CMD_OPTIONS:
        return answer == CMD_OPTIONS_REPLY
    if command == CMD_INFO:
        return answer in (CMD_INFO_REPLY, CMD_INFO_REPLY | 1) and len(reply) > 2 and len(request) > 2 \
            and reply[2] == request[2]
    if command == CMD_LOCK:
        return answer == CMD_LOCK_REPLY
    if command == CMD_UNIQUE_ID:
        return answer == CMD_UNIQUE_ID_REPLY
    return False


def parse_read_reply(reply: bytes) -> tuple[int, int, bytes]:
    """
    Decode a read reply into ``(space, address, data)``. Raises
    :class:`MemoryConfigError` for a Read Failed reply.
    """
    if len(reply) < 6 or reply[0] != DATAGRAM_CONFIGURATION:
        raise MemoryConfigError("not a memory configuration reply")
    command = reply[1]
    space, header = _space_from_command(command, reply)
    address = int.from_bytes(reply[2:6], "big")
    if (command & 0xF8) == CMD_READ_FAILED:
        code = int.from_bytes(reply[header:header + 2], "big") if len(reply) >= header + 2 else 0
        raise MemoryConfigError("read of space 0x%02X at 0x%X failed, error 0x%04X" % (space, address, code), code)
    if (command & 0xF8) != CMD_READ_REPLY:
        raise MemoryConfigError("unexpected reply 0x%02X" % command)
    return space, address, bytes(reply[header:])


def parse_write_reply(reply: bytes) -> None:
    """Check a write reply; raises :class:`MemoryConfigError` for Write Failed."""
    command = reply[1]
    if (command & 0xF8) == CMD_WRITE_FAILED:
        space, header = _space_from_command(command, reply)
        code = int.from_bytes(reply[header:header + 2], "big") if len(reply) >= header + 2 else 0
        raise MemoryConfigError("write to space 0x%02X failed, error 0x%04X" % (space, code), code)


class SpaceInfo:
    """What Get Address Space Information reports about a memory space."""

    def __init__(self, space: int, present: bool, highest: int = 0, lowest: int = 0,
                 read_only: bool = True, description: str = ""):
        self.space = space
        self.present = present
        self.highest = highest
        self.lowest = lowest
        self.read_only = read_only
        self.description = description

    @property
    def size(self) -> int:
        """Bytes from the lowest to the highest address, inclusive."""
        return self.highest - self.lowest + 1 if self.present else 0

    def to_dict(self) -> dict:
        return {"space": self.space, "present": self.present, "highest": self.highest,
                "lowest": self.lowest, "read_only": self.read_only, "size": self.size,
                "description": self.description}

    def __repr__(self):
        return "SpaceInfo(0x%02X, present=%s, highest=0x%X, read_only=%s)" % (
            self.space, self.present, self.highest, self.read_only)


def parse_space_info_reply(reply: bytes) -> SpaceInfo:
    """
    Decode ``[0x20, 0x86|present, space, highest(4), flags, lowest(4)?, description?]``.
    Flag bit 0 is read-only, bit 1 says a lowest address follows.
    """
    if len(reply) < 3 or reply[0] != DATAGRAM_CONFIGURATION or (reply[1] & 0xFE) != CMD_INFO_REPLY:
        raise MemoryConfigError("not an address space information reply")
    present = bool(reply[1] & 1)
    space = reply[2]
    if not present:
        return SpaceInfo(space, False)
    highest = int.from_bytes(reply[3:7], "big") if len(reply) >= 7 else 0
    flags = reply[7] if len(reply) >= 8 else 0
    lowest = 0
    rest = reply[8:]
    if flags & 0x02 and len(rest) >= 4:
        lowest = int.from_bytes(rest[:4], "big")
        rest = rest[4:]
    description = rest.split(b"\x00")[0].decode("utf-8", errors="replace")
    return SpaceInfo(space, True, highest, lowest, bool(flags & 0x01), description)


def parse_options_reply(reply: bytes) -> dict:
    """Decode Get Configuration Options Reply."""
    if len(reply) < 7 or reply[1] != CMD_OPTIONS_REPLY:
        raise MemoryConfigError("not a configuration options reply")
    available = int.from_bytes(reply[2:4], "big")
    return {
        "available_commands": available,
        "write_under_mask": bool(available & 0x8000),
        "unaligned_reads": bool(available & 0x4000),
        "unaligned_writes": bool(available & 0x2000),
        "read_acdi_manufacturer": bool(available & 0x0800),
        "read_acdi_user": bool(available & 0x0400),
        "write_acdi_user": bool(available & 0x0200),
        "write_lengths": reply[4],
        "highest_space": reply[5],
        "lowest_space": reply[6],
        "name": reply[7:].split(b"\x00")[0].decode("utf-8", errors="replace"),
    }


def describe(data: bytes) -> str:
    """A one-line summary of a Memory Configuration datagram, for traffic monitors."""
    if len(data) < 2 or data[0] != DATAGRAM_CONFIGURATION:
        return "datagram " + bytes(data).hex(" ").upper()
    command = data[1]

    def space_text(space):
        return ("0x%02X %s" % (space, SPACE_NAMES.get(space, ""))).rstrip()

    if command < 0x80:
        kind = command & 0xF8
        space, header = _space_from_command(command, data)
        address = int.from_bytes(data[2:6], "big") if len(data) >= 6 else 0
        body = data[header:]
        where = "space %s @ 0x%X" % (space_text(space), address)
        if kind in (CMD_READ, CMD_READ | 0x08) and (command & 0xFC) == CMD_READ:
            return "Read %s, %d bytes" % (where, body[0] & 0x7F if body else 0)
        if kind == CMD_READ_REPLY:
            return "Read reply %s: %d bytes" % (where, len(body))
        if kind == CMD_READ_FAILED:
            return "Read failed %s, error 0x%s" % (where, body[:2].hex().upper())
        if kind == CMD_WRITE:
            return "Write %s: %s" % (where, body.hex(" ").upper())
        if kind == CMD_WRITE_UNDER_MASK:
            return "Write under mask %s" % where
        if kind == CMD_WRITE_REPLY:
            return "Write reply %s" % where
        if kind == CMD_WRITE_FAILED:
            return "Write failed %s, error 0x%s" % (where, body[:2].hex().upper())
        return "Stream command 0x%02X %s" % (command, where)
    names = {
        CMD_OPTIONS: "Get configuration options", CMD_OPTIONS_REPLY: "Configuration options reply",
        CMD_LOCK: "Lock/reserve", CMD_LOCK_REPLY: "Lock reply", CMD_UNIQUE_ID: "Get unique ID",
        CMD_UNIQUE_ID_REPLY: "Unique ID reply", CMD_UNFREEZE: "Unfreeze", CMD_FREEZE: "Freeze",
        CMD_UPDATE_COMPLETE: "Update complete", CMD_RESET: "Reset/reboot",
        CMD_FACTORY_RESET: "Factory reset",
    }
    if command == CMD_INFO and len(data) > 2:
        return "Get address space info %s" % space_text(data[2])
    if (command & 0xFE) == CMD_INFO_REPLY and len(data) > 2:
        try:
            info = parse_space_info_reply(data)
            if info.present:
                return "Address space info %s: 0x%X-0x%X%s" % (
                    space_text(info.space), info.lowest, info.highest, ", read-only" if info.read_only else "")
        except MemoryConfigError:
            pass
        return "Address space info %s: not present" % space_text(data[2])
    return names.get(command, "Memory configuration command 0x%02X" % command)


class MemoryConfiguration:
    """
    A Memory Configuration client for one remote node.

    Parameters
    ----------
    node : pyolcb.Node
        The local node to send from.
    destination : Address | int
        The node to configure, as an :class:`Address` or 48-bit node ID.
    timeout : float
        Seconds to wait for each answer.
    """

    def __init__(self, node, destination, timeout: float = 3.0):
        self.node = node
        self.destination = destination
        self.timeout = timeout

    def _exchange(self, request: bytes, expect_reply: bool = True):
        return self.node.datagram_exchange(self.destination, request, timeout=self.timeout,
                                           expect_reply=expect_reply,
                                           reply_filter=lambda reply: is_reply_to(request, reply))

    def options(self) -> dict:
        """Get Configuration Options."""
        reply = self._exchange(options_request())
        if reply is None:
            raise MemoryConfigError("node sent no options reply")
        return parse_options_reply(reply)

    def space_info(self, space: int) -> SpaceInfo:
        """Get Address Space Information."""
        reply = self._exchange(space_info_request(space))
        if reply is None:
            raise MemoryConfigError("node sent no space information")
        return parse_space_info_reply(reply)

    def read(self, space: int, address: int, length: int) -> bytes:
        """
        Read ``length`` bytes in as many 64-byte requests as it takes. Stops
        early, returning fewer bytes, at the end of the space.
        """
        out = bytearray()
        while len(out) < length:
            count = min(MAX_TRANSFER, length - len(out))
            request = read_request(space, address + len(out), count)
            reply = self._exchange(request)
            if reply is None:
                raise MemoryConfigError("node acknowledged a read without replying")
            _, _, data = parse_read_reply(reply)
            if not data:
                break
            out.extend(data[:count])
            if len(data) < count:
                break
        return bytes(out)

    def write(self, space: int, address: int, data: bytes):
        """Write ``data`` in as many 64-byte requests as it takes."""
        data = bytes(data)
        for offset in range(0, len(data), MAX_TRANSFER):
            request = write_request(space, address + offset, data[offset:offset + MAX_TRANSFER])
            reply = self._exchange(request)
            if reply:
                parse_write_reply(reply)

    def read_space(self, space: int, stop_at_nul: bool = False, limit: int = 1 << 20) -> bytes:
        """
        Read a whole space, sized with Get Address Space Information. With
        ``stop_at_nul`` reading ends at the first NUL (for the CDI).
        """
        info = self.space_info(space)
        if not info.present:
            raise MemoryConfigError("space 0x%02X is not present" % space, 0x1081)
        size = min(info.size, limit)
        out = bytearray()
        address = info.lowest
        while len(out) < size:
            chunk = self.read(space, address + len(out), min(MAX_TRANSFER, size - len(out)))
            if not chunk:
                break
            out.extend(chunk)
            if stop_at_nul and b"\x00" in chunk:
                break
        data = bytes(out)
        return data.split(b"\x00")[0] if stop_at_nul else data

    def read_cdi(self) -> str:
        """Read the node's Configuration Description Information XML."""
        return self.read_space(SPACE_CDI, stop_at_nul=True).decode("utf-8", errors="replace")

    def update_complete(self):
        """Tell the node the tool has finished writing, so it commits and applies the settings."""
        self._exchange(update_complete_request(), expect_reply=False)

    def reboot(self):
        """Ask the node to restart. A node that restarts before acknowledging is not an error."""
        try:
            self._exchange(reset_request(), expect_reply=False)
        except ReplyTimeout:
            pass

    def factory_reset(self, node_id: int):
        """Reset the node's configuration to factory defaults. ``node_id`` must be the node's own ID."""
        try:
            self._exchange(factory_reset_request(node_id), expect_reply=False)
        except ReplyTimeout:
            pass

    def lock(self, node_id: int) -> int:
        """Reserve the node for ``node_id`` (0 releases). Returns the node ID now holding the lock."""
        reply = self._exchange(lock_request(node_id))
        return int.from_bytes(reply[2:8], "big") if reply and len(reply) >= 8 else 0
