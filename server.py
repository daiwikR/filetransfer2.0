import socket
import threading
import os
import struct

from utils import (
    CHUNK_SIZE, pack_chunk, file_checksum, simulate_error, DROP_RATE, CORRUPT_RATE
)

HOST = '0.0.0.0'
PORT = 9001

# tweak these to stress-test the retransmit logic
DROP_RATE = DROP_RATE
CORRUPT_RATE = CORRUPT_RATE


def send_all(sock, data):
    # socket.sendall should handle this but wrapping it just in case
    sock.sendall(data)


def handle_client(conn, addr):
    print(f"[+] connection from {addr}")
    try:
        # first thing client sends is the filename it wants
        filename = conn.recv(1024).decode().strip()
        print(f"[*] {addr} requesting: {filename}")

        if not os.path.exists(filename):
            conn.sendall(b"ERROR: file not found\n")
            return

        checksum = file_checksum(filename)
        file_size = os.path.getsize(filename)

        # figure out how many chunks we'll need upfront
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        # send checksum and chunk count so client knows what to expect
        meta = f"{checksum},{total_chunks}\n"
        conn.sendall(meta.encode())

        # read all chunks into memory — fine for files up to a few hundred MB probably
        # TODO: for very large files this should stream instead of loading everything
        chunks = {}
        with open(filename, 'rb') as f:
            seq = 0
            while True:
                data = f.read(CHUNK_SIZE)
                if not data:
                    break
                chunks[seq] = data
                seq += 1

        _send_chunks(conn, chunks)

        # retransmit loop — keep going until client says it has everything
        while True:
            response = _recv_line(conn)
            if response == "OK":
                print(f"[*] {addr} confirmed all chunks received")
                break

            # client sends back the seq nums it's missing, comma-separated
            missing = [int(x) for x in response.split(',') if x.strip()]
            print(f"[*] {addr} missing {len(missing)} chunks, resending")

            missing_chunks = {seq: chunks[seq] for seq in missing if seq in chunks}
            _send_chunks(conn, missing_chunks)

        print(f"[+] transfer done for {addr}")

    except Exception as e:
        print(f"[!] error with {addr}: {e}")
    finally:
        conn.close()


def _send_chunks(conn, chunks):
    # pack first so checksum is computed on clean data, then run error sim on the packet
    for seq_num, data in chunks.items():
        packet = pack_chunk(seq_num, data)
        should_drop, packet = simulate_error(packet, DROP_RATE, CORRUPT_RATE)
        if should_drop:
            continue
        send_all(conn, packet)

    # END marker — 12 bytes to match the new header size (seq, len, csum all zero-ish)
    end_packet = struct.pack('>III', 0xFFFFFFFF, 0, 0)
    send_all(conn, end_packet)


def _recv_line(sock):
    # read until newline — client responses are short so this should be fine
    buf = b''
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("client disconnected")
        if byte == b'\n':
            break
        buf += byte
    return buf.decode().strip()


def main():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # lets us restart the server quickly without waiting for TIME_WAIT
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(5)
    print(f"[*] listening on {HOST}:{PORT}")

    while True:
        conn, addr = server_sock.accept()
        # spin up a thread per client, keeping it simple
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()


if __name__ == '__main__':
    main()
