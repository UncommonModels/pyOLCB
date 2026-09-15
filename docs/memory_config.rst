=========================
Memory Configuration & CDI
=========================
Read and write a node's configuration, CDI and identity through Memory
Configuration datagrams, and lay out its CDI.

.. code-block:: python

    from pyolcb import MemoryConfiguration, cdi

    mc = MemoryConfiguration(node, 0x020157000099)
    layout = cdi.parse(mc.read_cdi())
    for field in layout.fields():
        print("/".join(field.path), field.decode(mc.read(field.space, field.address, field.size)))
    mc.write(0xFB, 1, b"Yard throat\0")
    mc.update_complete()

.. automodule:: pyolcb.memory_config
    :members:

CDI
---
.. automodule:: pyolcb.cdi
    :members:

Simple Node Information
-----------------------
.. automodule:: pyolcb.snip
    :members:
