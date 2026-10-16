# status_panel.py - /status owner panel with live updates
import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta

def setup_status(bot, *, is_owner_user, log_command, data, save_data, ERROR_GUILD_ID=None):
    def _today_key():
        # IST = UTC+5:30
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).strftime("%d-%m-%Y")

    def _stats():
        s = data.setdefault("status_stats", {})
        day = _today_key()
        if s.get("day") != day:
            s["day"] = day
            s["joins"] = 0
            s["leaves"] = 0
            save_data(data)
        return s

    async def _find_status_message():
        entry = data.get("status_panel")
        if not entry:
            return None
        ch = bot.get_channel(entry.get("channel_id"))
        if ch is None:
            try:
                ch = await bot.fetch_channel(entry["channel_id"])
            except Exception:
                return None
        try:
            return await ch.fetch_message(entry["message_id"])
        except Exception:
            return None

    def _build_embeds():
        s = _stats()
        joins = int(s.get("joins", 0))
        leaves = int(s.get("leaves", 0))
        net = joins - leaves
        day = s.get("day", _today_key())

        user_online = bot.is_ready()
        guild_online = len(bot.guilds) > 0

        def dot(ok):
            return "🟢 Online" if ok else "🔴 Offline"

        e1 = discord.Embed(title="Bot Status", color=0x2B2D31)
        e1.add_field(name="User Install", value=dot(user_online), inline=False)
        e1.add_field(name="Guild Install", value=dot(guild_online), inline=False)

        e2 = discord.Embed(
            title=f"Server Statistics — {len(bot.guilds)} guilds",
            color=0x2B2D31,
            description=(
                f"```\n"
                f"Today : {day}\n"
                f"+ Joins: {joins}\n"
                f"- Leaves: {leaves}\n"
                f"= Net: {'+' if net >= 0 else ''}{net}\n"
                f"```"
            ),
        )
        e2.set_footer(text="Resets daily at 12 AM IST")
        return [e1, e2]

    async def refresh_status_panel():
        msg = await _find_status_message()
        if msg is None:
            return
        try:
            await msg.edit(embeds=_build_embeds())
        except Exception as e:
            print(f"status panel edit failed: {e}")

    @bot.tree.command(name="status", description="Post live bot status panel (owner only)")
    async def status_cmd(interaction: discord.Interaction):
        if not is_owner_user(interaction.user.id):
            return await interaction.response.send_message("Owner only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await log_command(interaction, "status")

        embeds = _build_embeds()
        channel = interaction.channel
        try:
            msg = await channel.send(embeds=embeds)
        except Exception as e:
            return await interaction.followup.send(f"Failed to post panel: `{e}`", ephemeral=True)

        data["status_panel"] = {
            "channel_id": msg.channel.id,
            "message_id": msg.id,
        }
        save_data(data)
        await interaction.followup.send("Status panel posted. It will auto-update on join/leave.", ephemeral=True)

    @bot.event
    async def on_guild_join(guild):
        s = _stats()
        s["joins"] = int(s.get("joins", 0)) + 1
        save_data(data)
        await refresh_status_panel()

    @bot.event
    async def on_guild_remove(guild):
        s = _stats()
        s["leaves"] = int(s.get("leaves", 0)) + 1
        save_data(data)
        await refresh_status_panel()

    bot.refresh_status_panel = refresh_status_panel
