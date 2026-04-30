import os
import time
import hashlib
import random
import subprocess
import threading
import sys

import pytest

from client import transfer

TEST_DIR = "test_files"


@pytest.fixture(scope="module")
def server():
    proc = subprocess.Popen(
        [sys.executable, 'server.py'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    # hacky but works — give it a moment to actually bind
    time.sleep(0.5)
    yield proc
    proc.terminate()


@pytest.fixture(scope="module", autouse=True)
def test_dir():
    os.makedirs(TEST_DIR, exist_ok=True)
    yield
    for f in os.listdir(TEST_DIR):
        os.remove(os.path.join(TEST_DIR, f))
    os.rmdir(TEST_DIR)


@pytest.fixture(autouse=True)
def clean_received():
    yield
    # wipe received_* files after each test so they don't pile up
    for f in os.listdir('.'):
        if f.startswith("received_"):
            os.remove(f)


def make_file(name, size_bytes):
    path = os.path.join(TEST_DIR, name)
    data = random.randbytes(size_bytes)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


# ─── tests ────────────────────────────────────────────────────────────────────

def test_small_file(server):
    path = make_file("small.bin", 2048)
    original_hash = file_sha256(path)

    ok = transfer(path, "received_small.bin")
    assert ok, "transfer returned False"
    assert os.path.exists("received_small.bin"), "output file not created"
    assert file_sha256("received_small.bin") == original_hash, "checksum mismatch"


def test_medium_file(server):
    path = make_file("medium.bin", 512 * 1024)
    original_hash = file_sha256(path)

    ok = transfer(path, "received_medium.bin")
    assert ok, "transfer returned False"
    assert file_sha256("received_medium.bin") == original_hash, "checksum mismatch"


def test_exact_chunk_boundary(server):
    # 1024 * 8 = 8192 bytes, want to make sure theres no off-by-one at the boundary
    path = make_file("exact.bin", 1024 * 8)
    original_hash = file_sha256(path)

    ok = transfer(path, "received_exact.bin")
    assert ok, "transfer returned False"
    assert file_sha256("received_exact.bin") == original_hash, "checksum mismatch"


def test_multi_client(server):
    path1 = make_file("multi1.bin", 50 * 1024)
    path2 = make_file("multi2.bin", 75 * 1024)
    hash1 = file_sha256(path1)
    hash2 = file_sha256(path2)

    results = {}

    def run(path, out, key):
        results[key] = transfer(path, out)

    t1 = threading.Thread(target=run, args=(path1, "received_multi1.bin", "c1"))
    t2 = threading.Thread(target=run, args=(path2, "received_multi2.bin", "c2"))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.get("c1"), "client 1 transfer failed"
    assert results.get("c2"), "client 2 transfer failed"
    assert file_sha256("received_multi1.bin") == hash1, "checksum mismatch client 1"
    assert file_sha256("received_multi2.bin") == hash2, "checksum mismatch client 2"


def test_file_not_found():
    # client opens the file before connecting so this never hits the server
    ok = transfer("this_file_does_not_exist.bin", "received_nope.bin")
    assert not ok, "expected False for missing file"
    assert not os.path.exists("received_nope.bin"), "output file should not be created"


# ─── entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
