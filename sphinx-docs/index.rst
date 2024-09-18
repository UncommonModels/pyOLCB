.. toctree::
    :maxdepth: 2
    :hidden:
    
    Home <self>
    

=====================================================
pyOLCB
=====================================================
An unofficial Python implementation of the OpenLCB protocol.



Introduction
----------------

The pyOLCB package is designed to be an easy-to-use python implementation of OpenLCB (LCC) protocols, designed to interface with both CAN and TCP/IP implementations.


To install the latest version please run :code:`pip install pyOLCB`

Example Program
------------------
.. code-block::
    :linenos:

    from pyolcb import Node, Address, Event, Interface, InterfaceType

    address = Address(bytearray([0x05,0x01,0x01,0x01,0x8C,0x00]))


    node = Node(address)
    
    node.add_interface(Interface(InterfaceType.CAN))

    node.produce(Event(125))
    

Contact
------------
Please submit an issue if you encounter a bug and please email any questions or requests to pyOLCB@noahpaladino.com