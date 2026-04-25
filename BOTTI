import discord
import requests
from bs4 import BeautifulSoup
import asyncio
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
URL = os.getenv("URL")

intents = discord.Intents.default()
client = discord.Client(intents=intents)

async def check_product():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    was_available = False

    while True:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(URL, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")

            if "Saatavilla" in soup.text:
                if not was_available:
                    await channel.send("🔥 Tuote on nyt saatavilla Prismassa!")
                    was_available = True
            else:
                was_available = False

        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(300)

@client.event
async def on_ready():
    print(f"Bot käynnissä: {client.user}")
    client.loop.create_task(check_product())

client.run(TOKEN)
