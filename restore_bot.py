#!/usr/bin/env python3
"""Restore full bot.py from the verified hosted copy."""
import urllib.request
url = "https://smiling-fifth-k6ois.ship.place/bot.py"
print("Downloading full bot.py...")
with urllib.request.urlopen(url) as r:
    data = r.read()
with open("bot.py", "wb") as f:
    f.write(data)
print(f"Wrote bot.py ({len(data)} bytes)")
print("Done. Restart the bot.")
