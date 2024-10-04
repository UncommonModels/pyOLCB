=====================================================
Examples
=====================================================


Initialize a Node
-------------------
.. code-block::
    :linenos:

    from pyolcb import Node, Address, Event, Interface
    import can

    address = Address('05.01.01.01.8C.00')
    interface = Interface(can.Bus(interface='socketcan', channel='vcan0', bitrate=125000))

    node = Node(address, interface)
    

Produce an Event
-------------------
.. code-block::
    node.produce(Event(125))

Consume an Event
-------------------
.. code-block::
    def my_event_consumer(message:pyolcb.Message = None, *args, **kwargs):
        print("Hi! I received an Event!")
        
    node.add_consumer(1, event_processor)

Send a Datagram
-------------------
Coming Soon

Process a Datagram
-------------------
Coming Soon