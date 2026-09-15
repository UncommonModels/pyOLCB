from .address import Address


class MessageTypeIndicator:
    def __init__(self, mti: int):
        self.value = mti

    def get_mti(self):
        return self.value

    def __eq__(self, x: object) -> bool:
        return isinstance(x, MessageTypeIndicator) and self.value == x.value

    def __hash__(self):
        return hash(self.value)

    def __repr__(self):
        return "MTI(0x%04X %s)" % (self.value, name_of(self.value))

    def get_can_header(self, source: Address, destination: Address = None, frame_id: int = None) -> int:
        temp_bytes = ((0x0FFF & self.value) << 12) | source.get_alias()
        if self.value & (0b1 << 12):
            if not destination is None:
                temp_bytes = (temp_bytes & ~(0xFFF << 12)) | destination.get_alias() << 12
                match frame_id:
                    case None:
                        return int(temp_bytes | 0x1A000000)
                    case 1:
                        return int(temp_bytes | 0x1B000000)
                    case -1:
                        return int(temp_bytes | 0x1D000000)
                    case _:
                        return int(temp_bytes | 0x1C000000)
            else:
                raise Exception("Destination address not provided")
        else:
            return int(temp_bytes | 0x19000000)

    def get_can_header_bytes(self, source: Address, destination: Address = None, frame_id: int = None) -> bytes:
        return self.get_can_header(source, destination, frame_id).to_bytes(4, 'big')

    @classmethod
    def from_can_header(cls, can_header: int):
        mti = 0x0000
        if (can_header >> 24) in [0x1A, 0x1B, 0x1C, 0x1D]:
            return cls(0x1C48)
        if (can_header >> 24) == 0x1F:
            return cls(0x1F88)
        mti = mti | ((can_header >> 12) & 0x00FFF)
        return cls(mti)


class MTI(MessageTypeIndicator):
    pass


Initialization_Complete = MTI(0x0100)
Initialization_Complete_Simple = MTI(0x0101)
Verify_Node_ID_Number_Addressed = MTI(0x0488)
Verify_Node_ID_Number_Global = MTI(0x0490)
Verified_Node_ID_Number = MTI(0x0170)
Verified_Node_ID_Number_Simple = MTI(0x0171)
Optional_Interaction_Rejected = MTI(0x0068)
Terminate_Due_to_Error = MTI(0x00A8)
Protocol_Support_Inquiry = MTI(0x0828)
Protocol_Support_Reply = MTI(0x0668)
Identify_Consumer = MTI(0x08F4)
Consumer_Range_Identified = MTI(0x04A4)
Consumer_Identified_w_validity_unknown = MTI(0x04C7)
Consumer_Identified_as_currently_valid = MTI(0x04C4)
Consumer_Identified_as_currently_invalid = MTI(0x04C5)
Consumer_Identified__reserved = MTI(0x04C6)
Identify_Producer = MTI(0x0914)
Producer_Range_Identified = MTI(0x0524)
Producer_Identified_w_validity_unknown = MTI(0x0547)
Producer_Identified_as_currently_valid = MTI(0x0544)
Producer_Identified_as_currently_invalid = MTI(0x0545)
Producer_Identified__reserved = MTI(0x0546)
Identify_Events_Addressed = MTI(0x0968)
Identify_Events_Global = MTI(0x0970)
Learn_Event = MTI(0x0594)
Producer_Consumer_Event_Report = MTI(0x05B4)
PCER_w_Payload_1st = MTI(0x0F14)
PCER_w_Payload_middle = MTI(0x0F15)
PCER_w_Payload_last = MTI(0x0F16)
Traction_Control_Command = MTI(0x05EB)
Traction_Control_Reply = MTI(0x01E9)
Traction_Proxy_Command__obsolete = MTI(0x05EA)
Traction_Proxy_Reply__obsolete = MTI(0x01E8)
Xpressnet = MTI(0x09C0)
Remote_Button_Request = MTI(0x0948)
Remote_Button_Reply = MTI(0x0549)
Simple_Train_Node_Ident_Info_Request = MTI(0x0DA8)
Simple_Train_Node_Ident_Info_Reply = MTI(0x09C8)
Simple_Node_Ident_Info_Request = MTI(0x0DE8)
Simple_Node_Ident_Info_Reply = MTI(0x0A08)
Datagram = MTI(0x1C48)
Datagram_Received_OK = MTI(0x0A28)
Datagram_Rejected = MTI(0x0A48)
Stream_Initiate_Request = MTI(0x0CC8)
Stream_Initiate_Reply = MTI(0x0868)
Stream_Data_Send = MTI(0x1F88)
Stream_Data_Proceed = MTI(0x0888)
Stream_Data_Complete = MTI(0x08A8)
Node_number_Allocate = MTI(0x2000)
No_Filtering = MTI(0x2020)

# Every MTI above, keyed by its 16-bit value and by the 12-bit form a CAN
# header carries.
KNOWN_MTIS = {v.value: v for v in list(globals().values()) if isinstance(v, MessageTypeIndicator)}
MTI_NAMES = {value: name.replace("__", " ").replace("_", " ").replace(" w ", " with ")
             for name, v in list(globals().items()) if isinstance(v, MessageTypeIndicator)
             for value in [v.value]}
_CAN_NAMES = {value & 0xFFF: name for value, name in MTI_NAMES.items() if value < 0x1000}


def is_known_mti(mti: MessageTypeIndicator | int) -> bool:
    """True if ``mti`` (an MTI object or its 16-bit value) is in the table above."""
    value = mti.value if isinstance(mti, MessageTypeIndicator) else mti
    return value in KNOWN_MTIS


def name_of(mti: MessageTypeIndicator | int) -> str:
    """
    A readable name for an MTI, given as an object, its 16-bit value, or the
    12-bit value from a CAN header. Unknown values come back as hex.
    """
    value = mti.value if isinstance(mti, MessageTypeIndicator) else int(mti)
    if value in MTI_NAMES:
        return MTI_NAMES[value]
    if value in _CAN_NAMES:
        return _CAN_NAMES[value]
    return "MTI 0x%03X" % value
