



========
Message
========
The :class:`Message` base class is intended to provide a wrapper around message class implementations independent of transport layer (like TCP/IP or CAN).

.. autoclass:: pyolcb.Message
    :members:


Event
---------
.. autoclass:: pyolcb.Event
    :members:

Datagram
---------
.. autoclass:: pyolcb.Datagram
    :members:


Message Types
-------------
The :class:`message_types` module contains all currently defined message types, packaged into a :class:`MessageTypeIndicator` class to properly handle different :class:`Interface` types.

.. automodule:: pyolcb.message_types
    :members: