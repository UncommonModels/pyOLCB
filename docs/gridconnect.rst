===========
GridConnect
===========
GridConnect carries CAN frames as text, ``:X19490ABCN;``, over TCP (port 12021,
advertised over mDNS as ``_openlcb-can._tcp``) and serial links. The
interfaces here read in a background thread, reconnect by themselves when the
link drops, and deliver :class:`pyolcb.frame.Frame` objects to their listeners.

.. code-block:: python

    from pyolcb import Node, Address, GridConnectTcpInterface

    interface = GridConnectTcpInterface("femtolcc-0001.local", 12021)
    interface.wait_connected(5)
    node = Node(Address("02.01.57.FF.00.01"), interface)

.. automodule:: pyolcb.gridconnect
    :members:

Frames
------
.. automodule:: pyolcb.frame
    :members:
