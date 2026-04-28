import socket
import struct
import os
import sys

from utils import checksum_bytes

HOST = '127.0.0.1'
PORT = 9001

# header is 12 bytes: seq_num (4) + chunk_len (4) + checksum (4)
HEADER_SIZE = struct.calcsize('>III')


def recv_exact(sock, n):
    # TCP doesn't guarantee we get n bytes in one recv call, so loop until we have them
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("server disconnected mid-transfer")
        buf += chunk
    return buf


def recv_line(sock):
    # read byte by byte until newline, used for the metadata line
    buf = b''
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("server disconnected")
        if byte == b'\n':
            break
        buf += byte
    return buf.decode().strip()


def receive_chunks(sock):
    # collect chunks into a dict until we hit the END marker
    received = {}
    while True:
        header = recv_exact(sock, HEADER_SIZE)
        seq_num, chunk_len, stored_csum = struct.unpack('>III', header)

        # 0xFFFFFFFF is the end-of-transmission sentinel
        if seq_num == 0xFFFFFFFF:
            break

        data = recv_exact(sock, chunk_len)

        # verify chunk checksum — if it's wrong, skip it so it stays missing
        actual_csum = sum(data) & 0xFFFFFFFF
        if actual_csum != stored_csum:
            continue

        received[seq_num] = data

    return received


def find_missing(received, total_chunks):
    # just check which seq numbers we never got
    return [i for i in range(total_chunks) if i not in received]


def reassemble(received, total_chunks):
    # stitch chunks back together in order
    parts = []
    for i in range(total_chunks):
        parts.append(received[i])
    return b''.join(parts)


def transfer(filename, output_path=None):
    if output_path is None:
        # default: save as "received_<original filename>" in current dir
        output_path = "received_" + os.path.basename(filename)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"[*] connected to {HOST}:{PORT}")

    # tell server what file we want
    sock.sendall((filename + '\n').encode())

    # first response is "checksum,total_chunks"
    meta = recv_line(sock)

    if meta.startswith("ERROR"):
        print(f"[!] server error: {meta}")
        sock.close()
        return False

    expected_checksum, total_chunks = meta.split(',')
    total_chunks = int(total_chunks)
    print(f"[*] expecting {total_chunks} chunks, checksum: {expected_checksum[:12]}...")

    received = {}

    # first pass — get whatever the server sends (some might be dropped/corrupted)
    received.update(receive_chunks(sock))
    print(f"[*] got {len(received)}/{total_chunks} chunks on first pass")

    # retransmit loop
    MAX_RETRIES = 10
    retries = 0
    while True:
        missing = find_missing(received, total_chunks)

        if not missing:
            sock.sendall(b"OK\n")
            print(f"[*] all chunks received after {retries} retransmit round(s)")
            break

        if retries >= MAX_RETRIES:
            print(f"[!] gave up after {MAX_RETRIES} retransmit rounds, still missing {len(missing)} chunks")
            sock.close()
            return False

        print(f"[*] missing {len(missing)} chunks, requesting retransmit")
        request = ','.join(str(s) for s in missing) + '\n'
        sock.sendall(request.encode())

        new_chunks = receive_chunks(sock)
        received.update(new_chunks)
        retries += 1

    sock.close()

    # put the file back together and check the hash
    file_data = reassemble(received, total_chunks)
    actual_checksum = checksum_bytes(file_data)

    if actual_checksum != expected_checksum:
        print(f"[!] checksum mismatch — file is corrupt")
        print(f"    expected: {expected_checksum}")
        print(f"    got:      {actual_checksum}")
        return False

    with open(output_path, 'wb') as f:
        f.write(file_data)

    print(f"[+] file saved to {output_path} ({len(file_data)} bytes), checksum OK")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: python client.py <filename> [output_path]")
        sys.exit(1)

    filename = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None
    transfer(filename, output)
