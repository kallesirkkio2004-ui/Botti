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

URLS = [
    "https://www.verkkokauppa.com/fi/product/980138/Pokemon-SV10-boosters-kerailykortit-36-pack",
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.prisma.fi/tuotteet/111239016/pokemon-tcg-me02-5-premium-poster-collection-erilaisia-111239016",
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box",
    "https://www.verkkokauppa.com/fi/product/1037336/Pokemon-First-Partner-Collection-Box-Series-1-kerailykorttis",
    "https://www.verkkokauppa.com/fi/product/1037318/Pokemon-ME02-5-Premium-Poster-Collection-Mega-Lucario-ex-Meg",
    "https://www.verkkokauppa.com/fi/product/1037309/Pokemon-ME02-5-Ascended-Heroes-Booster-Bundle-kerailykorttip",
    "https://www.verkkokauppa.com/fi/product/1031984/Pokemon-TCG-ME02-5-Ascended-Heroes-Elite-Trainer-Box-keraily",
    "https://www.verkkokauppa.com/fi/product/980099/Pokemon-TCG-Scarlet-Violet-Destined-Rivals-Elite-Trainer-Box"
]

CHECK_INTERVAL = 60  # tarkistusväli sekunteina

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STATE ----------------
last_state = {}
START_TIME = datetime.now()
LAST_CHECK = "Ei vielä"

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
        await asyncio.sleep(random.uniform(0.3, 1.2))
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
    if not channel:
        log.error("Discord channel not found")
        return

    global LAST_CHECK

    while True:
        try:
            LAST_CHECK = datetime.now().strftime("%H:%M:%S")
            results = await asyncio.gather(*[fetch(url) for url in URLS])

            for url, soup in results:
                if not soup:
                    continue

                status = check_availability(url, soup)
                title = get_title(soup)

                log.info(f"{url} -> {status}")

                # jos tilaa ei ole vielä tallennettu
                if url not in last_state:
                    last_state[url] = status
                    continue

                # ilmoita heti jos tila muuttuu
                if status == "in" and last_state[url] != "in":
                    embed = discord.Embed(
                        title="🔥 TUOTE SAATAVILLA!",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )
                    await channel.send(embed=embed)
                    await send_telegram(f"🔥 <b>RESTOCK!</b>\n\n<b>{title}</b>\n\n{url}")

                # päivitä viimeisin tila
                last_state[url] = status

        except Exception as e:
            log.error(f"Loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL + random.randint(-10, 20))

# ---------------- COMMANDS ----------------
@tree.command(name="ping", description="Botin viive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(client.latency * 1000)}ms")

@tree.command(name="status", description="Botin tila")
async def status(interaction: discord.Interaction):
    uptime = datetime.now() - START_TIME
    embed = discord.Embed(title="📊 Bot Status", color=0x00ff00)
    embed.add_field(name="🟢 Status", value="Online", inline=True)
    embed.add_field(name="📡 Latency", value=f"{round(client.latency * 1000)}ms", inline=True)
    embed.add_field(name="📦 URLit", value=str(len(URLS)), inline=True)
    embed.add_field(name="⏱ Check", value=f"{CHECK_INTERVAL}s", inline=True)
    embed.add_field(name="🕒 Last check", value=LAST_CHECK, inline=True)
    embed.add_field(name="⌛ Uptime", value=str(uptime).split('.')[0], inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="forcecheck", description="Pakota tarkistus nyt")
async def forcecheck(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 Pakotettu tarkistus käynnissä...")
    results = await asyncio.gather(*[fetch(url) for url in URLS])
    for url, soup in results:
        if soup:
            log.info(f"Force check: {url} -> {check_availability(url, soup)}")

# ---------------- READY ----------------
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
    await tree.sync()
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ Bot käynnissä")
    await send_telegram("✅ Bot online")
    client.loop.create_task(check_loop())

client.run(TOKEN)
