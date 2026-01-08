import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
from discord.ui import View, Button
import json
import os
import time

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "bait_data.json"
AUTO_REACT_EMOJI = "🎣"
# ----------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- DATA HELPERS ----------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"scores": {}, "baits": {}, "debait_cooldowns": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()
scores = data.get("scores", {})
baits_data = data.get("baits", {})
debait_cooldowns = data.get("debait_cooldowns", {})
# ---------------------------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ---------- AUTO-REACT TOP SCORER ----------
def get_top_scorer():
    if not scores:
        return None
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_user_id, top_score = sorted_scores[0]
    return int(top_user_id)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Auto-react for top scorer
    top_scorer_id = get_top_scorer()
    if top_scorer_id and message.author.id == top_scorer_id:
        try:
            await message.add_reaction(AUTO_REACT_EMOJI)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

    await bot.process_commands(message)

# ---------- COMMANDS ----------

# --- Bait command ---
@bot.command()
@commands.cooldown(1, 1800, commands.BucketType.user)
async def bait(ctx, member: discord.Member, *, reason: str = None):

    user_id = str(member.id)

    # Update score
    scores[user_id] = scores.get(user_id, 0) + 1


    # Store reason (max 10)
    if reason:
        if user_id not in baits_data:
            baits_data[user_id] = []
        baits_data[user_id].append(reason.strip())
        if len(baits_data[user_id]) > 10:
            baits_data[user_id] = baits_data[user_id][-10:]

    save_data({"scores": scores, "baits": baits_data, "debait_cooldowns": debait_cooldowns})

    reply = f"🎣 **{member.display_name}** has baited! ➕ 1 point (Total: **{scores[user_id]}**)"
    if reason:
        reply += "\n Reason recorded!"
    await ctx.send(reply)

# --- Debait command ---
@bot.command()
async def debait(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        await ctx.send("You cannot debait yourself!")
        return

    author_id = str(ctx.author.id)
    user_id = str(member.id)

    now = time.time()
    last_used = debait_cooldowns.get(author_id, 0)
    cooldown_seconds = 86400  # 24 hours

    if now - last_used < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - last_used))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await ctx.send(f"Wait **{hours}h {minutes}m**")
        return

    # Subtract point (cannot go below 0)
    scores[user_id] = max(scores.get(user_id, 0) - 1, 0)

    # Update cooldown
    debait_cooldowns[author_id] = now

    save_data({"scores": scores, "baits": baits_data, "debait_cooldowns": debait_cooldowns})

    await ctx.send(f"🪝 **{member.display_name}** lost 1 bait point (Total: **{scores[user_id]}**)!")

# --- Check score ---
@bot.command()
async def score(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    await ctx.send(f"**{member.display_name}** has **{scores.get(user_id,0)}** bait points.")





# --- Paginated leaderboard ---
@bot.command()
async def leaderboard(ctx):
    if not scores:
        await ctx.send("No bait has been recorded yet 🐟")
        return

    # Sort all users by score descending
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    pages = [sorted_scores[i:i+10] for i in range(0, len(sorted_scores), 10)]
    current_page = 0

    async def make_embed(page_index):
        embed = discord.Embed(
            title="🎣 Bait Leaderboard",
            color=discord.Color.gold()
        )
        lines = []
        for i, (user_id, score) in enumerate(pages[page_index]):
            user = await bot.fetch_user(int(user_id))
            lines.append(f"#{i+1 + page_index*10} — {user.display_name}: **{score}**")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {page_index+1}/{len(pages)}")
        return embed

    embed = await make_embed(current_page)
    view = View()

    if len(pages) > 1:
        button_prev = Button(label="⬅️", style=discord.ButtonStyle.gray)
        button_next = Button(label="➡️", style=discord.ButtonStyle.gray)

        async def prev_callback(interaction):
            nonlocal current_page
            if current_page > 0:
                current_page -= 1
                new_embed = await make_embed(current_page)
                await interaction.response.edit_message(embed=new_embed, view=view)
            else:
                await interaction.response.defer()

        async def next_callback(interaction):
            nonlocal current_page
            if current_page < len(pages) - 1:
                current_page += 1
                new_embed = await make_embed(current_page)
                await interaction.response.edit_message(embed=new_embed, view=view)
            else:
                await interaction.response.defer()

        button_prev.callback = prev_callback
        button_next.callback = next_callback
        view.add_item(button_prev)
        view.add_item(button_next)

    await ctx.send(embed=embed, view=view)






# --- Cooldowns command ---
@bot.command()
async def cooldowns(ctx):
    messages = []

    # Bait cooldown
    bait_cooldown = bot.get_command("bait").get_cooldown_retry_after(ctx)
    if bait_cooldown:
        bait_hours = int(bait_cooldown // 3600)
        bait_minutes = int((bait_cooldown % 3600) // 60)
        bait_seconds = int(bait_cooldown % 60)
        bait_str = ""
        if bait_hours > 0:
            bait_str += f"{bait_hours}h "
        if bait_minutes > 0 or bait_hours > 0:
            bait_str += f"{bait_minutes}m "
        bait_str += f"{bait_seconds}s"
        messages.append(f"🎣 **Bait:** {bait_str}")
    else:
        messages.append("🎣 **Bait:** Ready!")

    # Debait cooldown
    author_id = str(ctx.author.id)
    now = time.time()
    last_used = debait_cooldowns.get(author_id, 0)
    remaining = int(max(0, 86400 - (now - last_used)))
    if remaining > 0:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        messages.append(f"🪝 **Debait:** {hours}h {minutes}m remaining")
    else:
        messages.append("🪝 **Debait:** Ready!")

    await ctx.send("\n".join(messages))

# --- Show bait reasons (paginated) ---
@bot.command()
async def baits(ctx, member: discord.Member):
    user_id = str(member.id)
    if user_id not in baits_data or len(baits_data[user_id]) == 0:
        await ctx.send(f"**{member.display_name}** has no recorded bait reasons.")
        return

    reasons = baits_data[user_id]
    pages = [reasons[i:i+10] for i in range(0, len(reasons), 10)]
    current_page = 0

    embed = discord.Embed(
        title=f"🎣 {member.display_name}'s Bait Reasons",
        description="\n".join(f"{i+1}. {r}" for i, r in enumerate(pages[current_page])),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Page {current_page+1}/{len(pages)}")

    view = View()

    if len(pages) > 1:
        button_prev = Button(label="⬅️", style=discord.ButtonStyle.gray)
        button_next = Button(label="➡️", style=discord.ButtonStyle.gray)

        async def prev_callback(interaction):
            nonlocal current_page
            if current_page > 0:
                current_page -= 1
                embed.description = "\n".join(f"{i+1 + current_page*10}. {r}" for i, r in enumerate(pages[current_page]))
                embed.set_footer(text=f"Page {current_page+1}/{len(pages)}")
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.defer()

        async def next_callback(interaction):
            nonlocal current_page
            if current_page < len(pages)-1:
                current_page += 1
                embed.description = "\n".join(f"{i+1 + current_page*10}. {r}" for i, r in enumerate(pages[current_page]))
                embed.set_footer(text=f"Page {current_page+1}/{len(pages)}")
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.defer()

        button_prev.callback = prev_callback
        button_next.callback = next_callback
        view.add_item(button_prev)
        view.add_item(button_next)

    await ctx.send(embed=embed, view=view)


# --- Command to display available commands ---
@bot.command()
async def commands(ctx):
    embed = discord.Embed(
        title="🎣 Bait Bot Commands",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="!bait @user <reason>",
        value="Add 1 point to a user for baiting. Reason optional. 30-minute cooldown",
        inline=False
    )

    embed.add_field(
        name="!debait @user",
        value="Remove 1 point from a user. 24-hour cooldown.",
        inline=False
    )

    embed.add_field(
        name="!score @user",
        value="Check the bait score of a user (defaults to yourself if no user is mentioned).",
        inline=False
    )

    embed.add_field(
        name="!leaderboard",
        value="Display the top 10 users by bait points.",
        inline=False
    )

    embed.add_field(
        name="!baits @user",
        value="View the most recent 10 bait reasons for a user.",
        inline=False
    )

    embed.add_field(
        name="!cooldowns",
        value="See your current command cooldowns for bait and debait.",
        inline=False
    )

    await ctx.send(embed=embed)


# ---------- COOLDOWN ERROR HANDLER ----------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        remaining = int(error.retry_after)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60

        time_parts = []
        if hours > 0:
            time_parts.append(f"{hours}h")
        if minutes > 0:
            time_parts.append(f"{minutes}m")
        time_parts.append(f"{seconds}s")

        await ctx.send(f"Wait {' '.join(time_parts)} before using this command again.")
    else:
        raise error

# ------------------------------
bot.run(BOT_TOKEN)
