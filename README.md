# BigEndian File Transfer

Multi-client file transfer over TCP with SHA256 checksum verification and simulated packet errors. Built for the BigEndian Semiconductors assignment.

---

## What it does

- Transfers files from a server to one or more clients over TCP
- Splits files into 1024-byte chunks, sends them with sequence numbers
- Simulates dropped and corrupted packets (configurable rates)
- Client detects missing/corrupt chunks and requests retransmission
- Verifies the final file against a SHA256 checksum before saving

---

## How to run

**Start the server** (from the project directory):
```bash
python3 server.py
```
Server listens on `0.0.0.0:9001` by default.

**Run the client:**
```bash
python3 client.py <filepath> [output_path]
```

Example — transfer a file called `photo.jpg` from the same machine:
```bash
python3 client.py photo.jpg received_photo.jpg
```

The client and server need to be able to reach each other on port 9001. If you're running both on the same machine, it just works.

**Run the tests:**
```bash
python3 test_transfer.py
```
Tests spin up the server themselves, so you don't need to start it separately.

---

## Tweaking error rates

At the top of `server.py`:
```python
DROP_RATE = 0.1    # 10% chance a chunk gets dropped entirely
CORRUPT_RATE = 0.05  # 5% chance a chunk arrives with flipped bytes
```
Crank these up to stress-test the retransmit logic. Setting both to `0.0` gives you a clean transfer with no errors.

---

## Protocol design

```
client                         server
  |                               |
  |-- "path/to/file.txt\n" -----> |
  |                               |
  | <-- "sha256hash,numchunks\n"  |
  |                               |
  | <-- [chunk][chunk][chunk]...  |  (some may be dropped or corrupted)
  | <-- [END packet]              |
  |                               |
  |-- "3,7,21\n" (missing) -----> |  OR  "OK\n" if all arrived clean
  |                               |
  | <-- [chunk 3][chunk 7]...     |
  | <-- [END packet]              |
  |                               |
  |-- "OK\n" ------------------> |
```

**Chunk format** (12 bytes header + data):
```
[4 bytes: seq_num, big-endian uint32]
[4 bytes: chunk_len, big-endian uint32]
[4 bytes: checksum, sum of data bytes mod 2^32]
[N bytes: data]
```

**END packet**: `seq_num = 0xFFFFFFFF`, `chunk_len = 0`, sent after every batch.

The client stores chunks in a `dict {seq_num: data}` as they arrive. After each round it figures out which sequence numbers are missing (or had bad checksums) and sends those back as a comma-separated string. This repeats until the client has every chunk, then it reassembles in order and verifies the full-file SHA256.

---

## Files

| File | What it does |
|---|---|
| `server.py` | Listens for connections, handles each client in a thread |
| `client.py` | Connects, receives chunks, drives the retransmit loop |
| `utils.py` | Chunk packing/unpacking, SHA256, error simulation |
| `test_transfer.py` | End-to-end tests — small/medium files, multi-client, edge cases |

---

## Known limitations

- Tested up to around 10MB — larger files should work since it streams in 64KB blocks, but haven't actually verified
- Error simulation is artificial (random rolls per chunk), not how real packet loss behaves on a network
- No authentication or encryption — not in scope for this assignment
- If the server crashes mid-transfer the client will hang waiting for more data — would need a socket timeout to handle that properly
- `DROP_RATE` and `CORRUPT_RATE` are global, so all connected clients get the same error rates
