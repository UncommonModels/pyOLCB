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


def to_gridconnect(arbitration_id: int, data: bytes, is_extended: bool = True) -> str:
    """
    Convert a CAN message to GridConnect ASCII format.
    
    Parameters
    ----------
    arbitration_id : int
        The CAN arbitration ID
    data : bytes
        The message data payload
    is_extended : bool
        Whether this is an extended CAN frame (default: True)
    
    Returns
    -------
    str
        GridConnect formatted string (e.g., ':X195B4123N0102030405060708;')
    """
    frame_type = 'X' if is_extended else 'S'
    id_width = 8 if is_extended else 3
    id_hex = format(arbitration_id, f'0{id_width}X')
    data_hex = ''.join(format(b, '02X') for b in data) if data else ''
    return f':{frame_type}{id_hex}N{data_hex};'


def from_gridconnect(frame: str) -> tuple[int, bytes, bool] | None:
    """
    Parse a GridConnect ASCII format frame into CAN message components.
    
    Parameters
    ----------
    frame : str
        GridConnect formatted string
    
    Returns
    -------
    tuple[int, bytes, bool] | None
        A tuple of (arbitration_id, data, is_extended) or None if parsing fails
    """
    frame = frame.strip()
    
    # Check basic frame structure
    if not frame.startswith(':') or not frame.endswith(';'):
        return None
    
    # Remove delimiters
    frame = frame[1:-1]
    
    # Check frame type
    if not frame or frame[0] not in ['X', 'S']:
        return None
    
    is_extended = (frame[0] == 'X')
    frame = frame[1:]
    
    # Find the 'N' separator
    n_pos = frame.find('N')
    if n_pos == -1:
        return None
    
    # Parse arbitration ID
    id_str = frame[:n_pos]
    try:
        arbitration_id = int(id_str, 16)
    except ValueError:
        return None
    
    # Parse data bytes
    data_str = frame[n_pos+1:]
    if len(data_str) % 2 != 0:
        return None
    
    try:
        data = bytes(int(data_str[i:i+2], 16) for i in range(0, len(data_str), 2))
    except ValueError:
        return None
    
    return (arbitration_id, data, is_extended)
