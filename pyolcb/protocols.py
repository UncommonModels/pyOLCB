
class Protocol:
    """
    A set of protocol flags, as carried in a Protocol Support Reply.

    The value holds the first three bytes of the reply (bit 23 = Simple
    Protocol subset ... bit 4 = Firmware Upgrade Active). Protocols combine
    with ``+`` and membership is tested with ``in``::

        p = Datagram_Protocol + Event_Exchange_Protocol
        Datagram_Protocol in p   # True
    """
    value = None

    def __init__(self, mask: int = 0x0) -> None:
        self.value = mask

    def __add__(self, o):
        return Protocol(self.value | o.value)

    def __iter__(self):
        return iter(self.value.to_bytes(3, 'big'))

    def __bytes__(self):
        return self.value.to_bytes(3, 'big')

    def __eq__(self, o) -> bool:
        return isinstance(o, Protocol) and self.value == o.value

    def __hash__(self):
        return hash(self.value)

    def __contains__(self, o) -> bool:
        return (self.value & o.value) == o.value

    def __repr__(self):
        return "Protocol(0x%06X)" % self.value

    def names(self) -> list[str]:
        """Human-readable names of the protocols in this set."""
        return [name for mask, name in PROTOCOL_NAMES if self.value & mask]

    @classmethod
    def from_bytes(cls, data: bytes) -> "Protocol":
        """Decode the payload of a Protocol Support Reply (its first three bytes)."""
        return cls(int.from_bytes(bytes(data[:3]).ljust(3, b"\x00"), 'big'))


Simple_Protocol_Subset = Protocol(0x800000)
Datagram_Protocol = Protocol(0x400000)
Stream_Protocol = Protocol(0x200000)
Memory_Configuration_Protocol = Protocol(0x100000)
Reservation_Protocol = Protocol(0x080000)
Event_Exchange_Protocol = Protocol(0x040000)
Identification_Protocol = Protocol(0x020000)
Teaching_Learning_Configuration_Protocol = Protocol(0x010000)
Remote_Button_Protocol = Protocol(0x008000)
Abbreviated_Default_CDI_Protocol = Protocol(0x004000)
Display_Protocol = Protocol(0x002000)
Simple_Node_Information_Protocol = Protocol(0x001000)
Configuration_Description_Information = Protocol(0x000800)
Train_Control_Protocol = Protocol(0x000400)
Function_Description_Information = Protocol(0x000200)
Function_Configuration = Protocol(0x000040)
Firmware_Upgrade_Protocol = Protocol(0x000020)
Firmware_Upgrade_Active = Protocol(0x000010)

PROTOCOL_NAMES = [
    (0x800000, "Simple Protocol subset"),
    (0x400000, "Datagram"),
    (0x200000, "Stream"),
    (0x100000, "Memory Configuration"),
    (0x080000, "Reservation"),
    (0x040000, "Event Exchange"),
    (0x020000, "Identification"),
    (0x010000, "Teach/Learn"),
    (0x008000, "Remote Button"),
    (0x004000, "ACDI"),
    (0x002000, "Display"),
    (0x001000, "SNIP"),
    (0x000800, "CDI"),
    (0x000400, "Traction Control"),
    (0x000200, "FDI"),
    (0x000100, "DCC Command Station"),
    (0x000080, "Simple Train Node Info"),
    (0x000040, "Function Configuration"),
    (0x000020, "Firmware Upgrade"),
    (0x000010, "Firmware Upgrade Active"),
]
