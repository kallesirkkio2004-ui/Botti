import discord
import requests
from bs4 import BeautifulSoup
import asyncio
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
URLS = [
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553?listName=search+result&listNameExtra=ascended",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box"
]

intents = discord.Intents.default()
client = discord.Client(intents=intents)

async def check_product():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    last_state = {url: None for url in URLS}

    while True:
        try:
            for url in URLS:
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, "html.parser")

                current_state = soup.text.strip()

                if last_state[url] is None:
                    last_state[url] = current_state
                elif current_state != last_state[url]:
                    await channel.send(f"🔔 {url} tuotteen tila muuttui!")
                    last_state[url] = current_state
        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(300)

@client.event
async def on_ready():
    print(f"Bot käynnissä: {client.user}")
    client.loop.create_task(check_product())

client.run(TOKEN)
