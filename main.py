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
    # 🇪🇺 ENGLANTI / EUROOPPA
    "https://eurotcg.com/be/product/pokemon-booster-bundle-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-booster-box-destined-rivals",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolutions-phantasmal-flames-pre-order",
    "https://www.playingcardshop.eu/pokemon-tcg-mega-evolution-ascended-heroes-booster-bundle-6-packs.html",
    "https://www.playingcardshop.eu/pokemon-tcg-scarlet-and-violet-destined-rivals-elite-trainer-box.html"
]

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STATE ----------------
last_state = {}
start_time = datetime.now()
session = None

# ---------------- STOCK DETECTION ----------------
def check_availability(text: str):
    text = text.lower()

    out_signals = [
        "ei saatavilla",
        "loppu varastosta",
        "out of stock",
        "sold out",
        "tilapäisesti loppu",
        "ei varastossa"
    ]
    in_signals = [
        "ostoskoriin",
        "add to cart",
        "buy now",
        "pre-order",
        "varastossa",
        "in stock"
    ]

    for s in out_signals:
        if s in text:
            return "out"
    for s in in_signals:
        if s in text:
            return "in"
    return "unknown"

def get_title(soup):
    return soup.title.text.strip() if soup and soup.title else "Tuote"

# ---------------- FETCH ----------------
async def fetch(url):
    try:
        async with session.get(url, timeout=12) as resp:
            if resp.status != 200:
                return url, None
            html = await resp.text()
            return url, html
    except Exception:
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

# ---------------- SINGLE URL MONITOR ----------------
async def monitor_url(url):
    global last_state
    while True:
        _, html = await fetch(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            status = check_availability(text)
            title = get_title(soup)

            log.info(f"{url} -> {status}")

            if url not in last_state:
                last_state[url] = status
            elif status == "in" and last_state[url] != "in":
                # SEND ALERT
                channel = client.get_channel(CHANNEL_ID)
                if channel:
                    embed = discord.Embed(
                        title="🔥 RESTOCK DETECTED",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )
                    await channel.send(embed=embed)
                await send_telegram(f"🔥 RESTOCK\n\n{title}\n\n{url}")

                last_state[url] = status
            else:
                last_state[url] = status

        # SMALL RANDOM DELAY FOR SAFETY
        await asyncio.sleep(random.uniform(3, 7))  # 3–7 sekuntia per URL

# ---------------- READY ----------------
@client.event
async def on_ready():
    global session
    log.info(f"Logged in as {client.user}")

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (StockBot)",
            "Accept-Language": "fi,en;q=0.8"
        }
    )

    await tree.sync()
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ ULTRA BOT ONLINE")

    # START MONITORING EACH URL IN ITS OWN TASK
    for url in URLS:
        client.loop.create_task(monitor_url(url))

# ---------------- COMMANDS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    uptime = datetime.now() - start_time
    embed = discord.Embed(title="Bot Status", color=0x00ff00)
    embed.add_field(name="URLs", value=len(URLS))
    embed.add_field(name="Latency", value=f"{round(client.latency*1000)}ms")
    embed.add_field(name="Uptime", value=str(uptime).split('.')[0])
    await interaction.response.send_message(embed=embed)

@tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong {round(client.latency*1000)}ms")

client.run(TOKEN)
