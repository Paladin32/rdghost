#!/usr/bin/env python3
"""Self-healing entrypoint.
On every start:
  1. downloads the fixed main bot (links + public_send)
  2. downloads the fixed extra_cmds (spam = direct channel.send, full amount)
  3. runs the bot
"""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_URL = "https://general-plank-7iygp.ship.place/bot.py"
EXTRA_URL = "https://pond-trouser-pmzj9.ship.place/extra_cmds.py"
BOT_FILE = os.path.join(HERE, "bot_full.py")
EXTRA_FILE = os.path.join(HERE, "extra_cmds.py")

def fetch(url, dest, must_contain):
    print(f"Fetching {url} ...")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read()
    for needle in must_contain:
        if needle.encode() not in data:
            print(f"Missing marker {needle!r} in download, abort")
            sys.exit(1)
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  -> {dest} ({len(data)} bytes)")

if __name__ == "__main__":
    fetch(BOT_URL, BOT_FILE, ["Install To Server", "No channel available for bulk"])
    fetch(EXTRA_URL, EXTRA_FILE, ["channel.send(text)", "Cannot resolve channel"])
    with open(BOT_FILE, encoding="utf-8") as f:
        code = f.read()
    # __file__ must point at BOT_FILE so _BASE finds extra_cmds.py next to it
    exec(compile(code, BOT_FILE, "exec"), {"__name__": "__main__", "__file__": BOT_FILE})
