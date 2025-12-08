# pyOLCB
An easy to use python implementation of OpenLCB (LCC) protocols, designed to interface with CAN and TCP/IP via GridConnect format.

This is very much a **work in progress**, please don't expect it to function fully for a while.

Documentation is available at [https://www.uncommonmodels.com/pyOLCB](https://www.uncommonmodels.com/pyOLCB)

## CAN Example

```python
from pyolcb import Node, Address, Event, Interface
import can

address = Address('05.01.01.01.8C.00')
interface = Interface(can.Bus(interface='socketcan', channel='vcan0', bitrate=125000))

node = Node(address, interface)

node.produce(Event(125))
```

## TCP/IP Example

```python
from pyolcb import Node, Address, Event, Interface
import socket

# Connect to an OpenLCB hub via TCP/IP
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 12021))  # Connect to GridConnect hub

address = Address('05.01.01.01.8C.00')
interface = Interface(sock)

node = Node(address, interface)

node.produce(Event(125))
```