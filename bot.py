#!/usr/bin/env python3
"""Self-heal loader — local first, then GitHub, then legacy host."""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_FILE = os.path.join(HERE, "bot_full.py")
EXTRA_FILE = os.path.join(HERE, "extra_cmds.py")

GH_BOT = "https://raw.githubusercontent.com/Paladin32/rdghost/main/bot_full.py"
GH_EXTRA = "https://raw.githubusercontent.com/Paladin32/rdghost/main/extra_cmds.py"
LEGACY_BOT = "https://pyrite-menu-glewo.ship.place/bot.py"
LEGACY_EXTRA = "https://pyrite-menu-glewo.ship.place/extra_cmds.py"

# soft markers — any match is enough; empty list = size check only
BOT_MARKERS = [b"discord", b"bot", b"TOKEN"]
EXTRA_MARKERS = [b"dmspam", b"tree.command"]


def try_fetch(url, dest, markers, timeout=20):
    print(f"Fetching {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rdghost-loader/1.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except Exception as e:
        print(f"  fail: {e}")
        return False
    if len(data) < 200:
        print(f"  too small ({len(data)} bytes)")
        return False
    if markers and not any(m in data for m in markers):
        print(f"  content does not look like expected file")
        return False
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  wrote {dest} ({len(data)} bytes)")
    return True


def ensure(path, urls, markers):
    if os.path.isfile(path) and os.path.getsize(path) > 200:
        with open(path, "rb") as f:
            data = f.read()
        if not markers or any(m in data for m in markers):
            print(f"using local {path} ({len(data)} bytes)")
            return True
        print(f"local {path} looks wrong, re-fetching")
    for url in urls:
        if try_fetch(url, path, markers):
            return True
    return False


if __name__ == "__main__":
    ok_extra = ensure(EXTRA_FILE, [GH_EXTRA, LEGACY_EXTRA], EXTRA_MARKERS)
    ok_bot = ensure(BOT_FILE, [GH_BOT, LEGACY_BOT], BOT_MARKERS)

    if not ok_bot:
        print(
            "FATAL: bot_full.py missing and all remote sources failed.\n"
            "→ Copy bot_full.py next to this file (Railway shell / redeploy with the file)\n"
            "→ Or paste the full bot source into the repo as bot_full.py"
        )
        sys.exit(1)

    if not ok_extra:
        print("WARN: extra_cmds.py missing — continuing without extra commands")

    with open(BOT_FILE, encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, BOT_FILE, "exec"), {"__name__": "__main__", "__file__": BOT_FILE})
