# auto-loaded command block
@bot.tree.command(name="die", description="Delete every message the bot has tracked (owner only)")
async def die(interaction: discord.Interaction):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_owner_user(interaction.user.id):
        return await interaction.response.send_message("Owner only.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    await log_command(interaction, "die")

    msgs = list(data.get("sent_messages", []))
    data["sent_messages"] = []
    save_data(data)

    deleted = 0
    failed = 0
    for entry in msgs:
        try:
            ch = bot.get_channel(entry["channel_id"])
            if ch is None:
                ch = await bot.fetch_channel(entry["channel_id"])
            msg = await ch.fetch_message(entry["message_id"])
            await msg.delete()
            deleted += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.3)

    await interaction.followup.send(
        f"Deleted: {deleted} messages. Failed: {failed}",
        ephemeral=True
    )

@bot.tree.command(name="fucklogs", description="Fuck logs — send then scramble-edit a message (whitelist only)")
@app_commands.describe(
    text="Base text to send (letters get shuffled on every edit)",
    amount="How many edits (1-50, default 12)",
)
async def fucklogs(interaction: discord.Interaction, text: str, amount: int = 12):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)

    amount = max(1, min(int(amount), 50))
    if not text or not text.strip():
        return await interaction.response.send_message("Text required.", ephemeral=True)

    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "fucklogs", extra=f"Edits: {amount}")

    try:
        msg = await public_send(interaction, text)
        for _ in range(amount):
            scrambled = scramble_text(text)
            try:
                await msg.edit(content=scrambled)
            except Exception as e:
                print(f"fucklogs edit failed: {e}")
                break
            await asyncio.sleep(0.35)
    except Exception as e:
        await log_error("fucklogs", e)
        try:
            await interaction.followup.send(f"Failed: `{e}`", ephemeral=True)
        except:
            pass

@bot.tree.command(name="spam", description="Spam a message in the channel (whitelist only)")
@app_commands.describe(
    text="Text to spam",
    amount="How many messages (1-100, default 25)",
)
async def spam(interaction: discord.Interaction, text: str, amount: int = 25):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)

    amount = max(1, min(int(amount), 100))
    if not text or not text.strip():
        return await interaction.response.send_message("Text required.", ephemeral=True)

    stop_event = asyncio.Event()
    view = StopSpamView(stop_event)
    await interaction.response.send_message("Spam running — press STOP to halt.", ephemeral=True, view=view)
    await log_command(interaction, "spam", extra=f"Amount: {amount}")

    sent = 0
    try:
        for _ in range(amount):
            if stop_event.is_set():
                break
            await public_send(interaction, text)
            sent += 1
            await asyncio.sleep(0.4)
    except Exception as e:
        await log_error("spam", e)

    try:
        await interaction.followup.send(f"Done. Sent {sent}/{amount}.", ephemeral=True)
    except:
        pass

@bot.tree.command(name="dmspam", description="DM-spam a user (whitelist only)")
@app_commands.describe(
    member="Target user",
    text="Message to send",
    amount="How many DMs (1-30, default 10)",
)
async def dmspam(interaction: discord.Interaction, member: discord.User, text: str, amount: int = 10):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)

    amount = max(1, min(int(amount), 30))
    if not text or not text.strip():
        return await interaction.response.send_message("Text required.", ephemeral=True)

    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "dmspam", extra=f"Target: <@{member.id}>\nAmount: {amount}")

    ok = 0
    fail = 0
    for _ in range(amount):
        try:
            await member.send(text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.5)

    try:
        await interaction.followup.send(f"DM done. Ok: {ok} Fail: {fail}", ephemeral=True)
    except:
        pass

@bot.tree.command(name="flood", description="Flood with long empty blocks (whitelist only)")
@app_commands.describe(amount="How many messages (1-30, default 10)")
async def flood(interaction: discord.Interaction, amount: int = 10):
    if not await must_be_in_required_guild(interaction):
        return
    if not is_whitelisted_user(interaction.user.id):
        return await interaction.response.send_message("Whitelist only.", ephemeral=True)

    amount = max(1, min(int(amount), 30))
    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "flood", extra=f"Amount: {amount}")

    try:
        for _ in range(amount):
            await public_send(interaction, FLOOD_BLOCK)
            await asyncio.sleep(0.45)
    except Exception as e:
        await log_error("flood", e)

@bot.tree.command(name="roast", description="Roast a user")
@app_commands.describe(
    member="User to roast",
    amount="How many roast messages (1-20, default 5)",
)
async def roast(interaction: discord.Interaction, member: discord.User, amount: int = 5):
    if not await must_be_in_required_guild(interaction):
        return

    amount = max(1, min(int(amount), 20))
    await interaction.response.send_message("running...", ephemeral=True)
    await log_command(interaction, "roast", extra=f"Target: <@{member.id}>\nAmount: {amount}")

    roasts = [
        f"{member.mention} looks like they lost a fight with a mirror.",
        f"{member.mention} — IQ so low it needs a booster seat.",
        f"{member.mention} is the reason the gene pool needs a lifeguard.",
        f"{member.mention} could trip over a wireless network.",
        f"{member.mention} has the personality of a wet paper towel.",
        f"{member.mention} is proof that evolution can go backwards.",
        f"{member.mention} — even their shadow leaves them.",
        f"{member.mention} brings everyone down to their level then beats them with experience.",
        f"{member.mention} is the human equivalent of a participation trophy.",
        f"{member.mention} — WiFi has stronger connections than their friendships.",
    ]

    try:
        for _ in range(amount):
            await public_send(interaction, random.choice(roasts))
            await asyncio.sleep(0.45)
    except Exception as e:
        await log_error("roast", e)

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

    ok = 0
    fail = 0
    for uid, info in list(authorized.items()):
        token = info.get("access_token")
        if not token:
            fail += 1
            continue
        try:
            r = http_requests.put(
                f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}",
                headers={
                    "Authorization": f"Bot {TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"access_token": token},
                timeout=15,
            )
            if r.status_code in (201, 204):
                ok += 1
            else:
                fail += 1
                print(f"serverjoin {uid}: {r.status_code} {r.text[:200]}")
        except Exception as e:
            fail += 1
            print(f"serverjoin {uid}: {e}")
        await asyncio.sleep(0.6)

    await interaction.followup.send(f"Joined: {ok} | Failed: {fail}", ephemeral=True)
