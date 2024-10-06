
.. toctree::
    :maxdepth: 2
    :hidden:
    
    Home <self>
    examples

.. toctree::
    :hidden:
    :glob:
    :caption: API Reference

    node
    message
    interface


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

    from pyolcb import Node, Address, Event, Interface
    import can

    address = Address('05.01.01.01.8C.00')
    interface = Interface(can.Bus(interface='socketcan', channel='vcan0', bitrate=125000))

    node = Node(address, interface)
    
    node.produce(Event(125))
    

Contact
------------
Source code is available on `Github <https://github.com/UncommonModels/pyOLCB>`_

Please submit an `issue <https://github.com/UncommonModels/pyOLCB/issue>`_ if you encounter a bug and please email any questions or requests to pyOLCB@uncommonmodels.com
