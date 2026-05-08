import discord
import requests
from bs4 import BeautifulSoup
import asyncio
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# 🔥 Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# (optional) rooli ping → laita ID tai None
ROLE_ID = None

URLS = [
    # 🔵 Prisma
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.prisma.fi/tuotteet/111239016/pokemon-tcg-me02-5-premium-poster-collection-erilaisia-111239016",

    # 🟠 Kärkkäinen
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box",

    # 🟣 Verkkokauppa
    "https://www.verkkokauppa.com/fi/product/1037336/Pokemon-First-Partner-Collection-Box-Series-1-kerailykorttis",
    "https://www.verkkokauppa.com/fi/product/1037318/Pokemon-ME02-5-Premium-Poster-Collection-Mega-Lucario-ex-Meg",
    "https://www.verkkokauppa.com/fi/product/1037309/Pokemon-ME02-5-Ascended-Heroes-Booster-Bundle-kerailykorttip",
    "https://www.verkkokauppa.com/fi/product/1031984/Pokemon-TCG-ME02-5-Ascended-Heroes-Elite-Trainer-Box-keraily"
]

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def get_title(soup):
    if soup.title:
        return soup.title.text.strip()
    return "Tuote"


def check_availability(url, soup):
    text = soup.get_text(" ", strip=True).lower()

    # 🔵 Prisma
    if "prisma.fi" in url:
        if "ei saatavilla" in text or "loppu varastosta" in text:
            return "out"
        if "lisää ostoskoriin" in text or "tilattavissa" in text:
            return "in"

    # 🟠 Kärkkäinen
    if "karkkainen.com" in url:
        if "loppu varastosta" in text:
            return "out"
        if "tilattavissa" in text or "ostoskoriin" in text:
            return "in"

    # 🟣 Verkkokauppa
    if "verkkokauppa.com" in url:
        if "ei saatavilla" in text or "loppu varastosta" in text:
            return "out"

        buttons = soup.find_all("button")
        for b in buttons:
            if "ostoskoriin" in b.get_text().lower():
                return "in"

    return "unknown"


# 🔥 Telegram viestin lähetys
async def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        requests.post(url, data=data, timeout=10)

    except Exception as e:
        print("Telegram error:", e)


async def check_product():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    last_state = {url: None for url in URLS}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "fi-FI,fi;q=0.9"
    }

    while True:
        try:
            for url in URLS:
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")

                status = check_availability(url, soup)
                title = get_title(soup)

                print(url, "->", status)

                # eka kierros → ei spämmiä
                if last_state[url] is None:
                    last_state[url] = status
                    continue

                # 🔥 ilmoitus kun tulee saataville
                if status == "in" and last_state[url] != "in":

                    embed = discord.Embed(
                        title="🔥 TUOTE SAATAVILLA!",
                        description=f"[{title}]({url})",
                        color=0x00ff00
                    )

                    embed.add_field(
                        name="Status",
                        value="✅ In Stock",
                        inline=False
                    )

                    msg = ""
                    if ROLE_ID:
                        msg = f"<@&{ROLE_ID}>"

                    # Discord ilmoitus
                    await channel.send(content=msg, embed=embed)

                    # Telegram ilmoitus
                    telegram_msg = f"""
🔥 <b>TUOTE SAATAVILLA!</b>

<b>{title}</b>

🛒 {url}
"""

                    await send_telegram(telegram_msg)

                last_state[url] = status

        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(60)


@client.event
async def on_ready():
    print(f"Kirjautunut sisään: {client.user}")

    channel = client.get_channel(CHANNEL_ID)

    await channel.send("✅ Restock-botti käynnissä!")

    # 🔥 Telegram testiviesti
    await send_telegram("✅ Telegram yhdistetty onnistuneesti!")

    client.loop.create_task(check_product())


client.run(TOKEN)
