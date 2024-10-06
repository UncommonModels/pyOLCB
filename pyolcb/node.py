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
from . import utilities, message_types, protocols, exceptions
import can


class Node:
    """
    Implementation of an OpenLCB/LCC :class:`Node`.

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
    datagram_handler = lambda *args: None
    unknown_message_processor = lambda *args: None
    simple = False
    _datagram_queue = {}

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
        elif isinstance(interfaces, list) and all(isinstance(x, Interface) for x in interfaces):
            self.interfaces += interfaces
        else:
            raise Exception("No Interfaces to attach to")

        if not self.simple:
            self.send(Message(message_types.Initialization_Complete,
                      bytes(self.address), self.address))
        else:
            self.send(Message(message_types.Initialization_Complete_Simple, bytes(
                self.address), self.address))

        for interface in self.interfaces:
            interface.register_connected_device(self.address)
            interface.register_listener(self.process_message)

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
        Register a function to be run on receipt of a specific :class:`Event`.

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
        if not event.id in self.consumers:
            self.consumers[event.id] = function
            return self.consumers
        else:
            raise Exception("Consumer already registered")

    def remove_consumer(self, event: Event | int):
        """
        Deregister the function to be run on receipt of a specific :class:`Event`.

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
        if event.id in self.consumers:
            del self.consumers[event.id]
        return self.consumers

    def replace_consumer(self, event: Event | int, function: callable):
        """
        Replace a function that is run on receipt of a specific :class:`Event`.

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

    def consume(self, event: Event | int):
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
        if event.id in self.consumers:
            return self.consumers[event.id]()
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
        if event.id in self.consumers:
            return self.consumers[event.id]
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

    def set_datagram_handler(self, datagram_handler: callable):
        """
        Register a function to be run on receipt of a :class:`Datagram`.

        Parameters
        ----------
        datagram_handler : callable
            The function to be called upon receipt of a :class:`Datagram` packet. Must take a :class:`Datagram` as the first parameter.
        """
        self.datagram_handler = datagram_handler
        return self.datagram_handler

    def set_unknown_message_processor(self, function: callable):
        """
        Register a function to be run on receipt of a message of unknown type.

        Parameters
        ----------
        function : callable
            The function to be called upon receipt of an unknown message. Must take a :class:`Message` as the first parameter.
        """
        self.unknown_message_processor = function
        return self.unknown_message_processor

    def process_message(self, message):
        if isinstance(message, can.Message):
            converted_message = Message.from_can_message(message)
        else:
            raise NotImplementedError()

        match converted_message.message_type:
            case message_types.Verify_Node_ID_Number_Addressed:
                if converted_message.data == self.address.get_alias_bytes():
                    self.verified_node_id()
                    return
            case message_types.Verify_Node_ID_Number_Global:
                self.verified_node_id()
                return
            case message_types.Producer_Consumer_Event_Report:
                event = Event(converted_message.data)
                if event.id in self.consumers:
                    self.consumers[event.id](converted_message)
            case message_types.Datagram:
                if converted_message.destination == self.address:
                    match converted_message.frame_id:
                        case None:
                            Datagram.from_message_list(converted_message)
                        case 1:
                            self._datagram_queue[converted_message.source.alias] = []
                            self._datagram_queue[converted_message.source.alias].append(
                                converted_message)
                        case -1:
                            self._datagram_queue[converted_message.source.alias].append(
                                converted_message)
                            self.datagram_handler(Datagram.from_message_list(
                                self._datagram_queue[converted_message.source.alias]))
                            self._datagram_queue[converted_message.source.alias] = []
                        case _:
                            self._datagram_queue[converted_message.source.alias].append(
                                converted_message)
            case _:
                self.unknown_message_processor(converted_message)


class SimpleNode(Node):
    simple = True
    supported_protocols = protocols.Simple_Protocol_Subset

    def __init__(self, address: Address, interfaces: Interface | list[Interface]):
        super().__init__(address, interfaces)
