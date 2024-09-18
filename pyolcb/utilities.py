def process_bytes(n:int, x: str | list[int] | int | bytes | bytearray):
    if isinstance(x,str) and len(x.split('.')) == n:
        return bytes([ int("0x%s" % str(y), 16) for y in x.split('.')])
    elif isinstance(x, list) and len(x) == n:
        return bytes([ int(y) for y in x])
    elif isinstance(x, int) and x >= 0 and x <= 0xFFFFFFFFFFFF:
        return x.to_bytes(n, 'big')
    elif isinstance(x, bytes) and len(x) == n:
        return bytes(x)
    elif isinstance(x, bytearray) and len(x) == n:
        return bytes(x)
    else:
        raise Exception("Invalid bytes format, could not be read as %d bytes" % n)
    
byte_options = str | list[int] | int | bytes | bytearray
