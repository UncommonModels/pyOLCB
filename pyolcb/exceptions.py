"""
==============
exceptions
==============

Errors raised by pyOLCB's request/response helpers.
"""


class OlcbError(Exception):
    """Base class for OpenLCB protocol errors."""


class NotPermittedError(OlcbError):
    """The node has not (yet) claimed an alias, so it may not send messages."""


class ReplyTimeout(OlcbError, TimeoutError):
    """The remote node did not answer in time."""


class UnknownNodeError(OlcbError):
    """No alias is known for the requested node ID and none could be found."""


class RejectedError(OlcbError):
    """
    The remote node refused a message.

    Attributes
    ----------
    code : int
        The OpenLCB error code (bit 0x1000 permanent, 0x2000 temporary).
    """

    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code

    @property
    def temporary(self) -> bool:
        return bool(self.code & 0x2000)


class InteractionRejected(RejectedError):
    """Optional Interaction Rejected or Terminate Due To Error."""


class DatagramRejected(RejectedError):
    """Datagram Rejected."""


class MemoryConfigError(RejectedError):
    """A Memory Configuration read or write failed on the remote node."""
