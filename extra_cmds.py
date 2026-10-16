# auto-loaded command block
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

@bot.tree.command(name="editspam", description="Edit-spam a message — scrambles letters each edit (whitelist only)")
@app_commands.describe(
    text="Base text to send (letters get shuffled on every edit)",
    amount="How many edits (1-50, default 12)",
)
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
                await log_error("editspam.channel.send", e)
                msg = await interaction.followup.send(text, ephemeral=False)
        else:
            msg = await interaction.followup.send(text, ephemeral=False)

        edited = 0
        last_err = None
        for i in range(amount):
            try:
                scrambled = scramble_text(text)
                suffix = "\u200b" * ((i % 3) + 1)
                content = (scrambled + suffix)[:2000]
                await msg.edit(content=content)
                edited += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                last_err = e
                await log_error(f"editspam.edit#{i}", e, extra=f"text[:80]={text[:80]!r}")
                break

        status = f"editspam done — {edited}/{amount} edits"
        if last_err and edited == 0:
            status = f"edit failed: `{last_err}`"
        await interaction.followup.send(status, ephemeral=True)
    except Exception as e:
        await log_error("editspam", e)
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
        await log_error("spam", e)
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
            await log_error("dmspam", e)
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
        await log_error("flood", e)
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
    "I'd agree with {u}, but then we'd both be wrong.",
    "{u} has zero rizz and infinite confidence. Terrifying combo.",
    "If {u} was a spice, they'd be flour.",
    "{u} is why aliens won't visit Earth.",
    "{u} has the aura of a buffering YouTube video.",
    "{u} is the main character... of a cautionary tale.",
]

@bot.tree.command(name="roast", description="Roast a user")
@app_commands.describe(
    member="User to roast (optional, defaults to you)",
    amount="How many roast messages (1-50, default 5)",
)
async def roast(interaction: discord.Interaction, member: discord.User = None, amount: int = 5):
    if not await must_be_in_required_guild(interaction):
        return

    amount = max(1, min(int(amount), 50))
    target = member or interaction.user
    await interaction.response.send_message("sent", ephemeral=True)
    await log_command(interaction, "roast", extra=f"Target: <@{target.id}>\nAmount: {amount}")

    try:
        for _ in range(amount):
            line = random.choice(ROASTS).format(u=target.mention)
            await public_send(interaction, line)
            await asyncio.sleep(0.45)
    except Exception as e:
        await log_error("roast", e, extra=f"target={target.id}")
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
