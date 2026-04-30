import socket
import struct
import os
import sys

from utils import checksum_bytes, HEADER_SIZE

HOST = '127.0.0.1'
PORT = 9001


def recv_exact(sock, n):
    # TCP doesn't guarantee we get n bytes in a single loop so loop until we have them
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("server disconnected mid-transfer")
        buf += chunk
    return buf

def recv_line(sock):
    # read byte by byte until newline
    buf = b''
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("server disconnected")
        if byte == b'\n':
            break
        buf += byte
    return buf.decode().strip()



def grab_chunks(sock, expected_client_id):
    # collect chunks into a dict until we hit the END marker
    received = {}
    while True:
        header = recv_exact(sock, HEADER_SIZE)
        seq_num, chunk_client_id, chunk_len, stored_csum = struct.unpack('>IIII', header)


        if seq_num == 0xFFFFFFFF:
            break

        data = recv_exact(sock, chunk_len)

        # check if the TCP connection is proper
        if chunk_client_id != expected_client_id:
            continue

        # verify chunk checksum just drop if its wrong
        actual_csum = sum(data) & 0xFFFFFFFF
        if actual_csum != stored_csum:
            continue

        received[seq_num] = data

    return received

def find_missing(received, total_chunks):
    # just check which seq numbers we never got
    return [i for i in range(total_chunks) if i not in received]


def reassemble(received, total_chunks):
    # rearrange the chucks in order
    parts = []
    for i in range(total_chunks):
        parts.append(received[i])
    return b''.join(parts)

def transfer(filename, output_path=None):
    if output_path is None:
        # im going to  save as "received_<original filename>" in current dir
        output_path = "received_" + os.path.basename(filename)

    try:
        with open(filename, 'rb') as f:
            file_data = f.read()
    except FileNotFoundError:
        print(f"[!] file not found: {filename}")
        return False

    file_size = len(file_data)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"[*] connected to {HOST}:{PORT}")

    # server immediately sends our assigned client_id
    raw_id = recv_exact(sock, 4)
    client_id = struct.unpack('>I', raw_id)[0]
    print(f"[*] assigned client_id={client_id}")

    # upload: send filename, then file size, then the actual bytes
    sock.sendall((os.path.basename(filename) + '\n').encode())
    sock.sendall(struct.pack('>Q', file_size))
    sock.sendall(file_data)
    print(f"[*] uploaded {file_size} bytes")

    # server responds with checksum and chunk count
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
    received.update(grab_chunks(sock, client_id))
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

        new_chunks = grab_chunks(sock, client_id)
        received.update(new_chunks)
        retries += 1

    sock.close()

    # put the file back together and check the hash
    rebuilt = reassemble(received, total_chunks)
    actual_checksum = checksum_bytes(rebuilt)

    if actual_checksum != expected_checksum:
        print(f"[!] checksum mismatch — file is corrupt")
        print(f"    expected: {expected_checksum}")
        print(f"    got:      {actual_checksum}")
        return False

    with open(output_path, 'wb') as f:
        f.write(rebuilt)

    print(f"[+] file saved to {output_path} ({len(rebuilt)} bytes), checksum OK")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: python client.py <filename> [output_path]")
        sys.exit(1)

    filename = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None
    transfer(filename, output)
