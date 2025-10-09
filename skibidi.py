import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import sqlite3
from flask import Flask
from threading import Thread

# ===== Flask server cho Render =====
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot đang chạy!"
Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))).start()

# ===== Database SQLite =====
conn = sqlite3.connect("inactivity.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS inactivity (
    member_id TEXT PRIMARY KEY,
    guild_id TEXT,
    last_seen TIMESTAMP,
    role_added BOOLEAN DEFAULT 0
)
""")
conn.commit()

# ===== Bot Discord =====
TOKEN = os.getenv("TOKEN")
ROLE_NAME = "💤 Tín Đồ Ngủ Đông"
INACTIVE_DAYS = 30

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.presences = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Task: check inactivity & gán role =====
@tasks.loop(hours=24)
async def check_inactivity():
    now = datetime.now(timezone.utc)
    print("🔍 Bắt đầu kiểm tra thành viên không hoạt động...")
    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=ROLE_NAME)
        if not role:
            print(f"⚠️ Không tìm thấy role '{ROLE_NAME}' trong server '{guild.name}'")
            continue

        for member in guild.members:
            if member.bot:
                continue

            # Cập nhật last_seen trong DB
            c.execute("SELECT last_seen, role_added FROM inactivity WHERE member_id=?", (str(member.id),))
            row = c.fetchone()
            last_seen, role_added = (row if row else (None, 0))

            if member.activity is None and str(member.status) == "offline":
                c.execute("""
                    INSERT INTO inactivity (member_id, guild_id, last_seen, role_added)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(member_id) DO UPDATE SET last_seen=excluded.last_seen
                """, (str(member.id), str(guild.id), now, role_added))
                conn.commit()
                last_seen = now

            # Gán role nếu đủ 30 ngày offline
            if last_seen and (now - last_seen).days >= INACTIVE_DAYS and role_added == 0:
                try:
                    await member.add_roles(role)
                    c.execute("UPDATE inactivity SET role_added=1 WHERE member_id=?", (str(member.id),))
                    conn.commit()
                    print(f"✅ Gán role '{ROLE_NAME}' cho {member.name}")
                except discord.Forbidden:
                    print(f"🚫 Không đủ quyền để gán role cho {member.name}")
                except Exception as e:
                    print(f"⚠️ Lỗi khi gán role cho {member.name}: {e}")
    print("✅ Kiểm tra hoàn tất!")

# ===== Command: test bot =====
@bot.command()
async def test(ctx):
    await ctx.send("✅ Bot đang hoạt động và kiểm tra mỗi 24h 🕓")

# ===== Command: list offline members =====
@bot.command()
async def list_off(ctx):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if not role:
        await ctx.send(f"⚠️ Không tìm thấy role '{ROLE_NAME}'")
        return

    offline_members = [f"{m.name}#{m.discriminator}" for m in role.members if str(m.status) == "offline"]
    if offline_members:
        await ctx.send("📋 **Danh sách member offline với role ngủ đông:**\n" + "\n".join(offline_members))
    else:
        await ctx.send("✅ Không có member offline nào với role này.")

# ===== Command: remove role =====
@bot.command()
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if not role:
        await ctx.send(f"⚠️ Không tìm thấy role '{ROLE_NAME}'")
        return

    bot_member = guild.me
    if role.position >= bot_member.top_role.position:
        await ctx.send("🚫 Bot không có quyền gỡ role này.")
        return

    try:
        await member.remove_roles(role)
        await ctx.send(f"✅ Gỡ role '{ROLE_NAME}' cho {member.name}")
        c.execute("UPDATE inactivity SET role_added=0 WHERE member_id=?", (str(member.id),))
        conn.commit()
    except discord.Forbidden:
        await ctx.send("🚫 Bot không có quyền để gỡ role.")
    except Exception as e:
        await ctx.send(f"⚠️ Lỗi: {e}")

# ===== Event: bot ready =====
@bot.event
async def on_ready():
    print(f"🤖 Bot {bot.user} đã online!")
    await bot.change_presence(activity=discord.Game("Theo dõi tín đồ 😴"))
    check_inactivity.start()

# ===== Run bot =====
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Không tìm thấy TOKEN trong biến môi trường!")
