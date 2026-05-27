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

TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

# ---------------- URLS ----------------
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
session: aiohttp.ClientSession = None
start_time = datetime.now()

# ---------------- STOCK LOGIC ----------------
OUT = ["ei saatavilla", "loppu varastosta", "out of stock", "sold out", "ei varastossa"]
IN = ["ostoskoriin", "add to cart", "buy now", "pre-order", "varastossa", "in stock"]

def check(text):
    text = text.lower()
    if any(x in text for x in IN):
        return "in"
    if any(x in text for x in OUT):
        return "out"
    return "unknown"

def title(soup):
    return soup.title.text.strip() if soup.title else "Product"

# ---------------- FETCH ----------------
async def fetch(url):
    try:
        async with session.get(url, timeout=20) as r:
            if r.status != 200:
                return None
            html = await r.text()
            if "captcha" in html.lower() or "access denied" in html.lower():
                log.warning(f"BLOCKED: {url}")
                return None
            return html
    except Exception as e:
        log.error(f"Fetch error {url}: {e}")
        return None

# ---------------- TELEGRAM ----------------
async def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        log.error(f"Telegram error: {e}")

# ---------------- ALERT ----------------
async def alert(title_str, url):
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🔥 TUOTE SAATAVILLA!",
            url=url,
            description=f"[{title_str}]({url})",
            color=0x00ff00
        )
        await channel.send(content="@everyone", embed=embed)
    await send_telegram(f"🔥 <b>{title_str}</b>\n🛒 {url}")

# ---------------- MONITOR ----------------
async def monitor(url):
    global last_state
    while True:
        html = await fetch(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            state = check(text)
            prev = last_state.get(url)
            log.info(f"{url} -> {state}")

            if prev is None:
                last_state[url] = state
            elif prev != state:
                last_state[url] = state
                if state == "in":
                    await alert(title(soup), url)
        await asyncio.sleep(random.uniform(30, 60))

# ---------------- READY ----------------
@client.event
async def on_ready():
    global session
    log.info(f"Logged in as {client.user}")
    session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fi,en;q=0.8"})

    if TEST_GUILD_ID:
        await tree.sync(guild=discord.Object(id=TEST_GUILD_ID))

    for url in URLS:
        asyncio.create_task(monitor(url))

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ BOT ONLINE")

# ---------------- COMMANDS ----------------
@tree.command(name="status", description="Näytä botin tila")
async def status(interaction: discord.Interaction):
    uptime = datetime.now() - start_time
    await interaction.response.send_message(f"URLs: {len(URLS)}\nUptime: {str(uptime).split('.')[0]}")

@tree.command(name="ping", description="Testaa botti")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong {round(client.latency*1000)}ms")

@tree.command(name="test_telegram", description="Lähetä testiviesti Telegramiin")
async def test_telegram(interaction: discord.Interaction):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        await interaction.response.send_message("Telegram token tai chat_id puuttuu!", ephemeral=True)
        return
    try:
        msg = "✅ Tämä on testiviesti Telegramista!"
        await send_telegram(msg)
        await interaction.response.send_message("Testiviesti lähetetty Telegramiin!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Virhe viestin lähetyksessä: {e}", ephemeral=True)

# ---------------- RUN ----------------
client.run(TOKEN)
