#!/usr/bin/env python3
# Self-healing loader: fetches the full fixed bot.py and runs it.
import os
import sys
import urllib.request

FULL_URL = "https://smiling-fifth-k6ois.ship.place/bot.py"
TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_full.py")

def ensure_full():
    try:
        with urllib.request.urlopen(FULL_URL, timeout=20) as r:
            data = r.read()
        if b"bot.run(TOKEN)" not in data or b"Install To Server" not in data:
            print("Downloaded file looks incomplete, abort")
            sys.exit(1)
        with open(TARGET, "wb") as f:
            f.write(data)
        print(f"Full bot written to {TARGET} ({len(data)} bytes)")
        return TARGET
    except Exception as e:
        print(f"Failed to fetch full bot: {e}")
        # fallback to local if already present
        if os.path.exists(TARGET):
            print(f"Using existing {TARGET}")
            return TARGET
        sys.exit(1)

if __name__ == "__main__":
    path = ensure_full()
    # exec the full bot in this process
    with open(path) as f:
        code = f.read()
    # make sure __name__ and globals work
    glb = {"__name__": "__main__", "__file__": path}
    exec(compile(code, path, "exec"), glb)
