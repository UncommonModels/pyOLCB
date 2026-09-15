from .address import Address
from .message_types import MessageTypeIndicator, is_known_mti


class Message:
    source = None
    destination = None
    data = bytes(8)

    def __init__(self, message_type: MessageTypeIndicator, data: bytes | bytearray = None, source: Address = None,
                 destination: Address = None, frame_id: int = None) -> None:
        self.source = source
        self.destination = destination
        self.data = data
        self.message_type = message_type
        self.frame_id = frame_id

    def get_can_header(self) -> int:
        if self.source is None:
            raise Exception("No source node set")
        else:
            return self.message_type.get_can_header(self.source, self.destination, self.frame_id)

    def get_can_header_bytes(self) -> bytes:
        if self.source is None:
            raise Exception("No source node set")
        else:
            return self.message_type.get_can_header_bytes(self.source, self.destination, self.frame_id)

    def get_mti(self) -> bytes:
        return self.message_type.get_mti()

    @classmethod
    def from_can_message(cls, message):
        """
        Convert a received frame into a :class:`Message`.

        Accepts a :class:`can.Message` or a :class:`pyolcb.frame.Frame` (anything
        with ``arbitration_id``, ``data`` and ``is_extended_id``). Returns
        ``None`` for CAN control frames and unknown MTIs. The destination of an
        addressed message or datagram is filled in as an alias-only
        :class:`Address`.
        """
        if not message.is_extended_id or not (message.arbitration_id & 0x08000000):
            return None
        can_id = message.arbitration_id
        mti = MessageTypeIndicator.from_can_header(can_id)
        frame_id = None
        destination = None
        data = bytes(message.data)
        match (can_id >> 24):
            case 0x1A:
                frame_id = None
            case 0x1B:
                frame_id = 1
            case 0x1D:
                frame_id = -1
            case 0x1C:
                frame_id = 2
        if (can_id >> 24) in (0x1A, 0x1B, 0x1C, 0x1D, 0x1F):
            destination = Address(alias=(can_id >> 12) & 0xFFF)
        elif mti.value & 0x0008 and len(data) >= 2:
            destination = Address(alias=((data[0] & 0x0F) << 8) | data[1])
        if is_known_mti(mti):
            return cls(mti, data, Address(alias=can_id & 0xFFF), destination, frame_id)
        else:
            return None
