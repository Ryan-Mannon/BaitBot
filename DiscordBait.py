import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
from discord.ui import View, Button
import json
import os
import time
import asyncio
import subprocess

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "bait_data.json"
AUTO_REACT_EMOJI = "🎣"
OWNER_ID = 291415368722022400
GIT_REPO_PATH = "/root/BaitBot"  # Path to local Git repo
# ----------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- GIT HELPERS ----------
async def async_push_json():
    """Commit and push the JSON file to GitHub asynchronously."""
    try:
        cmds = [
            ["git", "-C", GIT_REPO_PATH, "add", DATA_FILE],
            ["git", "-C", GIT_REPO_PATH, "commit", "-m", f"Update {DATA_FILE} at {time.strftime('%Y-%m-%d %H:%M:%S')}"],
            ["git", "-C", GIT_REPO_PATH, "push"]
        ]
        for cmd in cmds:
            subprocess.run(cmd, check=True)
        print(f"[INFO] {DATA_FILE} pushed to GitHub successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git push failed: {e}")

def pull_latest_json():
    """Pull the latest JSON file from GitHub synchronously."""
    try:
        subprocess.run(["git", "-C", GIT_REPO_PATH, "pull"], check=True)
        print(f"[INFO] Pulled latest {DATA_FILE} from GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git pull failed: {e}")

# ---------- DATA HELPERS ----------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"scores": {}, "baits": {}, "debait_cooldowns": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ---------- PULL LATEST DATA ON STARTUP ----------
pull_latest_json()
data = load_data()
scores = data.get("scores", {})
baits_data = data.get("baits", {})
debait_cooldowns = data.get("debait_cooldowns", {})

# ---------- BOT EVENTS ----------
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
@bot.command()
@commands.cooldown(1, 86400, commands.BucketType.user)
async def bait(ctx, member: discord.Member, *, reason: str = None):
    user_id = str(member.id)
    scores[user_id] = scores.get(user_id, 0) + 1

    if reason:
        if user_id not in baits_data:
            baits_data[user_id] = []
        baits_data[user_id].append(reason.strip())
        if len(baits_data[user_id]) > 10:
            baits_data[user_id] = baits_data[user_id][-10:]

    save_data({"scores": scores, "baits": baits_data, "debait_cooldowns": debait_cooldowns})
    asyncio.create_task(async_push_json())

    reply = f"🎣 **{member.display_name}** has baited! ➕ 1 point (Total: **{scores[user_id]}**)"
    if reason:
        reply += "\nReason recorded!"
    await ctx.send(reply)

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

    scores[user_id] = max(scores.get(user_id, 0) - 1, 0)
    debait_cooldowns[author_id] = now

    save_data({"scores": scores, "baits": baits_data, "debait_cooldowns": debait_cooldowns})
    asyncio.create_task(async_push_json())

    await ctx.send(f"🪝 **{member.display_name}** lost 1 bait point (Total: **{scores[user_id]}**)!")

@bot.command()
async def score(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    await ctx.send(f"**{member.display_name}** has **{scores.get(user_id,0)}** bait points.")

# --- Admin-only delete ---
@bot.command()
async def delete(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("You are not authorized to use this command.")
        return

    user_id = str(member.id)
    if user_id in scores or user_id in baits_data or user_id in debait_cooldowns:
        backup_file = f"bait_data_backup_{int(time.time())}.json"
        save_data({
            "scores": scores,
            "baits": baits_data,
            "debait_cooldowns": debait_cooldowns
        })
        await ctx.send(f"Backed up current data to `{backup_file}`")

        scores.pop(user_id, None)
        baits_data.pop(user_id, None)
        debait_cooldowns.pop(user_id, None)

        save_data({"scores": scores, "baits": baits_data, "debait_cooldowns": debait_cooldowns})
        asyncio.create_task(async_push_json())

        await ctx.send(f"All data for **{member.display_name}** has been deleted.")
    else:
        await ctx.send(f"No data found for **{member.display_name}**.")




# --- Leaderboard ---
@bot.command()
async def leaderboard(ctx):
    data = load_data()
    scores = data.get("scores", {})

    if not scores:
        await ctx.send("No bait has been recorded yet 🐟")
        return

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

bot.run(BOT_TOKEN)
