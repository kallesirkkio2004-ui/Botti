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
]

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("stockbot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STATE ----------------
last_state = {}
session = None
start_time = datetime.now()

# ---------------- DETECTION ----------------
OUT_SIGNALS = [
    "ei saatavilla",
    "loppu varastosta",
    "out of stock",
    "sold out",
    "tilapäisesti loppu",
    "ei varastossa",
]

IN_SIGNALS = [
    "ostoskoriin",
    "lisää ostoskoriin",
    "add to cart",
    "buy now",
    "pre-order",
    "varastossa",
    "in stock",
]

def check_availability(text: str):
    text = text.lower()

    found_in = any(s in text for s in IN_SIGNALS)
    found_out = any(s in text for s in OUT_SIGNALS)

    # PRIORISOI ALWAYS IN-STOCK
    if found_in:
        return "in"

    if found_out:
        return "out"

    return "unknown"

def get_title(soup):
    if soup.title:
        return soup.title.text.strip()

    h1 = soup.find("h1")
    if h1:
        return h1.text.strip()

    return "Pokemon Product"

# ---------------- FETCH ----------------
async def fetch(url):
    try:
        async with session.get(url, timeout=20) as resp:

            if resp.status != 200:
                log.warning(f"{url} -> HTTP {resp.status}")
                return None

            html = await resp.text()

            if not html:
                return None

            # BOT/CAPTCHA DETECTION
            lowered = html.lower()

            if "captcha" in lowered:
                log.warning(f"CAPTCHA DETECTED: {url}")
                return None

            if "access denied" in lowered:
                log.warning(f"ACCESS DENIED: {url}")
                return None

            return html

    except Exception as e:
        log.error(f"FETCH ERROR {url}: {e}")
        return None

# ---------------- TELEGRAM ----------------
async def send_telegram(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        telegram_url = (
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        )

        async with session.post(
            telegram_url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            }
        ):
            pass

    except Exception as e:
        log.error(f"Telegram error: {e}")

# ---------------- ALERT ----------------
async def send_alert(title, url):

    # DISCORD
    channel = client.get_channel(CHANNEL_ID)

    if channel:
        embed = discord.Embed(
            title="🔥 PRODUCT IN STOCK",
            description=f"[{title}]({url})",
            color=0x00ff00
        )

        embed.add_field(name="Link", value=url, inline=False)

        embed.set_footer(text="Pokemon Stock Bot")

        await channel.send(
            content="@everyone",
            embed=embed
        )

    # TELEGRAM
    await send_telegram(
        f"🔥 PRODUCT IN STOCK\n\n{title}\n{url}"
    )

# ---------------- MONITOR ----------------
async def monitor_url(url):

    global last_state

    domain = urlparse(url).netloc

    while True:

        html = await fetch(url)

        if html:

            soup = BeautifulSoup(html, "html.parser")

            text = soup.get_text(" ", strip=True)

            title = get_title(soup)

            status = check_availability(text)

            previous = last_state.get(url)

            log.info(
                f"{domain} | {status.upper()} | {title[:60]}"
            )

            # DEBUG PRISMA
            if "prisma.fi" in url:
                log.info(f"PRISMA DEBUG: {text[:500]}")

            # ENSIMMÄINEN CHECK
            if previous is None:

                last_state[url] = status

                # Jos botti käynnistyy ja tuote on heti IN STOCK
                if status == "in":
                    log.info(f"INITIAL STOCK FOUND: {title}")

                    await send_alert(title, url)

            # STATUS CHANGED
            elif previous != status:

                log.info(
                    f"STATUS CHANGE: {previous} -> {status} | {title}"
                )

                # ONLY ALERT WHEN GOING INTO STOCK
                if status == "in":
                    await send_alert(title, url)

                last_state[url] = status

        # DOMAIN-BASED SAFE DELAYS
        if "prisma.fi" in url:
            await asyncio.sleep(random.uniform(30, 60))

        elif "verkkokauppa.com" in url:
            await asyncio.sleep(random.uniform(20, 40))

        else:
            await asyncio.sleep(random.uniform(25, 45))

# ---------------- READY ----------------
@client.event
async def on_ready():

    global session

    log.info(f"Logged in as {client.user}")

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )

    await tree.sync()

    channel = client.get_channel(CHANNEL_ID)

    if channel:
        await channel.send("✅ STOCK BOT ONLINE")

    # START TASKS
    for url in URLS:
        asyncio.create_task(monitor_url(url))

# ---------------- COMMANDS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):

    uptime = datetime.now() - start_time

    embed = discord.Embed(
        title="Bot Status",
        color=0x00ff00
    )

    embed.add_field(
        name="Monitoring URLs",
        value=str(len(URLS)),
        inline=True
    )

    embed.add_field(
        name="Latency",
        value=f"{round(client.latency * 1000)}ms",
        inline=True
    )

    embed.add_field(
        name="Uptime",
        value=str(uptime).split(".")[0],
        inline=False
    )

    await interaction.response.send_message(embed=embed)

@tree.command(name="ping")
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Pong {round(client.latency * 1000)}ms"
    )

# ---------------- SHUTDOWN ----------------
async def close_session():

    global session

    if session:
        await session.close()

# ---------------- RUN ----------------
try:
    client.run(TOKEN)

except KeyboardInterrupt:
    asyncio.run(close_session())
