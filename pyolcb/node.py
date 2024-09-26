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
        An :class:`Interface` or list thereof to connect the :class:`Node` to.
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
            An :class:`Interface` or list thereof to attach the :class:`Node` to.
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
        int
            Returns the :class:`Node`'s alias as an :class:`int`.
        """
        if self.address.alias is None:
            raise Exception("Alias not set!")
        else:
            return self.address.get_alias()

    def set_alias(self, alias: utilities.byte_options):
        return self.address.set_alias(alias)

    def send(self, messages: Message | list[Message]):
        """
        Send a :class:`Message` (or sequence thereof) from this :class:`Node` on all registered interfaces.

        Parameters
        ----------
        messages : Message | list[Message]
            The :class:`Message` (or ordered list thereof) to send
        """
        if isinstance(messages, Message):
            messages = [messages]

        if len(self.interfaces) > 0:
            return [[i.send(m) for m in messages] for i in self.interfaces]
        else:
            raise Exception("No interfaces to send message on")

    def produce(self, event: int | Event):
        """
        Produce an :class:`Event` and send the resulting message on all interfaces.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to produce and send. By default, if an :class:`int` is provided for 
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
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

    def add_consumer(self, event: Event | int, function: callable):
        """
        Register a callable function to be run on receipt of a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for 
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        function : callable
            The function to be called upon receipt of the specified :class:`Event`. Must be able to take no parameters.
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                event = Event(event)
            else:
                event = Event(event, self.address)
        if not event in self.consumers:
            self.consumers[event] = function
            return self.consumers
        else:
            raise Exception("Consumer already registered")

    def remove_consumer(self, event: Event | int):
        """
        Deregister the callable function to be run on receipt of a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for 
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                event = Event(event)
            else:
                event = Event(event, self.address)
        if event in self.consumers:
            del self.consumers[event]
        return self.consumers

    def replace_consumer(self, event: Event | int, function: callable):
        """
        Replace a callable function that is run on receipt of a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for 
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.
        function : callable
            The function to be called upon receipt of the specified :class:`Event`. Must be able to take no parameters.
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                event = Event(event)
            else:
                event = Event(event, self.address)
        self.remove_consumer(event)
        return self.add_consumer(event, function)

    def run_consumer(self, event: Event | int):
        """
        Run the consumer for a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for 
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.

        Returns
        -------
        any
            Returns what the registered consumer function returns.
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                event = Event(event)
            else:
                event = Event(event, self.address)
        if event in self.consumers:
            return self.consumers[event]()
        else:
            raise Exception("Consumer not registered")

    def get_consumer(self, event: Event | int):
        """
        Run the consumer for a specific :class:`Event`.

        Parameters
        ----------
        event : int | Event
            The ID or :class:`Event` to consume. By default, if an :class:`int` is provided for 
            this parameter, and the (unsigned) value fits within two bytes, the :class:`Event` will be tagged
            with the address of the :class:`Node`. This behavior can be overridden by passing an :class:`Event`
            object with no source address.

        Returns
        -------
        callable
            Returns the registered consumer function.
        """
        if isinstance(event, int):
            if event < 0:
                raise Exception("Invalid Event")
            elif event > 2**16:
                event = Event(event)
            else:
                event = Event(event, self.address)
        if event in self.consumers:
            return self.consumers[event]
        else:
            raise Exception("Consumer not registered")

    def verify_node_id(self, address: Address | int = None):
        """
        Send a request to verify aliases on an OpenLCB/LCC network.

        Parameters
        ----------
        address : Address | int = None
            If specified, only request a response for a :class:`Node` with a given alias. Otherwise, 
            request responses from each :class:`Node` attached to all registered interfaces.

        """
        if not address is None:
            if isinstance(address, Address):
                address = address.get_alias()
            return self.send(Message(message_types.Verify_Node_ID_Number_Addressed, utilities.process_bytes(2, address), self.address, address))
        else:
            return self.send(Message(message_types.Verify_Node_ID_Number_Global, bytes(self.address), self.address))

    def verified_node_id(self):
        """
        Respond to a request to verify aliases on an OpenLCB/LCC network.
        """
        return self.send(Message(message_types.Verified_Node_ID_Number, bytes(self.address), self.address))

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
