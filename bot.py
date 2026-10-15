# language: Python 3.11+, file: bot.py, target: Discord API v10
# pip install -U discord.py

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import random
from pathlib import Path
from urllib.parse import urlencode

TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
CLIENT_ID = os.getenv("CLIENT_ID") or "YOUR_CLIENT_ID"
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
PREFIX = os.getenv("PREFIX") or "/"
REDIRECT_URI = os.getenv("REDIRECT_URI") or "http://localhost:8080/callback"

DATA_FILE = Path("data.json")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"whitelist": [], "blacklist": [], "sent_messages": [], "authorized": {}}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

data = load_data()

def is_owner_user(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_whitelisted_user(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    if user_id in data.get("blacklist", []):
        return False
    return user_id in data.get("whitelist", [])

async def track_message(msg):
    data.setdefault("sent_messages", []).append({"channel_id": msg.channel.id, "message_id": msg.id})
    save_data(data)

async def safe_send(channel, content, delete_after=None):
    try:
        msg = await channel.send(content, delete_after=delete_after)
        await track_message(msg)
        return msg
    except discord.HTTPException as e:
        if e.status == 429:
            await asyncio.sleep(getattr(e, "retry_after", 1.5) or 1.5)
            msg = await channel.send(content, delete_after=delete_after)
            await track_message(msg)
            return msg
        raise

def build_oauth_link():
    params = {
        "client_id": CLIENT_ID,
        "permissions": "8",
        "scope": "bot applications.commands",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
    }
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

@bot.event
async def on_ready():
    print(f"logged in as {bot.user} | {bot.user.id}")
    try:
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"sync failed: {e}")

@bot.tree.command(name="link", description="Send the bot authorize / install link")
async def link(interaction: discord.Interaction):
    url = build_oauth_link()
    await interaction.response.send_message(f"**Authorize / Install the bot:**\n{url}", ephemeral=False)

@bot.tree.command(name="adspam", description="Flood the channel with ad-style messages")
async def adspam(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    await interaction.response.defer()
    ads = [
        "@everyone JOIN NOW",
        "FREE NITRO → discord.gg/xxxx",
        "BOOST THIS SERVER",
        "RAID IN PROGRESS",
        "https://discord.gg/xxxx",
    ]
    for _ in range(15):
        await safe_send(interaction.channel, random.choice(ads))
        await asyncio.sleep(0.4)
    await interaction.followup.send("adspam done", ephemeral=True)

@bot.tree.command(name="test", description="Test if the bot works (sends then deletes)")
async def test(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    await interaction.response.send_message("bot online")
    msg = await interaction.original_response()
    await asyncio.sleep(1.2)
    try:
        await msg.delete()
    except:
        pass

@bot.tree.command(name="whitelist", description="Add a user to the whitelist (owner only)")
@app_commands.describe(member="User to whitelist")
async def whitelist(interaction: discord.Interaction, member: discord.Member):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    if member.id not in data["whitelist"]:
        data["whitelist"].append(member.id)
        save_data(data)
    await interaction.response.send_message(f"Whitelisted {member.mention}", ephemeral=True)

@bot.tree.command(name="unwhitelist", description="Remove a user from the whitelist (owner only)")
@app_commands.describe(member="User to unwhitelist")
async def unwhitelist(interaction: discord.Interaction, member: discord.Member):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    if member.id in data["whitelist"]:
        data["whitelist"].remove(member.id)
        save_data(data)
    await interaction.response.send_message(f"Unwhitelisted {member.mention}", ephemeral=True)

@bot.tree.command(name="blacklist", description="Blacklist a user (owner only)")
@app_commands.describe(member="User to blacklist")
async def blacklist(interaction: discord.Interaction, member: discord.Member):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    if member.id not in data["blacklist"]:
        data["blacklist"].append(member.id)
        save_data(data)
    if member.id in data["whitelist"]:
        data["whitelist"].remove(member.id)
        save_data(data)
    await interaction.response.send_message(f"Blacklisted {member.mention}", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove a user from the blacklist (owner only)")
@app_commands.describe(member="User to unblacklist")
async def unblacklist(interaction: discord.Interaction, member: discord.Member):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    if member.id in data["blacklist"]:
        data["blacklist"].remove(member.id)
        save_data(data)
    await interaction.response.send_message(f"Unblacklisted {member.mention}", ephemeral=True)

@bot.tree.command(name="blame", description="Send a fake blame message")
@app_commands.describe(member="User to blame (optional)")
async def blame(interaction: discord.Interaction, member: discord.Member = None):
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    target = member or interaction.user
    await interaction.response.send_message(f"**{target.mention}** just raided this server. Report them.")

@bot.tree.command(name="ghostping", description="Ghost ping a user")
@app_commands.describe(member="User to ghost ping")
async def ghostping(interaction: discord.Interaction, member: discord.Member):
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    await interaction.response.send_message(member.mention)
    msg = await interaction.original_response()
    await asyncio.sleep(0.6)
    try:
        await msg.delete()
    except:
        pass

@bot.tree.command(name="die", description="Delete every message the bot has tracked (owner only)")
async def die(interaction: discord.Interaction):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    for entry in list(data.get("sent_messages", [])):
        ch = bot.get_channel(entry["channel_id"])
        if ch is None:
            continue
        try:
            msg = await ch.fetch_message(entry["message_id"])
            await msg.delete()
            await asyncio.sleep(0.35)
        except:
            pass
    data["sent_messages"] = []
    save_data(data)
    await interaction.followup.send("All tracked messages deleted.", ephemeral=True)

@bot.tree.command(name="editspam", description="Edit-spam a message (whitelist only)")
@app_commands.describe(text="Text to spam via edits")
async def editspam(interaction: discord.Interaction, text: str):
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    await interaction.response.defer()
    msg = await safe_send(interaction.channel, text)
    for i in range(12):
        try:
            await msg.edit(content=f"{text} `{i}`")
            await asyncio.sleep(0.45)
        except:
            break
    await interaction.followup.send("editspam done", ephemeral=True)

@bot.tree.command(name="spam", description="Spam the channel (whitelist only)")
@app_commands.describe(text="Text to spam")
async def spam(interaction: discord.Interaction, text: str = "@everyone"):
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    if not interaction.guild:
        return await interaction.response.send_message("Server only.", ephemeral=True)
    await interaction.response.defer()
    for _ in range(25):
        await safe_send(interaction.channel, text)
        await asyncio.sleep(0.35)
    await interaction.followup.send("spam done", ephemeral=True)

@bot.tree.command(name="dmspam", description="DM spam a user (whitelist only)")
@app_commands.describe(member="User to DM", text="Message content")
async def dmspam(interaction: discord.Interaction, member: discord.Member, text: str = "you got hit"):
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    for _ in range(8):
        try:
            await member.send(text)
            await asyncio.sleep(0.7)
        except:
            break
    await interaction.followup.send("dmspam done", ephemeral=True)

@bot.tree.command(name="serverjoin", description="Store an invite for force-join (owner only)")
@app_commands.describe(invite="Invite link or code")
async def serverjoin(interaction: discord.Interaction, invite: str):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    await interaction.response.send_message(f"Invite stored: {invite}", ephemeral=True)

bot.run(TOKEN)
