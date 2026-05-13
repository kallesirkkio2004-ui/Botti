import discord
import asyncio
import os
import aiohttp
import random
import logging
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

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
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ---------------- STATE ----------------
last_state = {}
history = defaultdict(list)
start_time = datetime.now()
last_check_time = "Ei vielä"

# ---------------- HTTP SESSION ----------------
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


def is_stable(url):
    h = history[url]
    if len(h) < 3:
        return False
    return h[-1] == h[-2] == h[-3]


# ---------------- FETCH ----------------
async def fetch(url):
    try:
        await asyncio.sleep(random.uniform(0.3, 1.2))  # anti-burst
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
            log.info(f"Telegram: {await resp.text()}")

    except Exception as e:
        log.error(f"Telegram error: {e}")


# ---------------- LOOP ----------------
async def check_loop():
    await client.wait_until_ready()

    if CHANNEL_ID == 0:
        log.error("CHANNEL_ID puuttuu")
        return

    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        log.error("Discord channel not found")
        return

    global last_check_time

    while True:
        try:
            last_check_time = datetime.now().strftime("%H:%M:%S")

            results = await asyncio.gather(*[fetch(url) for url in URLS])

            for url, soup in results:
                if not soup:
                    continue

                status = check_availability(url, soup)
                title = get_title(soup)

                log.info(f"{url} -> {status}")

                # init state
                if url not in last_state:
                    last_state[url] = status
                    history[url].append(status)
                    continue

                history[url].append(status)
                if len(history[url]) > 5:
                    history[url].pop(0)

                # ignore unstable results
                if not is_stable(url):
                    continue

                # alert only real change
                if status == "in" and last_state[url] != "in":

                    embed = discord.Embed(
                        title="🔥 TUOTE SAATAVILLA!",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )

                    embed.add_field(name="Status", value="IN STOCK", inline=False)

                    await channel.send(embed=embed)

                    await send_telegram(
                        f"🔥 <b>RESTOCK!</b>\n\n<b>{title}</b>\n\n{url}"
                    )

                last_state[url] = status

        except Exception as e:
            log.error(f"Loop error: {e}")

        sleep_time = CHECK_INTERVAL + random.randint(-10, 20)
        await asyncio.sleep(max(30, sleep_time))


# ---------------- START ----------------
@client.event
async def on_ready():
    global session

    log.info(f"Logged in as {client.user}")

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (StockBot/1.0)",
            "Accept-Language": "fi-FI,fi;q=0.9"
        }
    )

    channel = client.get_channel(CHANNEL_ID)

    if channel:
        await channel.send("✅ Bot käynnissä")
    await send_telegram("✅ Bot online")

    client.loop.create_task(check_loop())


# ---------------- CLEANUP ----------------
@client.event
async def on_disconnect():
    log.warning("Bot disconnected")

    if session:
        await session.close()


client.run(TOKEN)
