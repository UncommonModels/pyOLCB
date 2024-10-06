from pyolcb import message_types
from .address import Address
from .message import Message
from . import message_types
from . import utilities
from math import ceil


class Datagram(Message):
    def __init__(self, data: bytes | bytearray, source: Address, destination: Address):
        super().__init__(message_types.Datagram, data, source, destination)

    def as_message_list(self):
        num_frames = ceil(len(self.data)/8)
        if num_frames <= 1:
            return [Message(message_types.Datagram, self.data, self.source, self.destination)]
        else:
            messages = []
            for frame_id in range(1, num_frames):
                messages.append(Message(message_types.Datagram, self.data[(
                    frame_id-1)*8:frame_id*8], self.source, self.destination, frame_id))
            messages.append(Message(message_types.Datagram, self.data[(
                num_frames-1)*8:], self.source, self.destination, frame_id))
            return messages
        

    @classmethod
    def from_message_list(cls, message_list: list[Message]):
        data_bytearray = bytearray()
        for message in message_list:
            data_bytearray.append(message.data)
        cls(data_bytearray, message_list[0].source, message_list[0].destination)


