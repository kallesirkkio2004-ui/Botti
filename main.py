import os
import asyncio
import random
import logging
from datetime import datetime

import discord
from discord import app_commands
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

CHECK_MIN = 20
CHECK_MAX = 45

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

# ================= LOGGING =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("bot")

# ================= DISCORD =================

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ================= STATE =================

last_state = {}
playwright = None
browser = None

# ================= STOCK DETECTION =================

def detect_stock(url: str, html: str, text: str) -> str:
    html = html.lower()
    text = text.lower()

    # ---- PRISMA ----
    if "prisma.fi" in url:
        if "ostoskoriin" in html:
            return "in"
        if "ei saatavilla" in html or "loppu varastosta" in html:
            return "out"
        return "unknown"

    # ---- VERKKOKAUPPA / K-RAUTA / GENERIC ----
    in_signals = ["add to cart", "ostoskoriin", "buy now", "in stock", "varastossa"]
    out_signals = ["ei saatavilla", "out of stock", "sold out", "loppu varastosta"]

    if any(x in text for x in in_signals):
        return "in"
    if any(x in text for x in out_signals):
        return "out"

    return "unknown"

# ================= FETCH =================

async def fetch(url: str):
    try:
        page = await browser.new_page()

        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        html = await page.content()

        await page.close()

        return html

    except Exception as e:
        log.error(f"FETCH ERROR {url} | {e}")
        return None

# ================= ALERT =================

async def send_alert(url: str):
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    await channel.send(
        f"🔥 **RESTOCK DETECTED**\n{url}\n@everyone"
    )

# ================= MONITOR =================

async def monitor(url: str):
    global last_state

    while True:
        html = await fetch(url)

        if html:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)

            status = detect_stock(url, html, text)
            prev = last_state.get(url)

            log.info(f"{status.upper():8} | {url}")

            # FIRST RUN (no alert)
            if prev is None:
                last_state[url] = status
                continue

            # STATE CHANGE
            if prev != status:
                log.warning(f"CHANGE {prev} -> {status}")
                last_state[url] = status

                if status == "in":
                    await send_alert(url)

        await asyncio.sleep(random.randint(CHECK_MIN, CHECK_MAX))

# ================= READY =================

@client.event
async def on_ready():
    global playwright, browser

    log.info(f"Logged in as {client.user}")

    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox"]
    )

    for url in URLS:
        asyncio.create_task(monitor(url))

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ STOCK BOT ONLINE")

# ================= COMMANDS =================

@tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong")

# ================= RUN =================

client.run(TOKEN)