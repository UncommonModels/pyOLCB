import can
import socket
import asyncio
from .message import Message
from .address import Address
from enum import Enum

class InterfaceType(Enum):
    CAN = 0
    TCP = 1

class Interface:
    network = []
    phy = None
    connection = None
    def __init__(self, connection: can.BusABC | socket.socket) -> None:
        if isinstance(connection, can.BusABC):
            self.connection = connection
            self.phy = InterfaceType.CAN
        else:
            raise NotImplementedError("TCP/IP support is not yet implemented")
        
    def send(self, message:Message):
        if self.phy == InterfaceType.CAN:
            can_message = can.Message(arbitration_id=message.get_can_header(), data=message.data, is_extended_id=True)
            return self.connection.send(can_message)
        
    def register_connected_device(self, address:Address):
        if not address in self.network:
            self.network.append(address)
        return self.network

    def register_listener(self, function:callable):
        if self.phy == InterfaceType.CAN:
            can.Notifier(self.connection, [function])

    def list_connected_devices(self):
        return self.network
