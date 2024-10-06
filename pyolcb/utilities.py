import math


def process_bytes(n: int | float, x: str | list[int] | int | bytes | bytearray):
    if isinstance(n, float):
        n = math.ceil(n)
    if isinstance(x, str) and len(x.replace('.', ' ').replace(',', ' ').replace(';', ' ').replace(':', ' ').split()) == n:
        return bytes([int("0x%s" % str(y), 16) for y in x.split('.')])
    if isinstance(x, list) and len(x) == n:
        return bytes([int(y) for y in x])
    if isinstance(x, int) and x >= 0 and x < 2**(n*8):
        return x.to_bytes(n, 'big')
    if isinstance(x, bytes) and len(x) == n:
        return bytes(x)
    if isinstance(x, bytearray) and len(x) == n:
        return bytes(x)

    raise Exception(
        "Invalid bytes format, could not be read as %d bytes" % n)


byte_options = str | list[int] | int | bytes | bytearray
