==========
Interface
==========
The :class:`Interface` base class is intended to provide a wrapper around transport layer implementations (like TCP/IP or CAN), with the goal of making each :class:`Node` instance transport method agnostic.

.. autoclass:: pyolcb.Interface
    :members: