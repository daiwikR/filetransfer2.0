import hashlib
import random
import struct

# chunk size felt reasonable after reading some SO posts, 1024 bytes
CHUNK_SIZE = 1024

# these can be tweaked from server.py, keeping defaults here for reference
DROP_RATE = 0.1
CORRUPT_RATE = 0.05


def pack_chunk(seq_num, data):
    # big-endian two unsigned ints: seq number and how long the data is
    header = struct.pack('>II', seq_num, len(data))
    return header + data


def unpack_chunk(raw):
    # header is always 8 bytes (4 + 4)
    header_size = struct.calcsize('>II')
    seq_num, chunk_len = struct.unpack('>II', raw[:header_size])
    data = raw[header_size:header_size + chunk_len]
    return seq_num, chunk_len, data


def file_checksum(filepath):
    # compute sha256 on the whole file before we split it up
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def checksum_bytes(data: bytes):
    # sometimes need to hash raw bytes directly (for verifying reassembled file)
    return hashlib.sha256(data).hexdigest()


def simulate_error(data, drop_rate=DROP_RATE, corrupt_rate=CORRUPT_RATE):
    """
    returns (should_drop, possibly_corrupted_data)
    called per chunk on the server side before sending
    """
    roll = random.random()

    if roll < drop_rate:
        # just don't send this chunk, client will notice it's missing
        return True, data

    # check if we corrupt this one — using a fresh roll so drop and corrupt
    # are independent events (not sure if that's how real packet loss works tbh)
    corrupt_roll = random.random()
    if corrupt_roll < corrupt_rate:
        data = _flip_bytes(data)
        return False, data

    return False, data


def _flip_bytes(data):
    # flip a couple of bytes somewhere in the middle to simulate bit errors
    if len(data) < 4:
        return data

    ba = bytearray(data)
    # TODO: maybe flip more bytes to make it a harder test case
    idx = random.randint(0, len(ba) - 1)
    ba[idx] ^= 0xFF
    return bytes(ba)
