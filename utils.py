import hashlib
import random
import struct

# chunk size felt reasonable after reading some SO posts, 1024 bytes
CHUNK_SIZE = 1024

# these can be tweaked from server.py, keeping defaults here for reference
DROP_RATE = 0.1
CORRUPT_RATE = 0.05


def _chunk_csum(data):
    # simple sum of all bytes mod 2^32, good enough to catch single-byte flips
    return sum(data) & 0xFFFFFFFF


def pack_chunk(seq_num, data):
    # header: seq_num, data length, checksum of the original data
    csum = _chunk_csum(data)
    header = struct.pack('>III', seq_num, len(data), csum)
    return header + data


def unpack_chunk(raw):
    # header is now 12 bytes (4 + 4 + 4)
    header_size = struct.calcsize('>III')
    seq_num, chunk_len, stored_csum = struct.unpack('>III', raw[:header_size])
    data = raw[header_size:header_size + chunk_len]
    is_corrupt = (_chunk_csum(data) != stored_csum)
    return seq_num, chunk_len, data, is_corrupt


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


def simulate_error(packet, drop_rate=DROP_RATE, corrupt_rate=CORRUPT_RATE):
    """
    takes a fully packed packet, returns (should_drop, possibly_corrupted_packet)
    corruption flips a byte in the data portion only — header stays intact
    so the client can still detect it as corrupt via the checksum field
    """
    roll = random.random()

    if roll < drop_rate:
        return True, packet

    corrupt_roll = random.random()
    if corrupt_roll < corrupt_rate:
        packet = _flip_bytes_in_payload(packet)
        return False, packet

    return False, packet


def _flip_bytes_in_payload(packet):
    # header is 12 bytes, only corrupt the data portion after that
    header_size = struct.calcsize('>III')
    if len(packet) <= header_size:
        return packet

    ba = bytearray(packet)
    # TODO: maybe flip more bytes to make it a harder test case
    idx = random.randint(header_size, len(ba) - 1)
    ba[idx] ^= 0xFF
    return bytes(ba)
