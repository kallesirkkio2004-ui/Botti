import discord
import asyncio
import os
import aiohttp
import random
import logging
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime
from discord import app_commands

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------------- URLS (RYHMITELTY NOPEUDEN MUKAAN) ----------------
URL_GROUPS = {
    "fast": [
        "https://www.verkkokauppa.com/fi/product/980138/...",
    ],
    "medium": [
        "https://www.prisma.fi/tuotteet/111268553/...",
        "https://www.karkkainen.com/verkkokauppa/...",
    ],
    "slow": [
        "https://eurotcg.com/be/product/pokemon-booster-bundle-mega-evolution-ascended-heroes-pre-order",
        "https://www.playingcardshop.eu/...",
    ]
}

INTERVALS = {
    "fast": (18, 28),
    "medium": (28, 45),
    "slow": (40, 70),
}

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STATE ----------------
last_state = {}
last_seen_change = {}
START_TIME = datetime.now()
LAST_CHECK = "Ei vielä"

session = None


# ---------------- HELPERS ----------------
def get_title(soup):
    return soup.title.text.strip() if soup.title else "Tuote"


def check_availability(soup):
    text = soup.get_text(" ", strip=True).lower()

    # parempi detection
    if "loppu" in text or "out of stock" in text or "sold out" in text:
        return "out"

    if "ostoskoriin" in text or "add to cart" in text or "pre-order" in text:
        return "in"

    return "unknown"


# ---------------- FETCH ----------------
async def fetch(url):
    try:
        await asyncio.sleep(random.uniform(0.3, 1.0))

        async with session.get(url, timeout=15) as resp:
            html = await resp.text()
            return url, BeautifulSoup(html, "html.parser")

    except Exception as e:
        log.warning(f"Fetch error {url}: {e}")
        return url, None


# ---------------- TELEGRAM ----------------
async def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        async with session.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }) as resp:
            log.info(await resp.text())

    except Exception as e:
        log.error(f"Telegram error: {e}")


# ---------------- CORE CHECK ----------------
async def check_url(url):
    _, soup = await fetch(url)
    if not soup:
        return

    status = check_availability(soup)
    title = get_title(soup)

    old = last_state.get(url)

    # ensimmäinen init
    if old is None:
        last_state[url] = status
        return

    # 🔥 MUUTOS DETECTION
    if status != old:

        # instant recheck (varmistus ilman viivettä)
        _, soup2 = await fetch(url)
        if soup2:
            status2 = check_availability(soup2)
        else:
            status2 = status

        # hyväksy vain jos sama muutos
        if status == status2:

            if status == "in":

                channel = client.get_channel(CHANNEL_ID)

                embed = discord.Embed(
                    title="🔥 RESTOCK!",
                    description=f"[{title}]({url})",
                    color=0x00ff00
                )

                await channel.send(embed=embed)
                await send_telegram(f"🔥 <b>RESTOCK</b>\n\n<b>{title}</b>\n{url}")

            last_state[url] = status
            last_seen_change[url] = datetime.now()


# ---------------- LOOP ----------------
async def worker(group_name, urls):
    while True:

        global LAST_CHECK
        LAST_CHECK = datetime.now().strftime("%H:%M:%S")

        tasks = [check_url(url) for url in urls]
        await asyncio.gather(*tasks)

        await asyncio.sleep(random.randint(*INTERVALS[group_name]))


# ---------------- READY ----------------
@client.event
async def on_ready():
    global session

    log.info(f"Logged in as {client.user}")

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "fi-FI,fi;q=0.9"
        }
    )

    await tree.sync()

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ FAST RESTOCK BOT v2 käynnissä")

    await send_telegram("✅ Bot online v2")

    # 🔥 start workers per speed group
    for group, urls in URL_GROUPS.items():
        client.loop.create_task(worker(group, urls))


client.run(TOKEN)
