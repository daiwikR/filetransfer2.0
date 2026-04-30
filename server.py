import socket
import threading
import struct

from utils import (CHUNK_SIZE, HEADER_SIZE, pack_chunk, checksum_bytes, simulate_error, DROP_RATE,
CORRUPT_RATE)

HOST = '0.0.0.0'
PORT = 9001

# TODO:tweak these to stress-test the retransmit logic
DROP_RATE = DROP_RATE
CORRUPT_RATE = CORRUPT_RATE

# monotonically increasing id so each connection gets a unique client_id
_client_id_counter = 0
_id_lock = threading.Lock()


def _next_client_id():
    global _client_id_counter
    with _id_lock:
        _client_id_counter += 1
        return _client_id_counter

def send_all(sock, data):
    sock.sendall(data)



def handle_client(conn, addr):
    client_id = _next_client_id()
    print(f"[+] connection from {addr}, client_id={client_id}")
    try:
        # tell the client what id it got — it needs this to validate chunks
        conn.sendall(struct.pack('>I', client_id))

        filename = _recv_line(conn)
        print(f"[*] client {client_id} uploading: {filename}")

        # receive the file size first so we know how many bytes to read
        raw_size = _recv_exact(conn, 8)
        file_size = struct.unpack('>Q', raw_size)[0]

        # now read the actual file bytes — client is doing the upload here
        file_bytes = _recv_exact(conn, file_size)
        print(f"[*] client {client_id} uploaded {file_size} bytes")

        checksum = checksum_bytes(file_bytes)
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        # split the received data into chunks
        chunks = {}
        for seq in range(total_chunks):
            start = seq * CHUNK_SIZE
            chunks[seq] = file_bytes[start:start + CHUNK_SIZE]

        # send checksum and chunk count so client knows what to expect
        meta = f"{checksum},{total_chunks}\n"
        conn.sendall(meta.encode())

        _send_chunks(conn, chunks, client_id)

        # retransmit loop — keep going until client says it has everything
        while True:
            response = _recv_line(conn)
            if response == "OK":
                print(f"[*] client {client_id} confirmed all chunks received")
                break

            # client sends back the seq nums it's missing, comma-separated
            missing = [int(x) for x in response.split(',') if x.strip()]
            print(f"[*] client {client_id} missing {len(missing)} chunks, resending")

            to_resend = {seq: chunks[seq] for seq in missing if seq in chunks}
            _send_chunks(conn, to_resend, client_id)

        print(f"[+] transfer done for client {client_id}")

    except Exception as e:
        print(f"[!] error with client {client_id} ({addr}): {e}")
    finally:
        conn.close()


def _send_chunks(conn, chunks, client_id):
    # pack first so checksum is computed on clean data, then run error sim on the packet
    for seq_num, data in chunks.items():
        packet = pack_chunk(seq_num, client_id, data)
        should_drop, packet = simulate_error(packet, DROP_RATE, CORRUPT_RATE)
        if should_drop:
            continue
        send_all(conn, packet)

    # END marker — seq_num=0xFFFFFFFF signals no more chunks in this batch
    end_packet = struct.pack('>IIII', 0xFFFFFFFF, 0, 0, 0)
    send_all(conn, end_packet)

def _recv_exact(sock, n):
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("client disconnected mid-receive")
        buf += chunk
    return buf


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
