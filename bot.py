import discord
from discord.ext import commands
import mysql.connector
import os

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("TOKEN")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
GUILD_ID = int(os.getenv("GUILD_ID"))
ORDER_CHANNEL_ID = int(os.getenv("ORDER_CHANNEL_ID"))
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID"))
RATING_CHANNEL_ID = int(os.getenv("RATING_CHANNEL_ID"))
ORDER_CATEGORY_ID = int(os.getenv("ORDER_CATEGORY_ID"))
BUYER_ROLE_ID = int(os.getenv("BUYER_ROLE_ID"))

pending_ratings = {}

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command()
async def order(ctx, *, input: str = None):
    if ctx.channel.id != ORDER_CHANNEL_ID:
        return

    if not input or input.count("|") != 3:
        await ctx.send(embed=discord.Embed(
            description="❌ Format salah. Gunakan: `!order <Nama Server> | <Paket> | <Durasi> | <Subdomain>`",
            color=discord.Color.red()))
        return

    server_name, package, duration, subdomain = map(str.strip, input.split("|"))

    guild = bot.get_guild(GUILD_ID)
    category = discord.utils.get(guild.categories, id=ORDER_CATEGORY_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    order_channel = await guild.create_text_channel(f'order-{ctx.author.name}', category=category, overwrites=overwrites)

    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (user_id, server_name, package, duration, subdomain, order_channel_id) VALUES (%s, %s, %s, %s, %s, %s)",
                   (ctx.author.id, server_name, package, duration, subdomain, order_channel.id))
    db.commit()
    cursor.close()
    db.close()

    embed = discord.Embed(title="🧾 Order Baru", color=discord.Color.blue())
    embed.add_field(name="Nama Server", value=server_name, inline=False)
    embed.add_field(name="Paket", value=package, inline=True)
    embed.add_field(name="Durasi", value=duration, inline=True)
    embed.add_field(name="Subdomain", value=subdomain, inline=False)
    embed.set_footer(text=f"Dibuat oleh {ctx.author}")

    await order_channel.send(f"{ctx.author.mention}", embed=embed)
    await ctx.send(embed=discord.Embed(description=f"✅ Order kamu telah dibuat di {order_channel.mention}", color=discord.Color.green()))

    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
    await admin_channel.send(f"🆕 Order dari {ctx.author.mention} telah masuk di {order_channel.mention}")

@bot.command()
async def process(ctx, *, input: str):
    try:
        order_id, userpanel, paket, durasi, subdomain = map(str.strip, input.split("|"))
    except ValueError:
        await ctx.send("❌ Format salah. Gunakan: !process <order_id> | <userpanel:pwpanel> | <paket> | <durasi> | <subdomain>")
        return

    user_panel, password_panel = userpanel.split(":")

    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE orders SET user_panel = %s, password_panel = %s, status = 'Processed' WHERE order_id = %s",
                   (user_panel, password_panel, order_id))
    db.commit()

    cursor.execute("SELECT order_channel_id, user_id FROM orders WHERE order_id = %s", (order_id,))
    result = cursor.fetchone()
    cursor.close()
    db.close()

    if not result:
        await ctx.send("❌ Order ID tidak ditemukan.")
        return

    channel_id, user_id = result
    channel = bot.get_channel(channel_id)

    embed = discord.Embed(title="✅ Pesanan Diproses", color=discord.Color.green())
    embed.add_field(name="User Panel", value=user_panel, inline=True)
    embed.add_field(name="Password Panel", value=password_panel, inline=True)
    embed.add_field(name="Paket", value=paket, inline=True)
    embed.add_field(name="Durasi", value=durasi, inline=True)
    embed.add_field(name="Subdomain", value=subdomain, inline=True)
    embed.set_footer(text="Terima kasih telah memesan di TidupatHost")

    await channel.send(f"<@{user_id}>", embed=embed)

@bot.command()
async def done(ctx):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT order_id, user_id FROM orders WHERE order_channel_id = %s", (ctx.channel.id,))
    result = cursor.fetchone()

    if not result:
        await ctx.send("❌ Order tidak ditemukan.")
        return

    order_id, user_id = result

    cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = %s", (order_id,))
    db.commit()
    cursor.close()
    db.close()

    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(user_id)
    role = guild.get_role(BUYER_ROLE_ID)
    await member.add_roles(role)

    await ctx.send("✅ Order selesai. Silakan beri rating dengan `!rate <1-5> <pesan>`")

    # Simpan channel agar dihapus setelah rating
    pending_ratings[user_id] = ctx.channel.id

@bot.command()
async def rate(ctx, rating: int, *, message: str):
    if rating < 1 or rating > 5:
        await ctx.send("❌ Rating harus antara 1 dan 5.")
        return

    channel = bot.get_channel(RATING_CHANNEL_ID)
    await channel.send(f"{ctx.author.mention} > ⭐️{rating} | {message}")
    await ctx.send("✅ Terima kasih atas ratingnya!")

    if ctx.author.id in pending_ratings:
        channel_id = pending_ratings.pop(ctx.author.id)
        channel = bot.get_channel(channel_id)
        await channel.delete()

bot.run(TOKEN)
