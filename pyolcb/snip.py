"""
==============
snip
==============

Simple Node Information Protocol (SNIP): the identity strings a node reports
in reply to a Simple Node Ident Info Request.

The reply is a version byte (4), manufacturer, model, hardware version and
software version as NUL-terminated strings, a second version byte (2), then the
user-assigned name and description. Older nodes send version 1 in either
place; both are accepted.
"""

MANUFACTURER_MAX = 40
MODEL_MAX = 40
HARDWARE_VERSION_MAX = 20
SOFTWARE_VERSION_MAX = 20
USER_NAME_MAX = 62
USER_DESCRIPTION_MAX = 63


class SimpleNodeInfo:
    """
    The identity of a node.

    Parameters
    ----------
    manufacturer, model, hardware_version, software_version : str
        Fixed at build time by the node's maker.
    user_name, user_description : str
        Set by the user through Memory Configuration space 0xFB.
    """

    FIELDS = ("manufacturer", "model", "hardware_version", "software_version",
              "user_name", "user_description")

    def __init__(self, manufacturer: str = "", model: str = "", hardware_version: str = "",
                 software_version: str = "", user_name: str = "", user_description: str = ""):
        self.manufacturer = manufacturer
        self.model = model
        self.hardware_version = hardware_version
        self.software_version = software_version
        self.user_name = user_name
        self.user_description = user_description

    def __eq__(self, o) -> bool:
        return isinstance(o, SimpleNodeInfo) and self.to_dict() == o.to_dict()

    def __repr__(self):
        return "SimpleNodeInfo(%s)" % ", ".join("%s=%r" % (f, getattr(self, f)) for f in self.FIELDS)

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in self.FIELDS}

    @classmethod
    def from_bytes(cls, data: bytes) -> "SimpleNodeInfo":
        """Decode a SNIP reply payload, tolerating short or truncated replies."""
        data = bytes(data)
        strings = []
        pos = 0
        if pos < len(data):
            pos += 1   # manufacturer block version
        for _ in range(4):
            end = data.find(b"\x00", pos)
            if end < 0:
                end = len(data)
            strings.append(data[pos:end])
            pos = end + 1
        if pos < len(data):
            pos += 1   # user block version
        for _ in range(2):
            if pos >= len(data):
                strings.append(b"")
                continue
            end = data.find(b"\x00", pos)
            if end < 0:
                end = len(data)
            strings.append(data[pos:end])
            pos = end + 1
        return cls(*(s.decode("utf-8", errors="replace") for s in strings))

    def to_bytes(self) -> bytes:
        """Encode as a SNIP reply payload."""
        def field(text, limit):
            return text.encode("utf-8")[:limit] + b"\x00"
        return (b"\x04" + field(self.manufacturer, MANUFACTURER_MAX) + field(self.model, MODEL_MAX)
                + field(self.hardware_version, HARDWARE_VERSION_MAX)
                + field(self.software_version, SOFTWARE_VERSION_MAX)
                + b"\x02" + field(self.user_name, USER_NAME_MAX)
                + field(self.user_description, USER_DESCRIPTION_MAX))
