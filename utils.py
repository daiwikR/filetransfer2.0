import hashlib
import random
import struct


CHUNK_SIZE = 1024

# these can be tweaked from server.py
DROP_RATE = 0.1
CORRUPT_RATE = 0.05

# header: seq_num (4) + client_id (4) + chunk_len (4) + checksum (4) = 16 bytes
HEADER_SIZE = struct.calcsize('>IIII')


def _chunk_csum(data):
    # simple sum of all bytes works to catch single-byte flips
    return sum(data) & 0xFFFFFFFF

def pack_chunk(seq_num, client_id, data):
    # header stores client_id so the receiver can verify the chunk belongs to it
    csum = _chunk_csum(data)
    header = struct.pack('>IIII', seq_num, client_id, len(data), csum)
    return header + data


def unpack_chunk(raw):
    seq_num, client_id, chunk_len, stored_csum = struct.unpack('>IIII', raw[:HEADER_SIZE])
    data = raw[HEADER_SIZE:HEADER_SIZE + chunk_len]
    is_corrupt = (_chunk_csum(data) != stored_csum)
    return seq_num, client_id, chunk_len, data, is_corrupt



def file_checksum(filepath):
    # compute sha256 on the whole file — used when hashing from disk
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def checksum_bytes(data: bytes):
    # sometimes need to hash raw bytes directly (for the uploaded data or reassembled file)
    return hashlib.sha256(data).hexdigest()

def simulate_error(packet, drop_rate=DROP_RATE, corrupt_rate=CORRUPT_RATE):
    # roll the dice — drop the packet or mess up some bytes
    roll = random.random()

    if roll < drop_rate:
        return True, packet

    corrupt_roll = random.random()
    if corrupt_roll < corrupt_rate:
        packet = _flip_bytes_in_payload(packet)
        return False, packet

    return False, packet


def _flip_bytes_in_payload(packet):
    # header is HEADER_SIZE bytes, only corrupt the data portion after that
    if len(packet) <= HEADER_SIZE:
        return packet

    ba = bytearray(packet)
    # TODO: maybe flip more bytes to make it a harder test case
    idx = random.randint(HEADER_SIZE, len(ba) - 1)
    ba[idx] ^= 0xFF
    return bytes(ba)
