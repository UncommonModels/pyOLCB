from enum import Enum
from .address import Address
from .message import Message
from . import message_types
from . import utilities


class EventState(Enum):
    """The state a producer or consumer reports for an event when identified."""
    VALID = 0x4
    INVALID = 0x5
    UNKNOWN = 0x7


# The (consumer, producer) identified MTIs for each state.
IDENTIFIED_MTI = {
    EventState.VALID: (0x4C4, 0x544),
    EventState.INVALID: (0x4C5, 0x545),
    EventState.UNKNOWN: (0x4C7, 0x547),
}


class Event(Message):
    id = bytes(8)
    well_known = False
    def __init__(self, event_id: utilities.byte_options, source: Address = None):
        self.id = utilities.process_bytes(8, event_id)
        if self.id[0:2] in [[0x01,0x00],[0x01,0x01]] or self.id[0:4] == [0x09, 0x00, 0x99, 0xFF]:
            self.well_known = True
        elif not source is None:
            self.id = ((source.get_full_address() << 16 )+int.from_bytes(self.id[-2:],'big')).to_bytes(8,'big')
        super().__init__(message_types.Producer_Consumer_Event_Report, self.id, source)

    def __eq__(self, x: object):
        return self.id == x.id

