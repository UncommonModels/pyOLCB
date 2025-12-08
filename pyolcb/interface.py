import can
import socket
import asyncio
import threading
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
    _tcp_listener_thread = None
    _tcp_running = False
    _tcp_buffer = ""
    
    def __init__(self, connection: can.BusABC | socket.socket) -> None:
        if isinstance(connection, can.BusABC):
            self.connection = connection
            self.phy = InterfaceType.CAN
        elif isinstance(connection, socket.socket):
            self.connection = connection
            self.phy = InterfaceType.TCP
            self._tcp_buffer = ""
        else:
            raise TypeError("Connection must be either can.BusABC or socket.socket")
        
    def send(self, message:Message):
        if self.phy == InterfaceType.CAN:
            can_message = can.Message(arbitration_id=message.get_can_header(), data=message.data, is_extended_id=True)
            return self.connection.send(can_message)
        elif self.phy == InterfaceType.TCP:
            gridconnect_frame = message.to_gridconnect()
            return self.connection.sendall(gridconnect_frame.encode('ascii'))
        
    def register_connected_device(self, address:Address):
        if not address in self.network:
            self.network.append(address)
        return self.network

    def register_listener(self, function:callable):
        if self.phy == InterfaceType.CAN:
            can.Notifier(self.connection, [function])
        elif self.phy == InterfaceType.TCP:
            # Start TCP listener thread
            if self._tcp_listener_thread is None or not self._tcp_listener_thread.is_alive():
                self._tcp_running = True
                self._tcp_listener_thread = threading.Thread(
                    target=self._tcp_listener_loop, 
                    args=(function,),
                    daemon=True
                )
                self._tcp_listener_thread.start()

    def _tcp_listener_loop(self, callback:callable):
        """
        Internal method to listen for TCP messages and call the callback function.
        """
        while self._tcp_running:
            try:
                # Receive data from socket
                data = self.connection.recv(4096)
                if not data:
                    # Connection closed
                    break
                
                # Add to buffer and decode
                self._tcp_buffer += data.decode('ascii', errors='ignore')
                
                # Process complete frames (ending with ';')
                while ';' in self._tcp_buffer:
                    frame_end = self._tcp_buffer.index(';')
                    frame = self._tcp_buffer[:frame_end+1]
                    self._tcp_buffer = self._tcp_buffer[frame_end+1:]
                    
                    # Parse and callback
                    message = Message.from_gridconnect(frame)
                    if message is not None:
                        callback(message)
                        
            except socket.timeout:
                continue
            except Exception as e:
                # Handle errors but keep listening
                continue
    
    def stop_listener(self):
        """
        Stop the TCP listener thread if running.
        """
        if self.phy == InterfaceType.TCP and self._tcp_running:
            self._tcp_running = False
            if self._tcp_listener_thread is not None:
                self._tcp_listener_thread.join(timeout=1.0)

    def list_connected_devices(self):
        return self.network
