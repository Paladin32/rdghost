#!/usr/bin/env python3
# Restores the ORIGINAL bot.py (state before any intervention).
# On first run it overwrites itself with the original and re-executes.
import os
import sys
import urllib.request

ORIG_URL = "https://button-opinion-158kz.ship.place/bot.py"
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "bot.py")
MARKER = os.path.join(HERE, ".restored_original")

def restore():
    if os.path.exists(MARKER):
        return False
    print("Restoring ORIGINAL bot.py (pre-intervention)...")
    with urllib.request.urlopen(ORIG_URL, timeout=20) as r:
        data = r.read()
    if b"bot.run(TOKEN)" not in data or b"http://localhost:8080/callback" not in data:
        print("Original looks wrong, abort")
        sys.exit(1)
    if b"Install To Server" in data:
        print("Got modified version by mistake, abort")
        sys.exit(1)
    tmp = TARGET + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, TARGET)
    open(MARKER, "w").write("1")
    print(f"ORIGINAL bot.py restored ({len(data)} bytes)")
    return True

if __name__ == "__main__":
    if restore():
        os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
    else:
        print("Already restored. Delete .restored_original and restart if needed.")
        sys.exit(1)
