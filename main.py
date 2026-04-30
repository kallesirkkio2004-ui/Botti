import discord
import requests
from bs4 import BeautifulSoup
import asyncio
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

URLS = [
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box"
]

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def check_availability(url, soup):
    text = soup.get_text(" ", strip=True).lower()

    # 🔵 Prisma
    if "prisma.fi" in url:
        if "ei saatavilla" in text:
            return "ei saatavilla"
        elif "loppu varastosta" in text:
            return "loppu varastosta"
        elif "lisää ostoskoriin" in text:
            return "saatavilla"

    # 🟠 Kärkkäinen
    if "karkkainen.com" in url:
        if "loppu varastosta" in text:
            return "loppu varastosta"
        elif "tilattavissa" in text or "ostoskoriin" in text:
            return "saatavilla"

    return "tuntematon"


async def check_product():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    last_state = {url: None for url in URLS}

    headers = {"User-Agent": "Mozilla/5.0"}

    while True:
        try:
            for url in URLS:
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")

                availability = check_availability(url, soup)

                print(url, "->", availability)  # DEBUG

                # Ensimmäinen kierros: vain tallennetaan tila
                if last_state[url] is None:
                    last_state[url] = availability
                    continue

                # 🔥 Ilmoita VAIN kun tulee saataville
                if availability == "saatavilla" and last_state[url] != "saatavilla":
                    await channel.send(f"🔥 Tuote on taas saatavilla! {url}")

                last_state[url] = availability

        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(300)  # 5 min


@client.event
async def on_ready():
    print(f"Kirjautunut sisään: {client.user}")
    client.loop.create_task(check_product())


client.run(TOKEN)
