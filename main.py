import discord
import requests
from bs4 import BeautifulSoup
import asyncio
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
URLS = [
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553?listName=search+result&listNameExtra=ascended",  # Prisma 1
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",  # Prisma 2
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box"  # Kärkkäinen
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

                
                if "ei saatavilla" in current_state.lower():
                    availability = "ei saatavilla"
                elif "saatavilla" in current_state.lower():
                    availability = "saatavilla"

                
                elif "loppu varastosta" in current_state.lower():
                    availability = "loppu varastosta"
                else:
                    availability = "tuntematon"

                if last_state[url] is None:
                    last_state[url] = availability

                
                elif availability != last_state[url]:
                    if availability == "saatavilla":
                        await channel.send(f"🔥 Tuote on nyt saatavilla! {url}")
                    elif availability == "ei saatavilla":
                        await channel.send(f"❌ Tuote on nyt ei saatavilla! {url}")
                    elif availability == "loppu varastosta":
                        await channel.send(f"❌ Tuote on nyt loppu varastosta! {url}")
                    last_state[url] = availability

        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(300)  # Tarkistetaan tilanne 5 minuutin välein

@client.event
async def on_ready():
    print(f"Bot käynnissä: {client.user}")
    client.loop.create_task(check_product())

client.run(TOKEN)
