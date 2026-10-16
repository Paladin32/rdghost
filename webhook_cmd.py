# webhook_cmd.py - loaded by bot.py
import asyncio
import discord
from discord import app_commands
import requests as http_requests

def setup(bot, *, must_be_in_required_guild, is_whitelisted_user, log_command, log_error):
    @bot.tree.command(name="webhookraid", description="Spam a Discord webhook URL (whitelist only — bot does not need to be in the server)")
    @app_commands.describe(
        webhook_url="Full Discord webhook URL (https://discord.com/api/webhooks/...)",
        text="Message content to spam",
        amount="How many messages (1-100, default 25)",
        username="Optional webhook display name override",
        avatar_url="Optional avatar URL override",
    )
    async def webhookraid(
        interaction: discord.Interaction,
        webhook_url: str,
        text: str = "@everyone",
        amount: int = 25,
        username: str = None,
        avatar_url: str = None,
    ):
        if not await must_be_in_required_guild(interaction):
            return
        if not is_whitelisted_user(interaction.user.id):
            return await interaction.response.send_message("Whitelist only.", ephemeral=True)

        amount = max(1, min(int(amount), 100))
        webhook_url = webhook_url.strip()
        if not (
            webhook_url.startswith("https://discord.com/api/webhooks/")
            or webhook_url.startswith("https://discordapp.com/api/webhooks/")
            or webhook_url.startswith("https://canary.discord.com/api/webhooks/")
            or webhook_url.startswith("https://ptb.discord.com/api/webhooks/")
        ):
            return await interaction.response.send_message(
                "Invalid webhook URL. Must be a Discord webhook link.",
                ephemeral=True,
            )
        if len(text) > 2000:
            text = text[:2000]

        await interaction.response.send_message("running...", ephemeral=True)
        await log_command(
            interaction,
            "webhookraid",
            extra=f"Amount: {amount}\nText: `{text[:150]}`\nURL: `{webhook_url[:80]}...`",
        )

        payload = {"content": text}
        if username:
            payload["username"] = username[:80]
        if avatar_url:
            payload["avatar_url"] = avatar_url

        sent = 0
        last_err = None
        for i in range(amount):
            try:
                r = http_requests.post(webhook_url, json=payload, timeout=10)
                if r.status_code in (200, 204):
                    sent += 1
                elif r.status_code == 429:
                    try:
                        retry = float(r.json().get("retry_after", 1.5))
                    except Exception:
                        retry = 1.5
                    await asyncio.sleep(retry)
                    r2 = http_requests.post(webhook_url, json=payload, timeout=10)
                    if r2.status_code in (200, 204):
                        sent += 1
                    else:
                        last_err = f"HTTP {r2.status_code}: {r2.text[:200]}"
                        await log_error("webhookraid.rate", last_err, extra=f"i={i}")
                        break
                else:
                    last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                    await log_error("webhookraid", last_err, extra=f"i={i}")
                    break
                await asyncio.sleep(0.35)
            except Exception as e:
                last_err = str(e)
                await log_error("webhookraid", e, extra=f"i={i}")
                break

        status = f"webhookraid done — {sent}/{amount} sent"
        if last_err and sent == 0:
            status = f"webhookraid failed: `{last_err}`"
        elif last_err:
            status += f" | stopped: `{last_err}`"
        try:
            await interaction.followup.send(status, ephemeral=True)
        except Exception:
            pass
