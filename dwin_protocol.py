"""Length-aware T5UIC1 framing shared by the UI and auxiliary UART broker.

Payloads may contain AA or the complete trailer. Never split on delimiters
inside a payload: memory replies and auxiliary uploads carry explicit lengths.
"""

HEADER = b'\xaa'
TAIL = b'\xcc\x33\xc3\x3c'
MAX_DATA_LENGTH = 248
FIXED_RX_PAYLOAD = {0x00: 2, 0x31: 3, 0x33: 2, 0x34: 2, 0xff: 1}


def aux_frames(data):
    """Frame binary TX without copying the unconsumed tail on every chunk."""
    offset = 0
    while offset < len(data):
        end = min(offset + MAX_DATA_LENGTH, len(data))
        marker = data.find(TAIL, offset, end)
        if marker >= 0:
            end = marker + len(TAIL) - 1
        yield b'\xaa\x39' + data[offset:end] + TAIL
        offset = end


def take_response(buffer):
    """Remove one complete valid inbound frame, or return None for partial RX.

    Mutates the caller-owned bytearray, preserving incomplete frames. Discards
    noise/unknown opcodes and resynchronizes after a malformed trailer.
    """
    while True:
        start = buffer.find(HEADER)
        if start < 0:
            buffer.clear()
            return None
        if start:
            del buffer[:start]
        if len(buffer) < 2:
            return None
        command = buffer[1]
        if command == 0x32:
            if len(buffer) < 6:
                return None
            size = 4 + buffer[5]
        elif command == 0x3a:
            if len(buffer) < 3:
                return None
            size = 1 + buffer[2]
        else:
            size = FIXED_RX_PAYLOAD.get(command)
            if size is None:
                del buffer[0]
                continue
        total = 2 + size + len(TAIL)
        if len(buffer) < total:
            return None
        if buffer[total - len(TAIL):total] != TAIL:
            del buffer[0]
            continue
        payload = bytes(buffer[2:2 + size])
        del buffer[:total]
        return command, payload


def aux_baud_divisor(baudrate):
    """Return panel divisor and the actual attainable baud rate."""
    if not isinstance(baudrate, int) or baudrate < 15300:
        raise ValueError('extended UART baudrate must be at least 15300')
    divisor = round(15667200 / baudrate)
    if not 1 <= divisor <= 0x03ff:
        raise ValueError('extended UART baudrate is outside panel range')
    return divisor, 15667200 / divisor
