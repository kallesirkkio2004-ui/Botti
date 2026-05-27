import discord
import asyncio
import os
import aiohttp
import random
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from discord import app_commands
from urllib.parse import urlparse

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

    # 🇪🇺 EUROOPPA
    "https://eurotcg.com/be/product/pokemon-booster-bundle-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-booster-box-destined-rivals",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolutions-phantasmal-flames-pre-order",
    "https://www.playingcardshop.eu/pokemon-tcg-mega-evolution-ascended-heroes-booster-bundle-6-packs.html",
    "https://www.playingcardshop.eu/pokemon-tcg-scarlet-and-violet-destined-rivals-elite-trainer-box.html"
]

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STATE ----------------
last_state = {}
session = None
start_time = datetime.now()

# ---------------- STOCK LOGIC ----------------
OUT_SIGNALS = [
    "ei saatavilla", "loppu varastosta", "out of stock",
    "sold out", "tilapäisesti loppu", "ei varastossa"
]

IN_SIGNALS = [
    "ostoskoriin", "add to cart", "buy now",
    "pre-order", "varastossa", "in stock"
]

def check_availability(text: str):
    text = text.lower()

    found_in = any(s in text for s in IN_SIGNALS)
    found_out = any(s in text for s in OUT_SIGNALS)

    # IMPORTANT: IN overrides OUT
    if found_in:
        return "in"
    if found_out:
        return "out"
    return "unknown"

def get_title(soup):
    return soup.title.text.strip() if soup.title else "Product"

# ---------------- FETCH ----------------
async def fetch(url):
    try:
        async with session.get(url, timeout=20) as resp:
            if resp.status != 200:
                return None

            html = await resp.text()

            lowered = html.lower()

            if "captcha" in lowered or "access denied" in lowered:
                log.warning(f"Blocked: {url}")
                return None

            return html

    except Exception as e:
        log.error(f"Fetch error {url}: {e}")
        return None

# ---------------- ALERT ----------------
async def send_alert(title, url):
    channel = client.get_channel(CHANNEL_ID)

    if channel:
        embed = discord.Embed(
            title="🔥 RESTOCK DETECTED",
            url=url,
            description=f"[{title}]({url})",
            color=0x00ff00
        )
        embed.add_field(name="Link", value=url, inline=False)

        await channel.send(content="@everyone", embed=embed)

# Telegram optional
async def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass

# ---------------- MONITOR ----------------
async def monitor_url(url):
    global last_state

    while True:
        html = await fetch(url)

        if html:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            title = get_title(soup)
            status = check_availability(text)

            prev = last_state.get(url)

            log.info(f"{url} -> {status}")

            # FIRST RUN
            if prev is None:
                last_state[url] = status
                if status == "in":
                    await send_alert(title, url)

            # STATE CHANGE
            elif prev != status:
                last_state[url] = status

                if status == "in":
                    await send_alert(title, url)

        await asyncio.sleep(random.uniform(25, 50))

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
        await channel.send("✅ BOT ONLINE")

    for url in URLS:
        asyncio.create_task(monitor_url(url))

# ---------------- COMMANDS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    uptime = datetime.now() - start_time
    await interaction.response.send_message(
        f"URLs: {len(URLS)}\nUptime: {str(uptime).split('.')[0]}"
    )

@tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong {round(client.latency*1000)}ms")

# ---------------- RUN ----------------
client.run(TOKEN)
