import discord
import asyncio
import os
import aiohttp
import random
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from discord import app_commands

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URLS = [
    # 🇫🇮 SUOMI
    "https://www.verkkokauppa.com/fi/product/980138/Pokemon-SV10-boosters-kerailykortit-36-pack",
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.prisma.fi/tuotteet/111239016/pokemon-tcg-me02-5-premium-poster-collection-erilaisia-111239016",
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box",
    "https://www.verkkokauppa.com/fi/product/1037336/Pokemon-First-Partner-Collection-Box-Series-1-kerailykorttis",
    "https://www.verkkokauppa.com/fi/product/1037318/Pokemon-ME02-5-Premium-Poster-Collection-Mega-Lucario-ex-Meg",
    "https://www.verkkokauppa.com/fi/product/1037309/Pokemon-ME02-5-Ascended-Heroes-Booster-Bundle-kerailykorttip",
    "https://www.verkkokauppa.com/fi/product/1031984/Pokemon-TCG-ME02-5-Ascended-Heroes-Elite-Trainer-Box-keraily",
    "https://www.verkkokauppa.com/fi/product/980099/Pokemon-TCG-Scarlet-Violet-Destined-Rivals-Elite-Trainer-Box",

    # 🌍 EU
    "https://eurotcg.com/be/product/pokemon-booster-bundle-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-booster-box-destined-rivals",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolutions-phantasmal-flames-pre-order",
    "https://www.playingcardshop.eu/pokemon-tcg-mega-evolution-ascended-heroes-booster-bundle-6-packs.html",
    "https://www.playingcardshop.eu/pokemon-tcg-scarlet-and-violet-destined-rivals-elite-trainer-box.html"
]

# ---------------- SPEED SETTINGS ----------------
BASE_MIN = 10
BASE_MAX = 25

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STATE ----------------
last_state = {}
notified = set()
last_check = "Ei vielä"
start_time = datetime.now()

session = None

# ---------------- STOCK CHECK ----------------
def check_availability(soup):
    text = soup.get_text(" ", strip=True).lower()

    # 🟥 OUT
    if any(x in text for x in [
        "ei saatavilla", "loppu varastosta", "out of stock",
        "sold out", "ei varastossa"
    ]):
        return "out"

    # 🟢 IN
    if any(x in text for x in [
        "ostoskoriin", "add to cart", "buy now",
        "pre-order", "varastossa", "in stock"
    ]):
        return "in"

    # 🧠 DOM fallback (button check)
    if soup.select_one("button"):
        btn_text = soup.select_one("button").get_text(strip=True).lower()
        if "cart" in btn_text or "buy" in btn_text:
            return "in"

    return "unknown"


def get_title(soup):
    return soup.title.text.strip() if soup.title else "Tuote"

# ---------------- FETCH (FAST + RETRY) ----------------
async def fetch(url):
    for _ in range(2):  # retry kevyt
        try:
            await asyncio.sleep(random.uniform(0.2, 0.6))

            async with session.get(url, timeout=12) as resp:
                if resp.status != 200:
                    continue

                html = await resp.text()
                return url, BeautifulSoup(html, "html.parser")

        except:
            continue

    return url, None

# ---------------- TELEGRAM ----------------
async def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        })
    except:
        pass

# ---------------- LOOP (ULTRA FAST STREAM MODE) ----------------
async def check_loop():
    await client.wait_until_ready()

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        log.error("Channel not found")
        return

    global last_check

    while True:
        try:
            last_check = datetime.now().strftime("%H:%M:%S")

            tasks = [fetch(url) for url in URLS]

            for coro in asyncio.as_completed(tasks):
                url, soup = await coro

                if not soup:
                    continue

                status = check_availability(soup)
                title = get_title(soup)

                log.info(f"{status} -> {url}")

                if url not in last_state:
                    last_state[url] = status
                    continue

                # 🔥 ONLY NEW RESTOCK
                if status == "in" and last_state[url] != "in":

                    if url in notified:
                        continue

                    notified.add(url)

                    embed = discord.Embed(
                        title="🔥 RESTOCK ALERT",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )

                    await channel.send(embed=embed)
                    await send_telegram(f"🔥 RESTOCK\n\n{title}\n\n{url}")

                last_state[url] = status

        except Exception as e:
            log.error(f"Loop error: {e}")

        await asyncio.sleep(random.randint(BASE_MIN, BASE_MAX))

# ---------------- COMMANDS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    uptime = datetime.now() - start_time

    embed = discord.Embed(title="Bot Status", color=0x00ff00)
    embed.add_field(name="URLs", value=len(URLS))
    embed.add_field(name="Last Check", value=last_check)
    embed.add_field(name="Uptime", value=str(uptime).split('.')[0])

    await interaction.response.send_message(embed=embed)

# ---------------- READY ----------------
@client.event
async def on_ready():
    global session

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (StockBot Ultra)",
            "Accept-Language": "fi,en;q=0.8"
        }
    )

    await tree.sync()

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("🚀 ULTRA FAST BOT ONLINE")

    client.loop.create_task(check_loop())

client.run(TOKEN)
