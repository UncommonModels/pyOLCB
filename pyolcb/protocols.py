
class Protocol:
    value = None
    def __init__(self, mask:int = 0x0 ) -> None:
        self.value = mask
    def __add__(self, o):
        return Protocol(self.value | o.value)
    def __iter__(self):
        return iter(self.value.to_bytes(3,'big'))

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