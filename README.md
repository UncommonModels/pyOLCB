# pyOLCB
An easy to use python implementation of OpenLCB (LCC) protocols, designed to interface with CAN and with TCP/IP and serial links via GridConnect.

This is very much a **work in progress**, please don't expect it to function fully for a while.

Documentation is available at [https://www.uncommonmodels.com/pyOLCB](https://www.uncommonmodels.com/pyOLCB)


```python
from pyolcb import Node, Address, Event, Interface
import can

address = Address('05.01.01.01.8C.00')
interface = Interface(can.Bus(interface='socketcan', channel='vcan0', bitrate=125000))

node = Node(address, interface)

node.produce(Event(125))
```

## Installing

```
pip install pyOLCB                 # GridConnect over TCP needs nothing else
pip install "pyOLCB[can]"          # python-can, for CAN buses
pip install "pyOLCB[serial]"       # pyserial, for GridConnect over USB/serial adapters
pip install "pyOLCB[mdns]"         # zeroconf, to find hubs advertised as _openlcb-can._tcp
```

## GridConnect over TCP or serial

```python
from pyolcb import Node, Address, SimpleNodeInfo, GridConnectTcpInterface, GridConnectSerialInterface

interface = GridConnectTcpInterface("femtolcc-0001.local", 12021)   # or GridConnectSerialInterface("/dev/ttyACM0")
interface.wait_connected(5)
node = Node(Address("02.01.57.FF.00.01"), interface,
            snip=SimpleNodeInfo("Me", "My tool", "", "1.0"))
```

Both interfaces read in a background thread and reconnect by themselves; the
node claims a fresh alias every time the link comes back.

## A node that claims its alias and talks back

`Node` claims its alias with the CID/RID/AMD handshake before announcing
itself, answers Verify Node ID, Alias Mapping Enquiry, Protocol Support
Inquiry, SNIP requests and Identify Events, and works as a client:

```python
node.send_global(0x490)                          # Verify Node ID: everyone answers
info = node.simple_node_info(0x020157000099)     # SimpleNodeInfo(manufacturer=..., model=..., ...)
protocols = node.protocol_support_inquiry(0x020157000099).names()
node.produce_event(0x0201570000010100)
node.add_frame_listener(lambda frame, outgoing: print(frame))
```

## Memory Configuration and CDI

```python
from pyolcb import MemoryConfiguration, cdi

mc = MemoryConfiguration(node, 0x020157000099)
layout = cdi.parse(mc.read_cdi())
for field in layout.fields():
    raw = mc.read(field.space, field.address, field.size)
    print("/".join(field.path), field.decode(raw))
mc.write(0xFB, 1, b"Yard throat\0")              # the node's user name
mc.update_complete()
```

`cdi.parse` lays the CDI out the way configuration tools do (segment origins,
`offset` attributes, group replication with repnames, int/string/eventid/float
sizes and maps) and gives every field its absolute space and address, plus
`encode`/`decode` for its value.

## Modules

| Module | |
|---|---|
| `pyolcb.frame` | `Frame`, a transport-neutral CAN frame, with field access and builders |
| `pyolcb.gridconnect` | GridConnect text encoding, a tolerant stream parser, TCP and serial interfaces, mDNS browsing |
| `pyolcb.node` | `Node`: alias allocation, standard replies, addressed requests, datagrams |
| `pyolcb.memory_config` | Memory Configuration requests, replies and the `MemoryConfiguration` client |
| `pyolcb.cdi` | CDI parsing and layout |
| `pyolcb.snip` | Simple Node Information encoding and decoding |
| `pyolcb.protocols` | Protocol Support flags |

## Tests

`tests/test_frame.py`, `test_gridconnect.py`, `test_memory_config.py`,
`test_cdi.py` and `test_node_stack.py` run anywhere: they use an in-memory bus
(`tests/loopback.py`). `tests/test_node.py` needs python-can and a `vcan0`
interface (`tests/setup_vcan.sh`).
