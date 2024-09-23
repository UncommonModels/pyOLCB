from pyolcb import message_types
from .address import Address
from .message import Message
from . import message_types
from . import utilities

class Event(Message):
    id = bytes(8)
    well_known = False
    def __init__(self, event_id, source: Address = None):
        self.id = utilities.process_bytes(8, event_id)
        if self.id[0:2] in [[0x01,0x00],[0x01,0x01]] or self.id[0:4] == [0x09, 0x00, 0x99, 0xFF]:
            self.well_known = True
        elif not source is None:
            self.id = ((source.get_full_address() << 16 )+int.from_bytes(self.id[-2:],'big')).to_bytes(8,'big')
        super().__init__(message_types.Producer_Consumer_Event_Report, self.id, source)