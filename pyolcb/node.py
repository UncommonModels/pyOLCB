"""
==============
node
==============

"""


from .address import Address
from .interface import Interface
from .message import Message
from .event import Event
from .datagram import Datagram
from . import utilities, message_types, protocols


class Node:
    """
    The :class:`Node` is the building block of an OpenLCB/LCC network. Each :class:`Node` can communicate
    with any other :class:`Node` on the network by sending events or datagrams over the common bus. Each 
    :class:`Node` object can be attached to an :class:`Interface` (or multiple) to allow for complex network 
    architectures. Each :class:`Message` should originate from one :class:`Node` .

    Parameters
    ----------
    address : Address
        The address (full and alias) to be associated with the :class:`Node`.
    interfaces : int, Interface | list[Interface]
        An :class:`Interface` or list therof to connect the :class:`Node` to.
    """
    address = None
    supported_protocols = protocols.Protocol()
    interfaces = []
    consumers = {}
    datagram_handler = None
    simple = False

    def __init__(self, address: Address, interfaces: Interface | list[Interface]):
        """
        Initialize the :class:`Node` object.

        Parameters
        ----------
        address : Address
            The address (full and alias) to be associated with the :class:`Node`.
        interfaces : int, Interface | list[Interface]
            An :class:`Interface` or list therof to attach the :class:`Node` to.
        """
        self.address = address
        if not self.address.has_alias():
            if self.address.alias is None:
                self.address.set_alias(
                    self.address.get_full_address() & 0xFFF)  # temporary

        if isinstance(interfaces, Interface):
            self.interfaces.append(interfaces)
            self.interfaces[-1].register_connected_device(self.address)
        elif isinstance(interfaces, list) and all(isinstance(x, Interface) for x in interfaces):
            self.interfaces += interfaces
            for i in self.interfaces[-len(interfaces):]:
                i.register_connected_device(self.address)
        else:
            raise Exception("No Interfaces to attach to")

        if not self.simple:
            self.send(Message(message_types.Initialization_Complete,
                      bytes(self.address), self.address))
        else:
            self.send(Message(message_types.Initialization_Complete_Simple, bytes(
                self.address), self.address))

    def get_alias(self) -> int:
        """
        Get the :class:`Node`'s alias.

        Returns
        -------
        Alias
            Returns the :class:`Node`'s alias as an `int`.
        """
        if self.address.alias is None:
            raise Exception("Alias not set!")
        else:
            return self.address.get_alias()

    def set_alias(self, alias: utilities.byte_options):
        return self.address.set_alias(alias)

    def send(self, messages: Message | list[Message], interfaces: Interface | list[Interface] = None):

        if isinstance(messages, Message):
            messages = [messages]

        if interfaces is None:
            interfaces = self.interfaces

        if isinstance(interfaces, Interface):
            interfaces = [interfaces]

        if len(interfaces) > 0:
            return [[i.send(m) for m in messages] for i in interfaces]
        else:
            raise Exception("No interfaces to send message on")

    def produce(self, event: int | Event):
        """
        Produce an :class:`Event` and send the resulting message. By default, 
        if an `int` is provided for the `event` parameter, and the (unsigned) value fits within two bytes,
        the event will be tagged with the address of the :class:`Node`. This behavior can be overridden by 
        passing an :class:`Event` object with no source address.

        Parameters
        ----------
        event : int | Event
            The event to produce
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                return self.send(Event(event))
            else:
                return self.send(Event(event, self.address))
        elif isinstance(event, Event):
            return self.send(event)
        else:
            raise Exception("Invalid event")

    def add_consumer(self, event: Event, function: callable):
        if not event in self.consumers:
            self.consumers[event] = function
            return self.consumers
        else:
            raise Exception("Consumer already registered")

    def remove_consumer(self, event: Event):
        if event in self.consumers:
            del self.consumers[event]
        return self.consumers

    def replace_consumer(self, event: Event, function: callable):
        self.remove_consumer(event)
        return self.add_consumer(event, function)

    def run_consumer(self, event: Event):
        if event in self.consumers:
            return self.consumers[event]()
        else:
            raise Exception("Consumer not registered")

    def get_consumer(self, event: Event):
        if event in self.consumers:
            return self.consumers[event]
        else:
            raise Exception("Consumer not registered")

    def verify_node_id(self, address: Address = None):
        if not address is None:
            return self.send(Message(message_types.Verify_Node_ID_Number_Addressed, utilities.process_bytes(2, address.get_alias()), self.address, address))
        else:
            return self.send(Message(message_types.Verify_Node_ID_Number_Global, bytes(self.address), self.address))

    def verified_node_id(self, interface: Interface = None):
        return self.send(Message(message_types.Verified_Node_ID_Number, bytes(self.address), self.address), interface)

    def add_supported_protocol(self, protocol: protocols.Protocol):
        self.supported_protocols += protocol
        return self.supported_protocols

    def get_supported_protocols(self):
        return self.supported_protocols

    def protocol_support_inqury(self, interface: Interface = None):
        pass

    def protocol_support_reply(self, interface: Interface = None):
        pass

    # def set_datagram_handler(self, datagram_handler: callable[Datagram]):


class SimpleNode(Node):
    simple = True
    supported_protocols = protocols.Simple_Protocol_Subset

    def __init__(self, address: Address, interfaces: Interface | list[Interface]):
        super().__init__(address, interfaces)
