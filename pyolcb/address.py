from . import utilities


class Address:
    full = None
    alias = None

    def __init__(self, address: utilities.byte_options = None, alias: utilities.byte_options = None) -> None:
        if not address is None:
            self.full = utilities.process_bytes(6, address)
        if not alias is None:
            self.alias = utilities.process_bytes(3, alias)

    def __str__(self):
        return ".".join(format(x, '02x') for x in self.full)

    def __iter__(self):
        return iter(self.full)

    def __int__(self) -> int:
        return int.from_bytes(self.full, 'big')

    def __eq__(self, x: object) -> bool:
        if self.alias == x.alias and self.full == x.full:
            return True
        elif (self.alias is None or x.alias is None) and self.full == x.full:
            return True
        elif (self.full is None or x.full is None) and self.alias == x.alias:
            return True
        else:
            return False

    def has_alias(self) -> bool:
        if self.alias is None:
            return False
        else:
            return True

    def has_address(self) -> bool:
        if self.full is None:
            return False
        else:
            return True

    def get_alias(self) -> bytes:
        if self.has_alias():
            return self.alias
        else:
            raise Exception("No alias has been set for this address")

    def get_alias_int(self) -> int:
        if self.has_alias():
            return int.from_bytes(self.alias, 'big')
        else:
            raise Exception("No alias has been set for this address")

    def set_alias(self, alias: utilities.byte_options) -> bytes:
        self.alias = utilities.process_bytes(3, alias)
        return self.alias

    def get_full_address(self) -> bytes:
        if self.has_address():
            return self.full
        else:
            raise Exception("No full address has been set for this address")

    def set_full_address(self, address: utilities.byte_options) -> bytes:
        self.full = utilities.process_bytes(3, address)
        return self.full

