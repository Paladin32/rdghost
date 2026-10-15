# language: Python 3.11+, file: bot.py, target: Discord API v10
# pip install -U discord.py

import discord
from discord.ext import commands
import asyncio
import json
import os
import random
from pathlib import Path

TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
PREFIX = os.getenv("PREFIX") or "/"

DATA_FILE = Path("data.json")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"whitelist": [], "blacklist": [], "sent_messages": []}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

data = load_data()

def is_owner():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

def is_whitelisted():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        if ctx.author.id in data["blacklist"]:
            return False
        return ctx.author.id in data["whitelist"]
    return commands.check(predicate)

def in_guild():
    async def predicate(ctx):
        return ctx.guild is not None
    return commands.check(predicate)

async def track_message(msg):
    data["sent_messages"].append({"channel_id": msg.channel.id, "message_id": msg.id})
    save_data(data)

async def safe_send(channel, content, delete_after=None):
    try:
        msg = await channel.send(content, delete_after=delete_after)
        await track_message(msg)
        return msg
    except discord.HTTPException as e:
        if e.status == 429:
            await asyncio.sleep(e.retry_after or 1.5)
            msg = await channel.send(content, delete_after=delete_after)
            await track_message(msg)
            return msg
        raise

@bot.event
async def on_ready():
    print(f"logged in as {bot.user} | {bot.user.id}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CheckFailure, commands.CommandNotFound)):
        return
    print(f"error: {error}")

@bot.command(name="adspam")
@in_guild()
async def adspam(ctx):
    ads = [
        "@everyone JOIN NOW",
        "FREE NITRO → discord.gg/xxxx",
        "BOOST THIS SERVER",
        "RAID IN PROGRESS",
        "https://discord.gg/xxxx",
    ]
    for _ in range(15):
        await safe_send(ctx.channel, random.choice(ads))
        await asyncio.sleep(0.4)

@bot.command(name="test")
@in_guild()
async def test(ctx):
    msg = await safe_send(ctx.channel, "bot online")
    await asyncio.sleep(1.2)
    try:
        await msg.delete()
    except:
        pass

@bot.command(name="whitelist")
@in_guild()
@is_owner()
async def whitelist(ctx, member: discord.Member):
    if member.id not in data["whitelist"]:
        data["whitelist"].append(member.id)
        save_data(data)
    await ctx.message.add_reaction("✅")

@bot.command(name="unwhitelist")
@in_guild()
@is_owner()
async def unwhitelist(ctx, member: discord.Member):
    if member.id in data["whitelist"]:
        data["whitelist"].remove(member.id)
        save_data(data)
    await ctx.message.add_reaction("✅")

@bot.command(name="blacklist")
@in_guild()
@is_owner()
async def blacklist(ctx, member: discord.Member):
    if member.id not in data["blacklist"]:
        data["blacklist"].append(member.id)
        save_data(data)
    if member.id in data["whitelist"]:
        data["whitelist"].remove(member.id)
        save_data(data)
    await ctx.message.add_reaction("✅")

@bot.command(name="unblacklist")
@in_guild()
@is_owner()
async def unblacklist(ctx, member: discord.Member):
    if member.id in data["blacklist"]:
        data["blacklist"].remove(member.id)
        save_data(data)
    await ctx.message.add_reaction("✅")

@bot.command(name="blame")
@in_guild()
async def blame(ctx, member: discord.Member = None):
    target = member or ctx.author
    await safe_send(ctx.channel, f"**{target.mention}** just raided this server. Report them.")

@bot.command(name="ghostping")
@in_guild()
async def ghostping(ctx, member: discord.Member):
    msg = await safe_send(ctx.channel, member.mention)
    await asyncio.sleep(0.6)
    try:
        await msg.delete()
    except:
        pass

@bot.command(name="die")
@in_guild()
@is_owner()
async def die(ctx):
    for entry in list(data["sent_messages"]):
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
    await ctx.message.add_reaction("💀")

@bot.command(name="editspam")
@in_guild()
@is_whitelisted()
async def editspam(ctx, *, text: str):
    msg = await safe_send(ctx.channel, text)
    for i in range(12):
        try:
            await msg.edit(content=f"{text} `{i}`")
            await asyncio.sleep(0.45)
        except:
            break

@bot.command(name="spam")
@in_guild()
@is_whitelisted()
async def spam(ctx, *, text: str = "@everyone"):
    for _ in range(25):
        await safe_send(ctx.channel, text)
        await asyncio.sleep(0.35)

@bot.command(name="dmspam")
@in_guild()
@is_whitelisted()
async def dmspam(ctx, member: discord.Member, *, text: str = "you got hit"):
    for _ in range(8):
        try:
            await member.send(text)
            await asyncio.sleep(0.7)
        except:
            break

@bot.command(name="serverjoin")
@in_guild()
@is_owner()
async def serverjoin(ctx, invite: str):
    await safe_send(ctx.channel, f"invite stored: {invite}")

bot.run(TOKEN)
