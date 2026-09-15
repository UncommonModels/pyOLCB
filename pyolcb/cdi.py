"""
==============
cdi
==============

Configuration Description Information: the XML a node serves from memory space
0xFF to describe its configuration memory.

:func:`parse` turns the XML into a layout tree in which every field carries
its absolute memory space and address, with group replication expanded::

    layout = cdi.parse(xml)
    for field in layout.fields():
        print(field.path, field.space, hex(field.address), field.size)

Layout rules, per the OpenLCB CDI standard:

* A ``<segment>`` sets the memory ``space`` and starts at its ``origin`` (default 0).
* Any element may have an ``offset`` attribute: bytes skipped (or, if negative,
  backed up) before the element.
* A ``<group>`` is as large as its contents; with ``replication`` N it is laid
  out N times back to back, each copy named from its ``<repname>`` plus a number.
* ``<int>`` is 1, 2, 4 or 8 bytes (default 1), big-endian, with optional
  ``<min>``, ``<max>``, ``<default>`` and a ``<map>`` of named values.
* ``<string>`` has a ``size`` and holds NUL-terminated UTF-8.
* ``<eventid>`` is always 8 bytes.
* ``<float>`` is 2, 4 or 8 bytes (default 4), IEEE 754 big-endian.
* ``<action>`` (a button that writes ``<value>``) and ``<blob>`` take ``size`` bytes.
"""

import struct
import xml.etree.ElementTree as ET

LEAF_TYPES = ("int", "string", "eventid", "float", "action", "blob")
DEFAULT_SIZES = {"int": 1, "eventid": 8, "float": 4}


def _tag(element) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child_text(element, name: str) -> str | None:
    for child in element:
        if _tag(child) == name:
            return (child.text or "").strip()
    return None


def _int_attr(element, name: str, default: int) -> int:
    value = element.get(name)
    if value is None or value.strip() == "":
        return default
    return int(value.strip(), 0)


def _number(text: str | None, as_float: bool):
    if text is None or text == "":
        return None
    try:
        return float(text) if as_float else int(text, 0)
    except ValueError:
        return None


class Field:
    """
    One configurable value at a fixed place in a node's memory.

    Attributes
    ----------
    kind : str
        ``int``, ``string``, ``eventid``, ``float``, ``action`` or ``blob``.
    name, description : str
    space, address, size : int
        Where the value lives.
    path : list[str]
        Names of the enclosing segment and groups, then the field's own name.
    minimum, maximum, default : int | float | None
    map : list[tuple[str, str]]
        ``(property, label)`` pairs; an ``int`` with a map is a choice.
    """

    def __init__(self, kind, name, description, space, address, size, path,
                 minimum=None, maximum=None, default=None, map=None, hints=None,
                 button_text=None, dialog_text=None, value=None):
        self.kind = kind
        self.name = name
        self.description = description
        self.space = space
        self.address = address
        self.size = size
        self.path = path
        self.minimum = minimum
        self.maximum = maximum
        self.default = default
        self.map = map or []
        self.hints = hints or {}
        self.button_text = button_text
        self.dialog_text = dialog_text
        self.value = value

    def __repr__(self):
        return "Field(%s %r space=0x%02X address=0x%X size=%d)" % (
            self.kind, "/".join(self.path), self.space, self.address, self.size)

    def to_dict(self) -> dict:
        d = {"type": self.kind, "name": self.name, "description": self.description,
             "space": self.space, "address": self.address, "size": self.size,
             "path": self.path}
        if self.minimum is not None:
            d["min"] = self.minimum
        if self.maximum is not None:
            d["max"] = self.maximum
        if self.default is not None:
            d["default"] = self.default
        if self.map:
            d["map"] = [[p, v] for p, v in self.map]
        if self.hints:
            d["hints"] = self.hints
        if self.kind == "action":
            d["buttonText"] = self.button_text
            d["dialogText"] = self.dialog_text
            d["value"] = self.value
        return d

    # --- value codec -------------------------------------------------------

    def decode(self, data: bytes):
        """Turn the field's bytes into a Python value (int, str, float, or dotted-hex event ID)."""
        data = bytes(data)
        if self.kind == "int":
            return int.from_bytes(data[:self.size], "big")
        if self.kind == "string":
            return data[:self.size].split(b"\x00")[0].decode("utf-8", errors="replace")
        if self.kind == "eventid":
            return ".".join("%02X" % b for b in data[:8])
        if self.kind == "float":
            fmt = {2: ">e", 4: ">f", 8: ">d"}.get(self.size)
            return struct.unpack(fmt, data[:self.size])[0] if fmt else None
        return data[:self.size].hex().upper()

    def encode(self, value) -> bytes:
        """Turn a value back into exactly ``size`` bytes."""
        if self.kind == "int":
            value = int(value, 0) if isinstance(value, str) else int(value)
            if self.minimum is not None and value < self.minimum:
                raise ValueError("%s: %d is below the minimum %d" % (self.name, value, self.minimum))
            if self.maximum is not None and value > self.maximum:
                raise ValueError("%s: %d is above the maximum %d" % (self.name, value, self.maximum))
            return int(value).to_bytes(self.size, "big")
        if self.kind == "string":
            raw = str(value).encode("utf-8")[:max(self.size - 1, 0)]
            return raw + b"\x00" * (self.size - len(raw))
        if self.kind == "eventid":
            from .frame import parse_id
            return parse_id(value, 8).to_bytes(8, "big")
        if self.kind == "float":
            fmt = {2: ">e", 4: ">f", 8: ">d"}.get(self.size)
            return struct.pack(fmt, float(value))
        if self.kind == "action":
            return int(self.value or 0).to_bytes(self.size, "big")
        raise ValueError("cannot write a %s field" % self.kind)


class Group:
    """A named block of fields and groups; a replicated group has one :class:`Group` per copy."""

    def __init__(self, name, description, children, label=None, index=None):
        self.name = name
        self.description = description
        self.children = children
        self.label = label
        self.index = index

    def to_dict(self) -> dict:
        return {"type": "group", "name": self.name, "description": self.description,
                "label": self.label, "index": self.index,
                "children": [c.to_dict() for c in self.children]}


class Replicated:
    """A group with ``replication`` > 1: the copies, in memory order."""

    def __init__(self, name, description, replicas):
        self.name = name
        self.description = description
        self.replicas = replicas

    def to_dict(self) -> dict:
        return {"type": "replicated", "name": self.name, "description": self.description,
                "replicas": [r.to_dict() for r in self.replicas]}


class Segment:
    """One ``<segment>``: fields in a single memory space."""

    def __init__(self, space, origin, name, description, children, end):
        self.space = space
        self.origin = origin
        self.name = name
        self.description = description
        self.children = children
        self.end = end

    @property
    def size(self) -> int:
        return self.end - self.origin

    def to_dict(self) -> dict:
        return {"type": "segment", "space": self.space, "origin": self.origin, "size": self.size,
                "name": self.name, "description": self.description,
                "children": [c.to_dict() for c in self.children]}


class Cdi:
    """A parsed CDI document."""

    def __init__(self, identification: dict, acdi: bool, segments: list[Segment]):
        self.identification = identification
        self.acdi = acdi
        self.segments = segments

    def fields(self) -> list[Field]:
        """Every field in memory order, replication expanded."""
        out = []

        def walk(items):
            for item in items:
                if isinstance(item, Field):
                    out.append(item)
                elif isinstance(item, Group):
                    walk(item.children)
                elif isinstance(item, Replicated):
                    walk(item.replicas)
        for segment in self.segments:
            walk(segment.children)
        return out

    def ranges(self) -> list[tuple[int, int, int]]:
        """``(space, start, length)`` spans covering every field, merged where they touch."""
        spans = {}
        for f in self.fields():
            spans.setdefault(f.space, []).append((f.address, f.address + f.size))
        out = []
        for space, items in spans.items():
            items.sort()
            start, end = items[0]
            for a, b in items[1:]:
                if a <= end:
                    end = max(end, b)
                else:
                    out.append((space, start, end - start))
                    start, end = a, b
            out.append((space, start, end - start))
        return out

    def to_dict(self) -> dict:
        return {"identification": self.identification, "acdi": self.acdi,
                "segments": [s.to_dict() for s in self.segments]}


def _repname(repnames: list[str], name: str, index: int, count: int) -> str:
    if len(repnames) > 1 and index < len(repnames) - 1:
        return repnames[index]
    if len(repnames) > 1 and len(repnames) == count:
        return repnames[index]
    base = repnames[-1] if repnames else (name or "Group")
    return "%s %d" % (base, index + 1)


def _layout(elements, space: int, position: int, path: list[str]):
    """Lay out ``elements`` starting at ``position``; returns (items, end position)."""
    items = []
    for element in elements:
        kind = _tag(element)
        if kind not in LEAF_TYPES and kind != "group":
            continue
        position += _int_attr(element, "offset", 0)
        name = _child_text(element, "name") or ""
        description = _child_text(element, "description") or ""
        if kind == "group":
            replication = max(1, _int_attr(element, "replication", 1))
            repnames = [(c.text or "").strip() for c in element if _tag(c) == "repname"]
            children = [c for c in element if _tag(c) in LEAF_TYPES or _tag(c) == "group"]
            group_path = path + ([name] if name else [])
            if replication == 1:
                inner, position = _layout(children, space, position, group_path)
                items.append(Group(name, description, inner))
                continue
            replicas = []
            for index in range(replication):
                label = _repname(repnames, name, index, replication)
                inner, position = _layout(children, space, position, group_path + [label])
                replicas.append(Group(name, description, inner, label=label, index=index))
            items.append(Replicated(name, description, replicas))
            continue

        size = _int_attr(element, "size", DEFAULT_SIZES.get(kind, 0))
        if kind == "eventid":
            size = 8
        if kind in ("string", "action", "blob") and size <= 0:
            raise ValueError("<%s> %r needs a size" % (kind, name))
        if kind == "int" and size not in (1, 2, 4, 8):
            raise ValueError("<int> %r has invalid size %d" % (name, size))
        if kind == "float" and size not in (2, 4, 8):
            raise ValueError("<float> %r has invalid size %d" % (name, size))
        is_float = kind == "float"
        mapping = []
        for child in element:
            if _tag(child) == "map":
                for relation in child:
                    if _tag(relation) == "relation":
                        mapping.append((_child_text(relation, "property") or "",
                                        _child_text(relation, "value") or ""))
        hints = {}
        for child in element:
            if _tag(child) == "hints":
                for hint in child:
                    hints[_tag(hint)] = dict(hint.attrib)
        items.append(Field(
            kind, name, description, space, position, size, path + [name],
            minimum=_number(_child_text(element, "min"), is_float),
            maximum=_number(_child_text(element, "max"), is_float),
            default=_number(_child_text(element, "default"), is_float)
            if kind in ("int", "float") else _child_text(element, "default"),
            map=mapping, hints=hints,
            button_text=_child_text(element, "buttonText"),
            dialog_text=_child_text(element, "dialogText"),
            value=_number(_child_text(element, "value"), False)))
        position += size
    return items, position


def parse(xml: str | bytes) -> Cdi:
    """Parse CDI XML into a :class:`Cdi` layout. Raises ``ValueError`` on malformed input."""
    if isinstance(xml, (bytes, bytearray)):
        xml = bytes(xml).split(b"\x00")[0].decode("utf-8", errors="replace")
    else:
        xml = xml.split("\x00")[0]
    try:
        root = ET.fromstring(xml.strip())
    except ET.ParseError as e:
        raise ValueError("CDI is not well-formed XML: %s" % e)
    if _tag(root) != "cdi":
        raise ValueError("CDI root element is <%s>, not <cdi>" % _tag(root))
    identification = {}
    acdi = False
    segments = []
    for element in root:
        kind = _tag(element)
        if kind == "identification":
            for child in element:
                if _tag(child) != "map":
                    identification[_tag(child)] = (child.text or "").strip()
        elif kind == "acdi":
            acdi = True
        elif kind == "segment":
            space = _int_attr(element, "space", -1)
            if not 0 <= space <= 255:
                raise ValueError("<segment> without a valid space")
            origin = _int_attr(element, "origin", 0)
            name = _child_text(element, "name") or ""
            children, end = _layout(list(element), space, origin, [name] if name else [])
            segments.append(Segment(space, origin, name, _child_text(element, "description") or "",
                                    children, end))
    return Cdi(identification, acdi, segments)
