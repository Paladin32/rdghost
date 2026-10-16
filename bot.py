#!/usr/bin/env python3
# Loads bot: /link links + amount fix (no followup for bulk = no 5-cap).
import os
import sys
import urllib.request

URL = "https://general-plank-7iygp.ship.place/bot.py"
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "bot_full.py")

def load():
    with urllib.request.urlopen(URL, timeout=20) as r:
        data = r.read()
    if b"Install To Server" not in data or b"No channel available for bulk" not in data:
        print("Unexpected content, abort")
        sys.exit(1)
    with open(TARGET, "wb") as f:
        f.write(data)
    print(f"Loaded bot ({len(data)} bytes)")
    return TARGET

if __name__ == "__main__":
    path = load()
    with open(path) as f:
        code = f.read()
    exec(compile(code, path, "exec"), {"__name__": "__main__", "__file__": path})
