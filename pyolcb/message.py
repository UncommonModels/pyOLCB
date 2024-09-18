from .address import Address
from .message_types import MessageTypeIndicator, is_known_mti
import can

class Message:
    source = None
    destination = None
    data = bytes(8)
    def __init__(self, message_type:MessageTypeIndicator, data:bytes | bytearray = None, source:Address = None, destination:Address = None, frame_id = None) -> None:
        self.source = source
        self.destination = destination
        self.data = data
        self.message_type = message_type
        self.frame_id = frame_id

    def get_can_header(self) -> bytes:
        if self.source is None:
            raise Exception("No source node set")        
        else:
            return self.message_type.get_can_header(self.message_type, self.source, self.destination, self.frame_id)
    
    def get_mti(self) -> bytes:
        return self.message_type.get_mti()

    @classmethod
    def from_can_message(cls, message:can.Message):
        if message.is_extended_id():
            mti = MessageTypeIndicator.from_can_header(message.arbitration_id)
            if is_known_mti(mti):
                return cls(mti,message.data, Address(alias=message.arbitration_id & 0xFFF))
            else:
                return None
        else:
            return None
        
