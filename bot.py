# language: Python 3.11+, file: bot.py, target: Discord API v10
# pip install -U discord.py requests

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import random
import requests as http_requests
from pathlib import Path
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
CLIENT_ID = os.getenv("CLIENT_ID") or "YOUR_CLIENT_ID"
CLIENT_SECRET = os.getenv("CLIENT_SECRET") or "YOUR_CLIENT_SECRET"
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
OWNER_ID_2 = int(os.getenv("OWNER_ID_2") or 0)
REQUIRED_GUILD_ID = int(os.getenv("REQUIRED_GUILD_ID") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 1560370435797950597)
WHITELIST_LOG_CHANNEL_ID = int(os.getenv("WHITELIST_LOG_CHANNEL_ID") or 1560375659501719623)
PREFIX = os.getenv("PREFIX") or "/"
REDIRECT_URI = os.getenv("REDIRECT_URI") or "http://localhost:8080/callback"

OWNER_IDS = {uid for uid in (OWNER_ID, OWNER_ID_2) if uid}

INVITE = "https://discord.gg/SKyfbZxzbp"

FLOOD_BLOCK = "\n".join(["\u3164"] * 80) + "\n@here @everyone\n" + INVITE

DATA_FILE = Path("data.json")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

bot.tree.allowed_contexts = discord.app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
bot.tree.allowed_installs = discord.app_commands.AppInstallationType(guild=True, user=True)

def load_data():
    if DATA_FILE.exists():
        raw = json.loads(DATA_FILE.read_text())
    else:
        raw = {}
    wl = raw.get("whitelist", {})
    if isinstance(wl, list):
        wl = {str(uid): "2099-01-01T00:00:00+00:00" for uid in wl}
    raw["whitelist"] = wl
    raw.setdefault("sent_messages", [])
    raw.setdefault("authorized", {})
    return raw

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

data = load_data()

def is_owner_user(user_id: int) -> bool:
    return user_id in OWNER_IDS

def cleanup_whitelist():
    now = datetime.now(timezone.utc)
    changed = False
    for uid in list(data.get("whitelist", {}).keys()):
        try:
            exp = datetime.fromisoformat(data["whitelist"][uid])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                del data["whitelist"][uid]
                changed = True
        except:
            del data["whitelist"][uid]
            changed = True
    if changed:
        save_data(data)

def is_whitelisted_user(user_id: int) -> bool:
    if user_id in OWNER_IDS:
        return True
    cleanup_whitelist()
    entry = data.get("whitelist", {}).get(str(user_id))
    if not entry:
        return False
    try:
        exp = datetime.fromisoformat(entry)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)
    except:
        return False

async def must_be_in_required_guild(interaction: discord.Interaction) -> bool:
    if REQUIRED_GUILD_ID == 0:
        return True
    guild = bot.get_guild(REQUIRED_GUILD_ID)
    if guild is None:
        if not interaction.response.is_done():
            await interaction.response.send_message("Required server not found. Bot must be in it.", ephemeral=True)
        return False
    member = guild.get_member(interaction.user.id)
    if member is None:
        try:
            member = await guild.fetch_member(interaction.user.id)
        except:
            member = None
    if member is None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"You must be in the required server to use this bot.\n{INVITE}",
                ephemeral=True
            )
        return False
    return True

async def resolve_channel(interaction: discord.Interaction):
    if interaction.channel_id:
        cached = bot.get_channel(interaction.channel_id)
        if cached is not None:
            return cached
        try:
            return await bot.fetch_channel(interaction.channel_id)
        except Exception as e:
            print(f"fetch_channel failed: {e}")
    return None

async def public_send(interaction: discord.Interaction, content: str):
    """Send public message. Prefer channel.send (editable/deletable by bot). Fallback: followup."""
    if len(content) > 2000:
        content = content[:1997] + "..."
    channel = await resolve_channel(interaction)
    if channel is not None:
        try:
            msg = await channel.send(content)
            data.setdefault("sent_messages", []).append({
                "channel_id": msg.channel.id,
                "message_id": msg.id,
                "via": "channel",
            })
            save_data(data)
            return msg
        except Exception as e:
            print(f"channel.send failed, falling back to followup: {e}")

    msg = await interaction.followup.send(content, ephemeral=False)
    try:
        data.setdefault("sent_messages", []).append({
            "channel_id": interaction.channel_id,
            "message_id": msg.id,
            "via": "followup",
        })
        save_data(data)
    except Exception as e:
        print(f"track followup failed: {e}")
    return msg

async def log_command(interaction: discord.Interaction, command_name: str, extra: str = None):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except:
            return

    guild_name = interaction.guild.name if interaction.guild else "DM"
    guild_id = interaction.guild.id if interaction.guild else 0
    channel_name = getattr(interaction.channel, "name", "unknown")
    channel_id = interaction.channel.id if interaction.channel else 0

    embed = discord.Embed(
        title="Command Log",
        color=0x2B2D31,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="User", value=f"<@{interaction.user.id}>", inline=True)
    embed.add_field(name="Command", value=f"`/{command_name}`", inline=True)
    embed.add_field(name="Server", value=f"{guild_name}\n`{guild_id}`", inline=False)
    embed.add_field(name="Channel", value=f"#{channel_name}\n`{channel_id}`", inline=False)
    if extra:
        embed.add_field(name="Details", value=extra[:1024], inline=False)
    embed.set_footer(text=f"ID: {interaction.user.id}")
    if interaction.user.display_avatar:
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"log failed: {e}")

async def log_whitelist(action: str, moderator: discord.User, target: discord.User, minutes: int = None):
    channel = bot.get_channel(WHITELIST_LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(WHITELIST_LOG_CHANNEL_ID)
        except Exception as e:
            print(f"whitelist log channel fetch failed: {e}")
            return

    color = 0x57F287 if action == "add" else 0xED4245
    title = "Whitelist Added" if action == "add" else "Whitelist Removed"

    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Moderator", value=f"<@{moderator.id}>", inline=True)
    embed.add_field(name="Target", value=f"<@{target.id}>", inline=True)
    if minutes is not None:
        embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
    embed.set_footer(text=f"Mod: {moderator.id} | Target: {target.id}")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"whitelist log failed: {e}")

def build_invite_link():
    params = {
        "client_id": CLIENT_ID,
        "permissions": "8",
        "scope": "bot applications.commands",
    }
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

def build_user_auth_link():
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds.join",
    }
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

class StopSpamView(discord.ui.View):
    def __init__(self, stop_event: asyncio.Event):
        super().__init__(timeout=300)
        self.stop_event = stop_event

    @discord.ui.button(label="STOP", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop_event.set()
        button.disabled = True
        await interaction.response.edit_message(content="Stopping spam...", view=self)
        self.stop()

@bot.event
async def on_ready():
    print(f"logged in as {bot.user} | {bot.user.id}")
    print(f"owners: {OWNER_IDS}")
    print(f"in {len(bot.guilds)} guild(s)")
    for g in bot.guilds:
        print(f"  - {g.name} ({g.id})")

    try:
        synced = await bot.tree.sync()
        print(f"global sync: {len(synced)} command(s)")
    except Exception as e:
        print(f"global sync failed: {e}")

    for g in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=g)
            synced = await bot.tree.sync(guild=g)
            print(f"guild sync [{g.name}]: {len(synced)} command(s)")
        except Exception as e:
            print(f"guild sync failed [{g.name}]: {e}")

@bot.tree.command(name="sync", description="Force re-sync slash commands (owner only)")
async def sync_cmd(interaction: discord.Interaction):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await log_command(interaction, "sync")
    try:
        if interaction.guild:
            bot.tree.copy_global_to(guild=interaction.guild)
            synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(f"Synced {len(synced)} commands to this server.", ephemeral=True)
        else:
            synced = await bot.tree.sync()
            await interaction.followup.send(f"Global sync: {len(synced)} commands.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Sync error: {e}", ephemeral=True)

@bot.tree.command(name="link", description="Send the bot invite / user auth link")
async def link(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    await log_command(interaction, "link")
    bot_url = build_invite_link()
    user_url = build_user_auth_link()
    await interaction.response.send_message(
        f"**Bot invite:**\n{bot_url}\n\n**User authorize (for force-join):**\n{user_url}",
        ephemeral=True
    )

@bot.tree.command(name="adspam", description="Flood the channel with big join ads")
@app_commands.describe(amount="How many messages (1-50, default 20)")
async def adspam(interaction: discord.Interaction, amount: int = 20):
    if not await must_be_in_required_guild(interaction):
        return
    amount = max(1, min(int(amount), 50))

    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "adspam", extra=f"Amount: {amount}")

    blocks = [
        f"## JOIN USSS\n## JOIN USSS\n## JOIN USSS\n\n{INVITE}\n\n**Slash**\n**Slash**\n2 Online\n3 Members\nEst. Oct 2026\n\n**Join**",
        f"## Server got fucked\n## JOIN USSS\n## JOIN USSS\n\n{INVITE}\n\n2 Online · 3 Members\nEst. Oct 2026",
        f"## JOIN USSS\n## JOIN USSS\n## JOIN USSS\n## JOIN USSS\n\n{INVITE}",
        f"## JOIN NOW\n## JOIN USSS\n\n{INVITE}\n\n**Slash**\n2 Online\n3 Members",
        f"## Server got fucked\n## JOIN USSS\n\n{INVITE}\n\nJoin the raid base.\nEst. Oct 2026",
    ]

    try:
        for _ in range(amount):
            await public_send(interaction, random.choice(blocks))
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f"adspam error: {e}")
        try:
            await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)
        except:
            pass

@bot.tree.command(name="test", description="Test send + delete (checks external app perms)")
async def test(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return

    await interaction.response.send_message("testing...", ephemeral=True)
    await log_command(interaction, "test")

    try:
        msg = await public_send(interaction, "bot online")
        await asyncio.sleep(1.5)
        try:
            await msg.delete()
        except Exception as e:
            print(f"delete failed (ok if external-only): {e}")
        await interaction.followup.send("PASS — message sent.", ephemeral=True)
    except Exception as e:
        print(f"test error: {e}")
        await interaction.followup.send(f"FAIL — `{e}`", ephemeral=True)

@bot.tree.command(name="whitelist", description="Temp whitelist a user (owner only)")
@app_commands.describe(member="User to whitelist", minutes="Duration in minutes (default 60)")
async def whitelist(interaction: discord.Interaction, member: discord.User, minutes: int = 60):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    if minutes < 1:
        minutes = 1
    if minutes > 10080:
        minutes = 10080

    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    data.setdefault("whitelist", {})[str(member.id)] = expires.isoformat()
    save_data(data)

    await log_command(interaction, "whitelist", extra=f"Target: <@{member.id}>\nDuration: {minutes} min")
    await log_whitelist("add", interaction.user, member, minutes)
    await interaction.response.send_message(
        f"Whitelisted {member.mention} for **{minutes} minutes**.\nExpires <t:{int(expires.timestamp())}:R>",
        ephemeral=True
    )

@bot.tree.command(name="unwhitelist", description="Remove a user from the whitelist (owner only)")
@app_commands.describe(member="User to unwhitelist")
async def unwhitelist(interaction: discord.Interaction, member: discord.User):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    data.get("whitelist", {}).pop(str(member.id), None)
    save_data(data)
    await log_command(interaction, "unwhitelist", extra=f"Target: <@{member.id}>")
    await log_whitelist("remove", interaction.user, member)
    await interaction.response.send_message(f"Unwhitelisted {member.mention}", ephemeral=True)

@bot.tree.command(name="blame", description="Send a fake blame message")
@app_commands.describe(member="User to blame (optional)")
async def blame(interaction: discord.Interaction, member: discord.User = None):
    if not await must_be_in_required_guild(interaction):
        return

    target = member or interaction.user
    await interaction.response.send_message("sent", ephemeral=True)
    await log_command(interaction, "blame", extra=f"Target: <@{target.id}>")

    try:
        await public_send(interaction, f"**{target.mention}** just raided this server. Report them.")
    except Exception as e:
        print(f"blame error: {e}")
        await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)

@bot.tree.command(name="ghostping", description="Ghost ping a user")
@app_commands.describe(member="User to ghost ping")
async def ghostping(interaction: discord.Interaction, member: discord.User):
    if not await must_be_in_required_guild(interaction):
        return

    await interaction.response.send_message("sent", ephemeral=True)
    await log_command(interaction, "ghostping", extra=f"Target: <@{member.id}>")

    try:
        msg = await public_send(interaction, member.mention)
        await asyncio.sleep(0.6)
        try:
            await msg.delete()
        except Exception as e:
            print(f"ghostping delete failed: {e}")
    except Exception as e:
        print(f"ghostping error: {e}")
        await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)

@bot.tree.command(name="die", description="Delete every message the bot has tracked (owner only)")
async def die(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    await log_command(interaction, "die")
    deleted = 0
    failed = 0
    seen = set()

    for entry in list(data.get("sent_messages", [])):
        cid = entry.get("channel_id")
        mid = entry.get("message_id")
        if not cid or not mid:
            continue
        key = (cid, mid)
        if key in seen:
            continue
        seen.add(key)
        ch = bot.get_channel(cid)
        if ch is None:
            try:
                ch = await bot.fetch_channel(cid)
            except Exception as e:
                print(f"die fetch channel {cid}: {e}")
                failed += 1
                continue
        try:
            msg = await ch.fetch_message(mid)
            await msg.delete()
            deleted += 1
            await asyncio.sleep(0.4)
        except Exception as e:
            print(f"die delete {mid}: {e}")
            failed += 1

    data["sent_messages"] = []
    save_data(data)

    channel = await resolve_channel(interaction)
    if channel is not None:
        try:
            async for msg in channel.history(limit=200):
                if msg.author.id != bot.user.id:
                    continue
                key = (msg.channel.id, msg.id)
                if key in seen:
                    continue
                try:
                    await msg.delete()
                    deleted += 1
                    seen.add(key)
                    await asyncio.sleep(0.4)
                except Exception as e:
                    print(f"die sweep delete: {e}")
                    failed += 1
        except Exception as e:
            print(f"die history: {e}")

    await interaction.followup.send(
        f"Deleted **{deleted}** messages. Failed: {failed}",
        ephemeral=True
    )

@bot.tree.command(name="editspam", description="Edit-spam a message (whitelist only)")
@app_commands.describe(text="Text to spam via edits", amount="How many edits (1-50, default 12)")
async def editspam(interaction: discord.Interaction, text: str, amount: int = 12):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    amount = max(1, min(int(amount), 50))
    if len(text) > 1900:
        text = text[:1900]

    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "editspam", extra=f"Text: `{text[:200]}`\nAmount: {amount}")

    try:
        channel = await resolve_channel(interaction)
        if channel is not None:
            try:
                msg = await channel.send(text)
                data.setdefault("sent_messages", []).append({
                    "channel_id": msg.channel.id,
                    "message_id": msg.id,
                    "via": "channel",
                })
                save_data(data)
            except Exception as e:
                print(f"editspam channel.send failed: {e}")
                msg = await interaction.followup.send(text, ephemeral=False)
        else:
            msg = await interaction.followup.send(text, ephemeral=False)

        edited = 0
        last_err = None
        for i in range(amount):
            try:
                suffix = "\u200b" * ((i % 5) + 1)
                await msg.edit(content=f"{text}{suffix}")
                edited += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                last_err = e
                print(f"editspam edit #{i}: {e}")
                break

        status = f"editspam done — {edited}/{amount} edits"
        if last_err and edited == 0:
            status = f"edit failed: `{last_err}`"
        await interaction.followup.send(status, ephemeral=True)
    except Exception as e:
        print(f"editspam error: {e}")
        await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)

@bot.tree.command(name="spam", description="Spam the channel (whitelist only) — has STOP button")
@app_commands.describe(text="Text to spam", amount="How many messages (1-50, default 25)")
async def spam(interaction: discord.Interaction, text: str = "@everyone", amount: int = 25):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    amount = max(1, min(int(amount), 50))

    await log_command(interaction, "spam", extra=f"Text: `{text[:200]}`\nAmount: {amount}")
    stop_event = asyncio.Event()
    view = StopSpamView(stop_event)
    await interaction.response.send_message("Spamming... click STOP to cancel.", view=view, ephemeral=True)

    try:
        for _ in range(amount):
            if stop_event.is_set():
                break
            await public_send(interaction, text)
            await asyncio.sleep(0.45)
    except Exception as e:
        print(f"spam error: {e}")
        try:
            await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)
        except:
            pass

    try:
        await interaction.edit_original_response(content="Spam finished / stopped.", view=None)
    except:
        pass

@bot.tree.command(name="dmspam", description="DM spam a user (whitelist only)")
@app_commands.describe(member="User to DM", text="Message content", amount="How many DMs (1-50, default 8)")
async def dmspam(interaction: discord.Interaction, member: discord.User, text: str = "you got hit", amount: int = 8):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    amount = max(1, min(int(amount), 50))

    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "dmspam", extra=f"Target: <@{member.id}>\nText: `{text[:200]}`\nAmount: {amount}")

    for _ in range(amount):
        try:
            await member.send(text)
            await asyncio.sleep(0.7)
        except Exception as e:
            print(f"dmspam error: {e}")
            break

@bot.tree.command(name="flood", description="Send long empty paragraphs to flood chat (whitelist only)")
@app_commands.describe(amount="How many flood messages (1-50, default 10)")
async def flood(interaction: discord.Interaction, amount: int = 10):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    amount = max(1, min(int(amount), 50))

    stop_event = asyncio.Event()
    view = StopSpamView(stop_event)
    await interaction.response.send_message("Flooding... click STOP to cancel.", view=view, ephemeral=True)
    await log_command(interaction, "flood", extra=f"Amount: {amount}")

    try:
        for _ in range(amount):
            if stop_event.is_set():
                break
            await public_send(interaction, FLOOD_BLOCK)
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f"flood error: {e}")
        try:
            await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)
        except:
            pass

    try:
        await interaction.edit_original_response(content="Flood finished / stopped.", view=None)
    except:
        pass

ROASTS = [
    "{u} is the reason the mute button was invented.",
    "{u} has the personality of a loading screen.",
    "{u} is living proof that evolution can go in reverse.",
    "If brains were dynamite, {u} couldn't blow their nose.",
    "{u} brings everyone so much joy... when they leave the room.",
    "{u}'s Wi-Fi has better connections than they do.",
    "Somewhere out there, a tree is working hard to produce oxygen for {u}. It should stop.",
    "{u} is not stupid — they're just highly advanced at being wrong.",
    "I'd agree with {u}, but then we'd both be wrong.",
    "{u} has zero rizz and infinite confidence. Terrifying combo.",
    "Even ChatGPT needs a break after talking to {u}.",
    "{u} is the human version of a participation trophy.",
    "If {u} was a spice, they'd be flour.",
    "{u} walked into a bar. Everyone else left.",
    "Mirror called. It wants a refund after seeing {u}.",
    "{u} is why aliens won't visit Earth.",
    "Your opinion is important {u}. Please keep it to yourself.",
    "{u} has the aura of a buffering YouTube video.",
    "I would roast {u} harder, but I don't bully the disabled.",
    "{u} is the main character... of a cautionary tale.",
]

@bot.tree.command(name="roast", description="Roast a user")
@app_commands.describe(member="User to roast (optional, defaults to you)")
async def roast(interaction: discord.Interaction, member: discord.User = None):
    if not await must_be_in_required_guild(interaction):
        return

    target = member or interaction.user
    await interaction.response.send_message("sent", ephemeral=True)
    await log_command(interaction, "roast", extra=f"Target: <@{target.id}>")

    line = random.choice(ROASTS).format(u=target.mention)
    try:
        await public_send(interaction, line)
    except Exception as e:
        print(f"roast error: {e}")
        await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)

@bot.tree.command(name="serverjoin", description="Force all authorized users into a server (owner only)")
@app_commands.describe(server_id="Target guild ID")
async def serverjoin(interaction: discord.Interaction, server_id: str):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    await log_command(interaction, "serverjoin", extra=f"Target guild: `{server_id}`")

    try:
        guild_id = int(server_id.strip())
    except ValueError:
        return await interaction.followup.send("Invalid server ID.", ephemeral=True)

    authorized = data.get("authorized", {})
    if not authorized:
        return await interaction.followup.send("No authorized users. They must use the user-auth link first.", ephemeral=True)

    success = 0
    failed = 0

    for uid, info in list(authorized.items()):
        access = info.get("access_token")
        if not access:
            failed += 1
            continue
        try:
            r = http_requests.put(
                f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}",
                headers={
                    "Authorization": f"Bot {TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"access_token": access},
            )
            if r.status_code in (201, 204):
                success += 1
            else:
                failed += 1
                print(f"join fail {uid}: {r.status_code} {r.text}")
        except Exception as e:
            failed += 1
            print(f"join error {uid}: {e}")
        await asyncio.sleep(0.4)

    await interaction.followup.send(
        f"Force-join done. Success: {success} | Failed: {failed}",
        ephemeral=True
    )

bot.run(TOKEN)
