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
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ROLE_ID = None

URLS = [
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.prisma.fi/tuotteet/111239016/pokemon-tcg-me02-5-premium-poster-collection-erilaisia-111239016",
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box",
    "https://www.verkkokauppa.com/fi/product/1037336/Pokemon-First-Partner-Collection-Box-Series-1-kerailykorttis",
    "https://www.verkkokauppa.com/fi/product/1037318/Pokemon-ME02-5-Premium-Poster-Collection-Mega-Lucario-ex-Meg",
    "https://www.verkkokauppa.com/fi/product/1037309/Pokemon-ME02-5-Ascended-Heroes-Booster-Bundle-kerailykorttip",
    "https://www.verkkokauppa.com/fi/product/1031984/Pokemon-TCG-ME02-5-Ascended-Heroes-Elite-Trainer-Box-keraily",
    "https://www.verkkokauppa.com/fi/product/980138/Pokemon-SV10-boosters-kerailykortit-36-pack",
    "https://www.verkkokauppa.com/fi/product/980099/Pokemon-TCG-Scarlet-Violet-Destined-Rivals-Elite-Trainer-Box"
]

CHECK_INTERVAL = 60

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("restock-bot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ---------------- STATE ----------------
last_state = {}
history = defaultdict(list)

# ---------------- HTTP SESSION ----------------
session = None


# ---------------- HELPERS ----------------
def get_title(soup):
    return soup.title.text.strip() if soup.title else "Tuote"


def is_false_positive(url, status_history):
    # 3 peräkkäistä "in" tai "out" tekee päätöksen luotettavammaksi
    if len(status_history) < 3:
        return False
    return len(set(status_history[-3:])) == 1


def check_availability(url, soup):
    text = soup.get_text(" ", strip=True).lower()

    # Prisma
    if "prisma.fi" in url:
        if "ei saatavilla" in text or "loppu varastosta" in text:
            return "out"
        if "lisää ostoskoriin" in text or "tilattavissa" in text:
            return "in"

    # Kärkkäinen
    if "karkkainen.com" in url:
        if "loppu varastosta" in text:
            return "out"
        if "ostoskoriin" in text or "tilattavissa" in text:
            return "in"

    # Verkkokauppa
    if "verkkokauppa.com" in url:
        if "ei saatavilla" in text or "loppu varastosta" in text:
            return "out"

        for b in soup.find_all("button"):
            t = b.get_text().lower()
            if "ostoskoriin" in t:
                return "in"

    return "unknown"


# ---------------- NETWORK ----------------
async def fetch(url):
    global session

    try:
        async with session.get(url, timeout=15) as resp:
            html = await resp.text()
            return url, BeautifulSoup(html, "html.parser")
    except Exception as e:
        log.warning(f"Fetch error {url}: {e}")
        return url, None


# ---------------- TELEGRAM ----------------
async def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        async with session.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }) as _:
            pass

    except Exception as e:
        log.warning(f"Telegram error: {e}")


# ---------------- CORE LOOP ----------------
async def check_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    global last_state

    while True:
        try:
            # ⚡ Rinnakkainen haku
            results = await asyncio.gather(*[fetch(url) for url in URLS])

            for url, soup in results:
                if soup is None:
                    continue

                status = check_availability(url, soup)
                title = get_title(soup)

                log.info(f"{url} -> {status}")

                # init
                if url not in last_state:
                    last_state[url] = status
                    continue

                history[url].append(status)
                if len(history[url]) > 5:
                    history[url].pop(0)

                # 🔒 estä väärät triggerit
                if not is_false_positive(url, history[url]):
                    continue

                # 🔥 vain transition
                if status == "in" and last_state[url] != "in":

                    embed = discord.Embed(
                        title="🔥 TUOTE SAATAVILLA!",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )

                    embed.add_field(name="Status", value="IN STOCK", inline=False)

                    msg = f"<@&{ROLE_ID}>" if ROLE_ID else ""

                    await channel.send(content=msg, embed=embed)

                    await send_telegram(
                        f"🔥 <b>TUOTE SAATAVILLA</b>\n\n<b>{title}</b>\n\n{url}"
                    )

                last_state[url] = status

        except Exception as e:
            log.error(f"Loop error: {e}")

        # 🧠 jitter = näyttää ihmismäiseltä & vähentää kuormaa
        sleep_time = CHECK_INTERVAL + random.randint(-10, 15)
        await asyncio.sleep(max(30, sleep_time))


# ---------------- DISCORD READY ----------------
@client.event
async def on_ready():
    global session

    log.info(f"Logged in as {client.user}")

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; StockChecker/1.0)",
            "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"
        }
    )

    channel = client.get_channel(CHANNEL_ID)

    await channel.send("✅ Restock-botti käynnissä!")
    await send_telegram("✅ Bot online")

    client.loop.create_task(check_loop())


@client.event
async def on_close():
    if session:
        await session.close()


client.run(TOKEN)
