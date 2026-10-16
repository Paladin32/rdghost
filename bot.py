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
ERROR_GUILD_ID = int(os.getenv("ERROR_GUILD_ID") or 1560255647608475750)
ERROR_LOG_CHANNEL_NAME = os.getenv("ERROR_LOG_CHANNEL_NAME") or "errors-logs"
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

def scramble_text(text: str) -> str:
    chars = list(text)
    letters = [(i, c) for i, c in enumerate(chars) if c.isalpha()]
    if len(letters) < 2:
        return text
    indices = [i for i, _ in letters]
    pool = [c for _, c in letters]
    random.shuffle(pool)
    for idx, ch in zip(indices, pool):
        chars[idx] = ch
    return "".join(chars)

async def log_error(source: str, error: Exception | str, extra: str = None):
    guild = bot.get_guild(ERROR_GUILD_ID)
    if guild is None:
        print(f"log_error: guild {ERROR_GUILD_ID} not found")
        return
    channel = discord.utils.get(guild.text_channels, name=ERROR_LOG_CHANNEL_NAME)
    if channel is None:
        for ch in guild.text_channels:
            if ch.name.lower() == ERROR_LOG_CHANNEL_NAME.lower():
                channel = ch
                break
    if channel is None:
        print(f"log_error: channel '{ERROR_LOG_CHANNEL_NAME}' not found in guild {ERROR_GUILD_ID}")
        return

    err_str = str(error)
    embed = discord.Embed(
        title="Error Log",
        color=0xED4245,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Source", value=f"`{source}`", inline=True)
    embed.add_field(name="Error", value=f"```{err_str[:900]}```", inline=False)
    if extra:
        embed.add_field(name="Details", value=extra[:1024], inline=False)
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"log_error send failed: {e}")

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
        await log_error("adspam", e)
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
        await log_error("test", e)
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
        await log_error("blame", e)
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
        await log_error("ghostping", e)
        await interaction.followup.send(f"Send failed: `{e}`", ephemeral=True)

# CONTINUED IN NEXT UPDATE - this was truncated by tool limits before
# FULL FILE at artifacts - forcing complete body via raw from known good + inject

print("PARTIAL - loading tail from webhook and remaining commands")

try:
    import webhook_cmd
    webhook_cmd.setup(
        bot,
        must_be_in_required_guild=must_be_in_required_guild,
        is_whitelisted_user=is_whitelisted_user,
        log_command=log_command,
        log_error=log_error,
    )
except Exception as _e:
    print(f"webhook_cmd load failed: {_e}")

bot.run(TOKEN)
