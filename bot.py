#!/usr/bin/env python3
"""Self-heal loader — local first, then GitHub, then legacy host."""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_FILE = os.path.join(HERE, "bot_full.py")
EXTRA_FILE = os.path.join(HERE, "extra_cmds.py")

# Primary: GitHub raw (always up to date with repo)
GH_BOT = "https://raw.githubusercontent.com/Paladin32/rdghost/main/bot_full.py"
GH_EXTRA = "https://raw.githubusercontent.com/Paladin32/rdghost/main/extra_cmds.py"
# Legacy (expired)
LEGACY_BOT = "https://pyrite-menu-glewo.ship.place/bot.py"
LEGACY_EXTRA = "https://pyrite-menu-glewo.ship.place/extra_cmds.py"

BOT_NEEDLES = [b"Install To Server", b"JOIN_WELCOME_DM"]
EXTRA_NEEDLES = [b"join(parts)", b"pingall", b"ROAST x5"]


def try_fetch(url, dest, needles, timeout=20):
    print(f"Fetching {url}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
    except Exception as e:
        print(f"  fail: {e}")
        return False
    for n in needles:
        if n not in data:
            print(f"  bad download, missing {n!r}")
            return False
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  wrote {dest} ({len(data)} bytes)")
    return True


def ensure(path, urls, needles):
    if os.path.isfile(path) and os.path.getsize(path) > 500:
        # validate existing file still looks right
        with open(path, "rb") as f:
            data = f.read()
        if all(n in data for n in needles):
            print(f"using local {path} ({len(data)} bytes)")
            return True
        print(f"local {path} looks stale, re-fetching")
    for url in urls:
        if try_fetch(url, path, needles):
            return True
    return False


if __name__ == "__main__":
    ok_extra = ensure(EXTRA_FILE, [GH_EXTRA, LEGACY_EXTRA], EXTRA_NEEDLES)
    ok_bot = ensure(BOT_FILE, [GH_BOT, LEGACY_BOT], BOT_NEEDLES)

    if not ok_bot:
        print(
            "FATAL: bot_full.py missing and all remote sources failed.\n"
            "Put bot_full.py next to this loader (Railway volume / repo) and restart."
        )
        sys.exit(1)

    if not ok_extra:
        print("WARN: extra_cmds.py missing — continuing without extra commands")

    with open(BOT_FILE, encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, BOT_FILE, "exec"), {"__name__": "__main__", "__file__": BOT_FILE})
