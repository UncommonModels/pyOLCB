=====
Node
=====
The :class:`Node` is the building block of an OpenLCB/LCC network. Each :class:`Node` can communicate with any other :class:`Node` on the network by sending events or datagrams over the common bus. Each :class:`Node` object can be attached to an :class:`Interface` (or multiple) to allow for complex network architectures. Each :class:`Message` should originate from one :class:`Node`.

.. autoclass:: pyolcb.Node
    :members: