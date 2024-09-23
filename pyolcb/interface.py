import can
import socket
import asyncio
from .message import Message
from .address import Address

class Interface:
    network = []
    def __init__(self, connection: can.BusABC | socket.socket) -> None:
        self.is_can_interface = False
        if isinstance(connection, can.BusABC):
            self.connection = connection
            self.is_can_interface = True
        else:
            raise Exception("TCP/IP support is not yet implemented")
        
    def send(self, message:Message):
        if self.is_can_interface:
            can_message = can.Message(arbitration_id=message.get_can_header(), data=message.data, is_extended_id=True)
            return self.connection.send(can_message)
        
    def register_connected_device(self, address:Address):
        if not address in self.network:
            self.network.append(address)
        return self.network
    
    def list_connected_devices(self):
        return self.network
