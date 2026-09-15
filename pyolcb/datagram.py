from .address import Address
from .message import Message
from . import message_types
from math import ceil


class Datagram(Message):
    """
    A datagram: up to 72 bytes sent reliably to one node, split across as many
    as nine CAN frames.

    Parameters
    ----------
    data : bytes | bytearray
        The datagram content. The first byte identifies the protocol (0x20 is
        Memory Configuration).
    source : Address
        The sending node.
    destination : Address
        The receiving node (its alias is required to build frames).
    """

    def __init__(self, data: bytes | bytearray, source: Address, destination: Address):
        super().__init__(message_types.Datagram, bytes(data), source, destination)

    def as_message_list(self):
        """
        Split the datagram into one :class:`Message` per CAN frame, with the
        frame types set for only (``None``), first (1), middle (2) and final
        (-1) frames.
        """
        num_frames = ceil(len(self.data) / 8)
        if num_frames <= 1:
            return [Message(message_types.Datagram, self.data, self.source, self.destination)]
        messages = []
        for frame_id in range(1, num_frames):
            messages.append(Message(message_types.Datagram, self.data[(frame_id - 1) * 8:frame_id * 8],
                                    self.source, self.destination, frame_id))
        messages.append(Message(message_types.Datagram, self.data[(num_frames - 1) * 8:],
                                self.source, self.destination, -1))
        return messages

    @classmethod
    def from_message_list(cls, message_list: list[Message] | Message):
        """Reassemble a datagram from the messages carrying its frames, in order."""
        if isinstance(message_list, Message):
            message_list = [message_list]
        data_bytearray = bytearray()
        for message in message_list:
            data_bytearray.extend(message.data)
        return cls(data_bytearray, message_list[0].source, message_list[0].destination)
