import os
import time
import hashlib
import random
import subprocess
import threading
import sys

from client import transfer

# where to put test files
TEST_DIR = "test_files"


def setup():
    os.makedirs(TEST_DIR, exist_ok=True)


def teardown():
    # clean up
    for f in os.listdir(TEST_DIR):
        os.remove(os.path.join(TEST_DIR, f))
    os.rmdir(TEST_DIR)

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


def start_server():
    # spin up the server as a subprocess so it runs independently
    proc = subprocess.Popen(
        [sys.executable, 'server.py'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    # hacky but works
    time.sleep(0.5)
    return proc


# ─── tests ────────────────────────────────────────────────────────────────────

def test_small_file(label="small file (~2KB)"):
    path = make_file("small.bin", 2048)
    original_hash = file_sha256(path)

    ok = transfer(path, "received_small.bin")
    assert ok, "transfer returned False"
    assert os.path.exists("received_small.bin"), "output file not created"

    received_hash = file_sha256("received_small.bin")
    assert received_hash == original_hash, "checksum mismatch on small file"
    print(f"  [pass] {label}")


def test_medium_file(label="medium file (~512KB)"):
    path = make_file("medium.bin", 512 * 1024)
    original_hash = file_sha256(path)

    ok = transfer(path, "received_medium.bin")
    assert ok, "transfer returned False"

    received_hash = file_sha256("received_medium.bin")
    assert received_hash == original_hash, "checksum mismatch on medium file"
    print(f"  [pass] {label}")


def test_exact_chunk_boundary(label="file exactly divisible by chunk size"):
    
    path = make_file("exact.bin", 1024 * 8)
    original_hash = file_sha256(path)

    ok = transfer(path, "received_exact.bin")
    assert ok, "transfer returned False"

    received_hash = file_sha256("received_exact.bin")
    assert received_hash == original_hash, "checksum mismatch on boundary file"
    print(f"  [pass] {label}")


def test_multi_client(label="two clients simultaneously"):
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
    print(f"  [pass] {label}")


def test_file_not_found(label="client returns False for missing local file"):
    # client now opens the file itself, so failure happens before we even connect
    ok = transfer("this_file_does_not_exist.bin", "received_nope.bin")
    assert not ok, "expected transfer to return False for missing file"
    assert not os.path.exists("received_nope.bin"), "output file should not be created"
    print(f"  [pass] {label}")


# ─── runner ───────────────────────────────────────────────────────────────────

def run_all():
    setup()
    server = start_server()

    tests = [
        test_small_file,
        test_medium_file,
        test_exact_chunk_boundary,
        test_multi_client,
        test_file_not_found,
    ]

    passed = 0
    failed = 0

    print("\nrunning tests...\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [fail] {test.__name__}: {e}")
            failed += 1

    server.terminate()
    teardown()

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    run_all()
