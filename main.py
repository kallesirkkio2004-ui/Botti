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

    last_state = None

    while True:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(URL, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")

            current_state = soup.text.strip()

            if last_state is None:
                last_state = current_state

            elif current_state != last_state:
                await channel.send("🔔 Tuotteen tila muuttui!")
                last_state = current_state

        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(300)

@client.event
async def on_ready():
    print(f"Bot käynnissä: {client.user}")
    client.loop.create_task(check_product())

client.run(TOKEN)
