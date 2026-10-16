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
        print(f"test error: {e}")
        await interaction.followup.send(f"FAIL — `{e}`", ephemeral=True)
