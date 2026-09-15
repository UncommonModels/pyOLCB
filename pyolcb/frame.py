"""
==============
frame
==============

Transport-neutral OpenLCB CAN frames.

Every OpenLCB frame is a 29-bit extended CAN frame, whether it travels on a
real CAN bus or as GridConnect text over TCP or a serial line::

    bit 28      always 1
    bit 27      1 = OpenLCB message frame, 0 = CAN control frame
    bits 26-12  variable field
    bits 11-0   source alias

In a message frame bits 26-24 are the frame type. For type 1 (global or
addressed message) bits 23-12 are the MTI; for types 2-5 (datagram) they are
the destination alias. In a control frame bits 26-24 are 4-7 for the CID frames
that carry a 12-bit slice of the node ID, and 0 for RID/AMD/AME/AMR.

:class:`Frame` is duck-type compatible with :class:`can.Message` (it has
``arbitration_id``, ``data`` and ``is_extended_id``), so code written for
python-can frames works on GridConnect frames too.
"""

import re

CAN_PRIORITY_BIT = 0x10000000
CAN_MESSAGE_BIT = 0x08000000

# Control frame variable fields.
VAR_RID = 0x0700   # Reserve ID
VAR_AMD = 0x0701   # Alias Map Definition
VAR_AME = 0x0702   # Alias Mapping Enquiry
VAR_AMR = 0x0703   # Alias Map Reset
VAR_ERROR_INFO = 0x0710   # Error Information Report 0-3 (0x0710-0x0713)

# Message frame types.
FRAME_TYPE_GLOBAL_ADDRESSED = 1
FRAME_TYPE_DATAGRAM_ONLY = 2
FRAME_TYPE_DATAGRAM_FIRST = 3
FRAME_TYPE_DATAGRAM_MIDDLE = 4
FRAME_TYPE_DATAGRAM_FINAL = 5
FRAME_TYPE_STREAM = 7

# An MTI with this bit set carries a destination alias in its first two bytes.
MTI_ADDRESSED_BIT = 0x008

# Framing flags in the top nibble of an addressed message's first byte.
ADDRESSED_ONLY = 0x00
ADDRESSED_FIRST = 0x10
ADDRESSED_LAST = 0x20
ADDRESSED_MIDDLE = 0x30


class Frame:
    """
    A single OpenLCB CAN frame, independent of how it is carried.

    Parameters
    ----------
    arbitration_id : int
        The 29-bit CAN identifier.
    data : bytes | bytearray | list[int]
        Up to eight payload bytes.
    """
    is_extended_id = True

    def __init__(self, arbitration_id: int, data: bytes | bytearray | list[int] = b""):
        self.arbitration_id = int(arbitration_id) & 0x1FFFFFFF
        self.data = bytes(data)
        if len(self.data) > 8:
            raise ValueError("A CAN frame carries at most 8 data bytes")

    def __eq__(self, x: object) -> bool:
        return (hasattr(x, "arbitration_id") and hasattr(x, "data")
                and self.arbitration_id == x.arbitration_id and bytes(self.data) == bytes(x.data))

    def __hash__(self):
        return hash((self.arbitration_id, self.data))

    def __repr__(self):
        return "Frame(0x%08X, %s)" % (self.arbitration_id, self.data.hex().upper() or "-")

    @classmethod
    def from_can_message(cls, message) -> "Frame":
        """Convert a :class:`can.Message` (or anything with ``arbitration_id`` and ``data``)."""
        return cls(message.arbitration_id, bytes(message.data))

    # --- field access ------------------------------------------------------

    @property
    def is_control(self) -> bool:
        """True for a CAN control frame (CID, RID, AMD, AME, AMR)."""
        return (self.arbitration_id & CAN_MESSAGE_BIT) == 0

    @property
    def variable_field(self) -> int:
        return (self.arbitration_id >> 12) & 0x7FFF

    @property
    def source_alias(self) -> int:
        return self.arbitration_id & 0xFFF

    @property
    def frame_type(self) -> int:
        return (self.arbitration_id >> 24) & 0x7

    @property
    def is_cid(self) -> bool:
        """True for the four Check ID frames of alias allocation."""
        return self.is_control and self.frame_type >= 4

    @property
    def is_datagram(self) -> bool:
        return (not self.is_control
                and FRAME_TYPE_DATAGRAM_ONLY <= self.frame_type <= FRAME_TYPE_DATAGRAM_FINAL)

    @property
    def is_stream(self) -> bool:
        return not self.is_control and self.frame_type == FRAME_TYPE_STREAM

    @property
    def mti(self) -> int:
        """The 12-bit MTI of a global or addressed message, 0 for anything else."""
        if self.is_control or self.frame_type != FRAME_TYPE_GLOBAL_ADDRESSED:
            return 0
        return (self.arbitration_id >> 12) & 0xFFF

    @property
    def is_addressed(self) -> bool:
        """True for an addressed (not global) message frame."""
        return self.mti != 0 and bool(self.mti & MTI_ADDRESSED_BIT)

    @property
    def destination_alias(self) -> int | None:
        """
        The destination alias of an addressed message or datagram frame, or
        ``None`` for a global message or control frame.
        """
        if self.is_datagram or self.is_stream:
            return (self.arbitration_id >> 12) & 0xFFF
        if self.is_addressed and len(self.data) >= 2:
            return ((self.data[0] & 0x0F) << 8) | self.data[1]
        return None

    @property
    def framing(self) -> int:
        """The multi-frame flags (``ADDRESSED_*``) of an addressed message."""
        if self.is_addressed and self.data:
            return self.data[0] & 0x30
        return ADDRESSED_ONLY

    @property
    def payload(self) -> bytes:
        """The data bytes after the destination alias of an addressed message."""
        if self.is_addressed:
            return bytes(self.data[2:])
        return bytes(self.data)

    # --- builders ----------------------------------------------------------

    @classmethod
    def control(cls, variable: int, alias: int, data: bytes = b"") -> "Frame":
        """A CAN control frame (RID, AMD, AME, AMR, or a CID with the ID slice in ``variable``)."""
        return cls(CAN_PRIORITY_BIT | ((variable & 0x7FFF) << 12) | (alias & 0xFFF), data)

    @classmethod
    def cid(cls, sequence: int, node_id: int, alias: int) -> "Frame":
        """
        Check ID frame ``sequence`` (7 = CID1 with node ID bits 47-36, down to
        4 = CID4 with bits 11-0).
        """
        chunk = (node_id >> (12 * (sequence - 4))) & 0xFFF
        return cls.control((sequence << 12) | chunk, alias)

    @classmethod
    def message(cls, mti: int, alias: int, data: bytes = b"") -> "Frame":
        """A global message frame, or one frame of an addressed message (``data`` includes the destination)."""
        return cls(CAN_PRIORITY_BIT | CAN_MESSAGE_BIT | (FRAME_TYPE_GLOBAL_ADDRESSED << 24)
                   | ((mti & 0xFFF) << 12) | (alias & 0xFFF), data)

    @classmethod
    def datagram(cls, frame_type: int, destination: int, source: int, data: bytes) -> "Frame":
        return cls(CAN_PRIORITY_BIT | CAN_MESSAGE_BIT | ((frame_type & 0x7) << 24)
                   | ((destination & 0xFFF) << 12) | (source & 0xFFF), data)


def addressed_frames(mti: int, source: int, destination: int, payload: bytes = b"") -> list[Frame]:
    """
    Split an addressed message into frames: two bytes of destination alias and
    framing flags, then up to six payload bytes per frame.
    """
    payload = bytes(payload)
    frames = []
    sent = 0
    first = True
    while True:
        chunk = payload[sent:sent + 6]
        last = sent + len(chunk) >= len(payload)
        if first:
            framing = ADDRESSED_ONLY if last else ADDRESSED_FIRST
        else:
            framing = ADDRESSED_LAST if last else ADDRESSED_MIDDLE
        head = bytes([framing | ((destination >> 8) & 0x0F), destination & 0xFF])
        frames.append(Frame.message(mti, source, head + chunk))
        sent += len(chunk)
        first = False
        if last:
            return frames


def datagram_frames(source: int, destination: int, data: bytes) -> list[Frame]:
    """Split a datagram (1-72 bytes) into only/first/middle/final frames."""
    data = bytes(data)
    if not 0 < len(data) <= 72:
        raise ValueError("A datagram carries 1 to 72 bytes")
    if len(data) <= 8:
        return [Frame.datagram(FRAME_TYPE_DATAGRAM_ONLY, destination, source, data)]
    frames = []
    for off in range(0, len(data), 8):
        chunk = data[off:off + 8]
        if off == 0:
            kind = FRAME_TYPE_DATAGRAM_FIRST
        elif off + len(chunk) >= len(data):
            kind = FRAME_TYPE_DATAGRAM_FINAL
        else:
            kind = FRAME_TYPE_DATAGRAM_MIDDLE
        frames.append(Frame.datagram(kind, destination, source, chunk))
    return frames


def format_node_id(node_id: int) -> str:
    """``0x020157000099`` -> ``'02.01.57.00.00.99'``."""
    return ".".join("%02X" % b for b in int(node_id).to_bytes(6, "big"))


def format_event_id(event_id: int) -> str:
    """``0x0201570000990001`` -> ``'02.01.57.00.00.99.00.01'``."""
    return ".".join("%02X" % b for b in int(event_id).to_bytes(8, "big"))


def parse_id(text: str | int | bytes, length: int) -> int:
    """
    Parse a node ID (``length`` 6) or event ID (``length`` 8) written as dotted
    hex (``02.01.57.00.00.99``), with other separators, or as plain hex.
    """
    if isinstance(text, int):
        value = text
    elif isinstance(text, (bytes, bytearray)):
        if len(text) != length:
            raise ValueError("expected %d bytes" % length)
        value = int.from_bytes(text, "big")
    else:
        stripped = str(text).strip()
        parts = [p for p in re.split(r"[.:\-\s]+", stripped) if p]
        if len(parts) > 1:
            # Separated bytes: each part is one byte, so 2.1.57.0.0.99 works too.
            if len(parts) != length or not all(re.fullmatch(r"[0-9A-Fa-f]{1,2}", p) for p in parts):
                raise ValueError("%r is not a %d-byte ID" % (text, length))
            value = int.from_bytes(bytes(int(p, 16) for p in parts), "big")
        else:
            cleaned = stripped[2:] if stripped.lower().startswith("0x") else stripped
            if not re.fullmatch(r"[0-9A-Fa-f]{1,%d}" % (2 * length), cleaned):
                raise ValueError("%r is not a %d-byte ID" % (text, length))
            value = int(cleaned, 16)
    if not 0 <= value < (1 << (8 * length)):
        raise ValueError("%r does not fit in %d bytes" % (text, length))
    return value
