=====================================================
Examples
=====================================================


Initialize a Node
-------------------
.. code-block:: python

    from pyolcb import Node, Address, Event, Interface, Datagram
    import can

    address = Address('05.01.01.01.8C.00', 0xC00)
    interface = Interface(can.Bus(interface='socketcan', channel='vcan0', bitrate=125000))

    node = Node(address, interface)
    

Produce an Event
-------------------
To send event `00.00.00.00.00.00.01.25`:

.. code-block:: python

    node.produce(Event(0x125))

Alternatively, if we want the event to be tagged with the device address (`05.01.01.01.8C.00.01.25`), use:

.. code-block:: python

    node.produce(0x125)

or

.. code-block:: python

    node.produce(Event(0x125, node.address))

Consume an Event
-------------------
.. code-block:: python
    
    def my_event_consumer(message:Message = None, *args, **kwargs):
        print("Hi! I received Event %s!" % ".".join(format(x, '02x') for x in message.data))

    node.add_consumer(0x125, my_event_consumer)

Send a Datagram
-------------------
.. code-block:: python
    
    datagram = Datagram(bytearray([0x00, 0x11, 0x00]), node.address, Address('05.01.01.01.8C.01', 0xC01))

    node.send(datagram.as_message_list())

Process a Datagram
-------------------
.. code-block:: python
    
    def my_datagram_handler(datagram:Datagram = None, *args, **kwargs):
        print("Hi! I received a Datagram with content: %s" 
                % ".".join(format(x, '02x') for x in datagram.data))

    node.set_datagram_handler(my_datagram_handler)