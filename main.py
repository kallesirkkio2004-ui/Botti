import discord
import asyncio
import os
import aiohttp
import random
import logging
from bs4 import BeautifulSoup
from collections import defaultdict

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")

CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID) if CHANNEL_ID else None

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URLS = [
    "https://www.verkkokauppa.com/fi/product/980138/Pokemon-SV10-boosters-kerailykortit-36-pack",
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
]

CHECK_INTERVAL = 60

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ---------------- DISCORD ----------------
client = discord.Client(intents=discord.Intents.default())

# ---------------- STATE ----------------
last_state = {}
history = defaultdict(list)

session = None


# ---------------- HELPERS ----------------
def get_title(soup):
    return soup.title.text.strip() if soup.title else "Tuote"


def check_availability(url, soup):
    text = soup.get_text(" ", strip=True).lower()

    if "ei saatavilla" in text or "loppu varastosta" in text:
        return "out"

    if "ostoskoriin" in text or "lisää ostoskoriin" in text:
        return "in"

    return "unknown"


# ---------------- FETCH ----------------
async def fetch(url):
    try:
        async with session.get(url, timeout=15) as resp:
            html = await resp.text()
            return url, BeautifulSoup(html, "html.parser")
    except Exception as e:
        log.warning(f"Fetch error {url}: {e}")
        return url, None


# ---------------- TELEGRAM ----------------
async def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Telegram env missing")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        async with session.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }) as resp:

            result = await resp.text()
            log.info(f"Telegram response: {result}")

    except Exception as e:
        log.error(f"Telegram error: {e}")


# ---------------- LOOP ----------------
async def check_loop():
    await client.wait_until_ready()

    if not CHANNEL_ID:
        log.error("CHANNEL_ID missing")
        return

    channel = client.get_channel(CHANNEL_ID)

    while True:
        try:
            results = await asyncio.gather(*[fetch(url) for url in URLS])

            for url, soup in results:
                if not soup:
                    continue

                status = check_availability(url, soup)
                title = get_title(soup)

                log.info(f"{url} -> {status}")

                if url not in last_state:
                    last_state[url] = status
                    continue

                # history tracking
                history[url].append(status)
                if len(history[url]) > 5:
                    history[url].pop(0)

                # alert only real transition
                if status == "in" and last_state[url] != "in":

                    embed = discord.Embed(
                        title="🔥 TUOTE SAATAVILLA!",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )

                    await channel.send(embed=embed)

                    await send_telegram(
                        f"🔥 <b>RESTOCK!</b>\n\n<b>{title}</b>\n\n{url}"
                    )

                last_state[url] = status

        except Exception as e:
            log.error(f"Loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL + random.randint(-10, 15))


# ---------------- START ----------------
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

    channel = client.get_channel(CHANNEL_ID)

    await channel.send("✅ Bot käynnissä")
    await send_telegram("✅ Bot online (Telegram toimii)")

    client.loop.create_task(check_loop())


client.run(TOKEN)
