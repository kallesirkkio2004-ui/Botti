"""
Pokemon TCG -varastovahti
==========================
Seuraa listaa verkkokauppojen tuotesivuja ja hälyttää Discordiin + Telegramiin
kun jokin tuote muuttuu "loppu"/"tuntematon" -> "saatavilla".

Suunnitteluperiaatteet:
- Ensisijainen tunnistus: schema.org JSON-LD (Product/Offer.availability).
  Tämä on standardoitu tapa jota valtaosa verkkokaupoista käyttää SEO:ta
  varten, ja se on paljon luotettavampi kuin avainsanahaku sivun tekstistä.
- Varajärjestelmä: avainsanahaku, jossa "loppu varastossa" -tyyppiset
  signaalit voittavat "lisää ostoskoriin" -tyyppiset signaalit, koska monilla
  sivustoilla ostoskori-nappi on HTML:ssä läsnä (disabloituna) vaikka tuote
  olisi loppu.
- Per-domeeni-rajoitin pyynnöille, jotta yksittäistä kauppaa ei pommiteta.
- Tila persistoidaan levylle, jotta uudelleenkäynnistys ei unohda mitä on
  jo hälytetty.
- "unknown"-tila ei koskaan ylikirjoita viimeisintä tunnettua tilaa, jotta
  yksittäinen epäonnistunut lataus ei aiheuta turhaa hälytystä.
"""

import asyncio
import json
import logging
import os
import random
import re
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import aiohttp
import discord
from bs4 import BeautifulSoup
from discord import app_commands

# =========================================================================
# CONFIG
# =========================================================================

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    token: str = field(default_factory=lambda: os.getenv("TOKEN", ""))
    channel_id: int = field(default_factory=lambda: _env_int("CHANNEL_ID", 0))
    telegram_token: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN"))
    telegram_chat_id: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))
    test_guild_id: int = field(default_factory=lambda: _env_int("TEST_GUILD_ID", 0))

    check_interval_min: float = field(default_factory=lambda: _env_float("CHECK_INTERVAL_MIN", 30))
    check_interval_max: float = field(default_factory=lambda: _env_float("CHECK_INTERVAL_MAX", 60))
    per_domain_concurrency: int = field(default_factory=lambda: _env_int("PER_DOMAIN_CONCURRENCY", 2))
    global_concurrency: int = field(default_factory=lambda: _env_int("GLOBAL_CONCURRENCY", 6))
    request_timeout: float = field(default_factory=lambda: _env_float("REQUEST_TIMEOUT", 20))

    state_file: str = field(default_factory=lambda: os.getenv("STATE_FILE", "last_state.json"))
    broken_url_threshold: int = field(default_factory=lambda: _env_int("BROKEN_URL_ALERT_THRESHOLD", 10))
    alert_cooldown_minutes: float = field(default_factory=lambda: _env_float("ALERT_COOLDOWN_MINUTES", 15))

    max_backoff: float = field(default_factory=lambda: _env_float("MAX_BACKOFF_SECONDS", 900))

    def validate(self) -> list[str]:
        problems = []
        if not self.token:
            problems.append("TOKEN puuttuu - botti ei voi kirjautua Discordiin.")
        if not self.channel_id:
            problems.append("CHANNEL_ID puuttuu tai on 0 - hälytyksiä ei voida lähettää Discord-kanavalle.")
        if not self.telegram_token or not self.telegram_chat_id:
            problems.append("TELEGRAM_TOKEN/TELEGRAM_CHAT_ID puuttuu - Telegram-hälytykset ovat pois päältä.")
        return problems


CFG = Config()

# =========================================================================
# URLS
# =========================================================================

URLS = [
    # Suomi
    "https://www.verkkokauppa.com/fi/product/980138/Pokemon-SV10-boosters-kerailykortit-36-pack",
    "https://www.prisma.fi/tuotteet/111268553/pokemon-tcg-kerailykortit-me02-5-ascended-heroes-booster-bundle-111268553",
    "https://www.prisma.fi/tuotteet/111268550/pokemon-tcg-kerailykortit-first-partner-collection-box-111268550",
    "https://www.prisma.fi/tuotteet/111239016/pokemon-tcg-me02-5-premium-poster-collection-erilaisia-111239016",
    "https://www.karkkainen.com/verkkokauppa/pokemon-tcg-me02-5-elite-trainer-box",
    "https://www.verkkokauppa.com/fi/product/1037336/Pokemon-First-Partner-Collection-Box-Series-1-kerailykorttis",
    "https://www.verkkokauppa.com/fi/product/1037318/Pokemon-ME02-5-Premium-Poster-Collection-Mega-Lucario-ex-Meg",
    "https://www.verkkokauppa.com/fi/product/1037309/Pokemon-ME02-5-Ascended-Heroes-Booster-Bundle-kerailykorttip",
    "https://www.verkkokauppa.com/fi/product/1031984/Pokemon-TCG-ME02-5-Ascended-Heroes-Elite-Trainer-Box-keraily",
    "https://www.verkkokauppa.com/fi/product/980099/Pokemon-TCG-Scarlet-Violet-Destined-Rivals-Elite-Trainer-Box",
    "https://www.prisma.fi/tuotteet/111354656/poke-first-partner-collection-box-2-19-6-111354656",
    "https://www.prisma.fi/tuotteet/111268549/pokemon-tcg-kerailykortit-me025-ascended-heroes-ex-box-erilaisia-111268549",
    "https://www.karkkainen.com/verkkokauppa/pokemon-first-partner-collection-box-2-kerailykortit",
    "https://www.muovitukku.fi/tuote/pokemon-tcg-first-partner-illustration-collection-series-2/",
    "https://www.muovitukku.fi/tuote/pokemon-tcg-mega-evolution-ascended-heroes-booster-bundle/",
    "https://www.muovitukku.fi/tuote/pokemon-tcg-me5-pitch-black-elite-trainer-box-julkaisupaiva-17-7-2026/",
    "https://www.muovitukku.fi/tuote/pokemon-tcg-me5-pitch-black-booster-bundle-julkaisupaiva-17-7-2026/",
    "https://www.prisma.fi/tuotteet/111354652/poke-first-partner-collection-box-3-78-111354652",
    "https://www.karkkainen.com/verkkokauppa/pokemon-first-partner-collection-box-3-kerailykortit",
    "https://peliparatiisi.net/products/pokemon-tcg-30th-celebration-elite-trainer-box?_pos=2&_sid=a7f17e2b7&_ss=r",
    "https://www.korttistoppi.fi/tuote/pokemon-tcg-30th-celebration-elite-trainer-box-julkaisupaiva-1692026?category=30th-celebration",

    # Eurooppa
    "https://eurotcg.com/be/product/pokemon-booster-bundle-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolution-ascended-heroes-pre-order",
    "https://eurotcg.com/be/product/pokemon-booster-box-destined-rivals",
    "https://eurotcg.com/be/product/pokemon-elite-trainer-box-mega-evolutions-phantasmal-flames-pre-order",
    "https://www.playingcardshop.eu/pokemon-tcg-mega-evolution-ascended-heroes-booster-bundle-6-packs.html",
    "https://www.playingcardshop.eu/pokemon-tcg-scarlet-and-violet-destined-rivals-elite-trainer-box.html",
]

# =========================================================================
# LOGGING
# =========================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
log = logging.getLogger("pokebot")

# =========================================================================
# DISCORD CLIENT
# =========================================================================

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================================================================
# STOCK DETECTION
# =========================================================================

# Tekstipohjainen varajärjestelmä. Järjestys on tärkeä: OUT tarkistetaan
# ENSIN, koska "lisää ostoskoriin" -tyyppinen teksti on monilla sivustoilla
# HTML:ssä läsnä (disabloituna) vaikka tuote olisi loppu.
OUT_PHRASES = [
    "ei saatavilla", "loppu varastosta", "loppuunmyyty", "ei varastossa",
    "out of stock", "sold out", "unavailable", "niet op voorraad",
    "épuisé", "momenteel niet",
]
IN_PHRASES = [
    "ostoskoriin", "lisää ostoskoriin", "add to cart", "add to basket",
    "buy now", "pre-order", "varastossa", "in stock", "op voorraad",
    "in voorraad",
]

AVAILABILITY_IN = {"instock", "limitedavailability", "preorder", "backorder"}
AVAILABILITY_OUT = {"outofstock", "discontinued", "soldout"}


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def extract_jsonld_availability(soup: BeautifulSoup) -> Optional[str]:
    """Etsii schema.org Product/Offer-lohkon ja palauttaa 'in' / 'out' / None.

    Tämä on ensisijainen tunnistustapa koska se perustuu rakenteiseen dataan
    jonka kauppa itse julkaisee hakukoneita varten, eikä siis riipu sivun
    visuaalisesta tekstistä tai napin tilasta.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            # @graph-wrapperit (yleinen mm. WordPress/WooCommerce-sivuilla)
            graph = node.get("@graph")
            sub_candidates = graph if isinstance(graph, list) else [node]

            for item in sub_candidates:
                if not isinstance(item, dict):
                    continue
                offers = item.get("offers")
                offer_list = offers if isinstance(offers, list) else [offers] if offers else []
                for offer in offer_list:
                    if not isinstance(offer, dict):
                        continue
                    availability = offer.get("availability", "")
                    if not isinstance(availability, str):
                        continue
                    token = availability.rsplit("/", 1)[-1].lower()
                    if token in AVAILABILITY_IN:
                        return "in"
                    if token in AVAILABILITY_OUT:
                        return "out"
    return None


def extract_price(soup: BeautifulSoup) -> Optional[str]:
    """Parhaan yrityksen hinnanhaku JSON-LD:stä, jos saatavilla."""
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            sub = node.get("@graph") if isinstance(node.get("@graph"), list) else [node]
            for item in sub:
                if not isinstance(item, dict):
                    continue
                offers = item.get("offers")
                offer_list = offers if isinstance(offers, list) else [offers] if offers else []
                for offer in offer_list:
                    if isinstance(offer, dict) and offer.get("price"):
                        currency = offer.get("priceCurrency", "")
                        return f"{offer['price']} {currency}".strip()
    return None


def check_text(text: str) -> str:
    text = text.lower()
    if any(p in text for p in OUT_PHRASES):
        return "out"
    if any(p in text for p in IN_PHRASES):
        return "in"
    return "unknown"


def detect_state(soup: BeautifulSoup, page_text: str) -> str:
    jsonld_state = extract_jsonld_availability(soup)
    if jsonld_state:
        return jsonld_state
    return check_text(page_text)


def page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.text:
        # monilla sivuilla title on muotoa "Tuote - Kauppa", siistitään hieman
        return re.sub(r"\s+", " ", soup.title.text).strip()
    return "Tuote"

# =========================================================================
# STATE
# =========================================================================

@dataclass
class UrlState:
    state: Optional[str] = None
    consecutive_unknown: int = 0
    consecutive_errors: int = 0
    alerted_broken: bool = False
    last_alert_at: Optional[str] = None  # ISO timestamp

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


class StateStore:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, UrlState] = {}
        self._lock = asyncio.Lock()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.data = {url: UrlState.from_dict(v) for url, v in raw.items()}
                log.info(f"Ladattiin tila {len(self.data)} URL:lle tiedostosta {self.path}")
            except Exception as e:
                log.error(f"Tilan lataus epäonnistui ({self.path}): {e}")
                self.data = {}

    async def save(self):
        async with self._lock:
            tmp_path = f"{self.path}.tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump({u: s.to_dict() for u, s in self.data.items()}, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.path)  # atominen kirjoitus
            except Exception as e:
                log.error(f"Tilan tallennus epäonnistui: {e}")

    def get(self, url: str) -> UrlState:
        if url not in self.data:
            self.data[url] = UrlState()
        return self.data[url]


store = StateStore(CFG.state_file)

# =========================================================================
# HTTP
# =========================================================================

session: Optional[aiohttp.ClientSession] = None
global_semaphore: Optional[asyncio.Semaphore] = None
domain_semaphores: dict[str, asyncio.Semaphore] = {}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15",
]


def domain_semaphore(url: str) -> asyncio.Semaphore:
    d = _domain(url)
    if d not in domain_semaphores:
        domain_semaphores[d] = asyncio.Semaphore(CFG.per_domain_concurrency)
    return domain_semaphores[d]


async def fetch(url: str) -> Optional[str]:
    assert session is not None and global_semaphore is not None
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "fi,en;q=0.8"}
    try:
        async with global_semaphore, domain_semaphore(url):
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=CFG.request_timeout)
            ) as r:
                if r.status == 429:
                    log.warning(f"429 Too Many Requests: {url}")
                    return None
                if r.status != 200:
                    log.warning(f"HTTP {r.status}: {url}")
                    return None
                html = await r.text()
                lowered = html.lower()
                if "captcha" in lowered or "access denied" in lowered or "cloudflare" in lowered and "checking your browser" in lowered:
                    log.warning(f"Blokattu / captcha: {url}")
                    return None
                return html
    except asyncio.TimeoutError:
        log.error(f"Timeout: {url}")
        return None
    except Exception as e:
        log.error(f"Fetch-virhe {url}: {e}")
        return None

# =========================================================================
# NOTIFICATIONS
# =========================================================================

async def send_telegram(msg: str):
    if not CFG.telegram_token or not CFG.telegram_chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{CFG.telegram_token}/sendMessage"
        async with session.post(
            url,
            data={"chat_id": CFG.telegram_chat_id, "text": msg, "parse_mode": "HTML",
                  "disable_web_page_preview": "false"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                log.error(f"Telegram vastasi {r.status}: {await r.text()}")
    except Exception as e:
        log.error(f"Telegram-virhe: {e}")


async def send_discord_alert(title: str, url: str, price: Optional[str]):
    try:
        channel = client.get_channel(CFG.channel_id)
        if channel:
            embed = discord.Embed(
                title="🔥 TUOTE SAATAVILLA!",
                url=url,
                description=f"[{title}]({url})",
                color=0x00FF00,
                timestamp=datetime.now(),
            )
            if price:
                embed.add_field(name="Hinta", value=price, inline=True)
            embed.add_field(name="Kauppa", value=_domain(url), inline=True)
            await channel.send(content="@everyone", embed=embed)
    except discord.HTTPException as e:
        log.error(f"Discord-hälytys epäonnistui (HTTP): {e}")
    except Exception as e:
        log.error(f"Discord-hälytys epäonnistui: {e}")

    price_line = f"\n💶 {price}" if price else ""
    await send_telegram(f"🔥 <b>{title}</b>{price_line}\n🛒 {url}")


async def send_broken_url_alert(url: str, failures: int):
    msg = (f"⚠️ **{_domain(url)}** ei ole antanut tunnistettavaa tulosta {failures} "
           f"peräkkäisellä yrityksellä.\nSivupohja on voinut muuttua tai IP on blokattu:\n{url}")
    log.warning(msg)
    try:
        channel = client.get_channel(CFG.channel_id)
        if channel:
            await channel.send(msg)
    except Exception as e:
        log.error(f"Broken-url-hälytys epäonnistui: {e}")

# =========================================================================
# MONITOR LOOP
# =========================================================================

async def monitor(url: str, stop_event: asyncio.Event):
    st = store.get(url)
    backoff = CFG.check_interval_max  # kasvaa peräkkäisillä virheillä

    while not stop_event.is_set():
        html = await fetch(url)

        if html is None:
            st.consecutive_errors += 1
            backoff = min(backoff * 1.5, CFG.max_backoff)
            log.info(f"{_domain(url)} -> fetch epäonnistui ({st.consecutive_errors}. kerta), "
                     f"odotetaan {backoff:.0f}s")
        else:
            backoff = CFG.check_interval_max
            st.consecutive_errors = 0
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            state = detect_state(soup, text)
            prev = st.state
            log.info(f"{_domain(url)} -> {state}")

            if state == "unknown":
                st.consecutive_unknown += 1
                if st.consecutive_unknown >= CFG.broken_url_threshold and not st.alerted_broken:
                    await send_broken_url_alert(url, st.consecutive_unknown)
                    st.alerted_broken = True
                # Ei ylikirjoiteta tunnettua tilaa "unknown"-arvolla.
            else:
                st.consecutive_unknown = 0
                st.alerted_broken = False

                if prev is None:
                    st.state = state
                elif prev != state:
                    st.state = state
                    if state == "in":
                        can_alert = True
                        if st.last_alert_at:
                            elapsed = datetime.now() - datetime.fromisoformat(st.last_alert_at)
                            can_alert = elapsed > timedelta(minutes=CFG.alert_cooldown_minutes)
                        if can_alert:
                            price = extract_price(soup)
                            await send_discord_alert(page_title(soup), url, price)
                            st.last_alert_at = datetime.now().isoformat()
                        else:
                            log.info(f"{_domain(url)}: hälytys jäähyllä, ohitetaan tällä kertaa")

            await store.save()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=random.uniform(
                CFG.check_interval_min, max(CFG.check_interval_min, backoff)
            ))
        except asyncio.TimeoutError:
            pass  # normaali - jatketaan seuraavaan tarkistukseen

# =========================================================================
# LIFECYCLE
# =========================================================================

_setup_done = False
_stop_event: Optional[asyncio.Event] = None
_monitor_tasks: list[asyncio.Task] = []
_start_time = datetime.now()


@client.event
async def on_ready():
    global session, global_semaphore, _setup_done, _stop_event

    log.info(f"Kirjauduttu sisään: {client.user}")

    if _setup_done:
        log.info("on_ready laukesi uudelleen (reconnect) - ohitetaan alustus")
        return
    _setup_done = True

    problems = CFG.validate()
    for p in problems:
        log.warning(f"KONFIGURAATIOVAROITUS: {p}")

    session = aiohttp.ClientSession()
    global_semaphore = asyncio.Semaphore(CFG.global_concurrency)
    _stop_event = asyncio.Event()

    store.load()

    try:
        if CFG.test_guild_id:
            await tree.sync(guild=discord.Object(id=CFG.test_guild_id))
        else:
            await tree.sync()
    except Exception as e:
        log.error(f"Komentojen synkronointi epäonnistui: {e}")

    for url in URLS:
        _monitor_tasks.append(asyncio.create_task(monitor(url, _stop_event)))

    channel = client.get_channel(CFG.channel_id)
    if channel:
        await channel.send(f"✅ BOT ONLINE — seurataan {len(URLS)} tuotetta ({len(set(_domain(u) for u in URLS))} kauppaa)")


async def shutdown():
    log.info("Suljetaan siististi...")
    if _stop_event:
        _stop_event.set()
    if _monitor_tasks:
        await asyncio.gather(*_monitor_tasks, return_exceptions=True)
    await store.save()
    if session:
        await session.close()
    await client.close()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop):
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
        except NotImplementedError:
            pass  # esim. Windows

# =========================================================================
# SLASH COMMANDS
# =========================================================================

@tree.command(name="status", description="Näytä botin tila")
async def status_cmd(interaction: discord.Interaction):
    uptime = datetime.now() - _start_time
    in_stock = [u for u, s in store.data.items() if s.state == "in"]
    broken = [u for u, s in store.data.items() if s.alerted_broken]

    lines = [
        f"**Uptime:** {str(uptime).split('.')[0]}",
        f"**Seurattavia URLeja:** {len(URLS)}",
        f"**Saatavilla juuri nyt:** {len(in_stock)}",
    ]
    if in_stock:
        lines.append("\n".join(f"🟢 {_domain(u)}" for u in in_stock[:10]))
    if broken:
        lines.append(f"\n⚠️ **Ongelmallisia sivuja:** {len(broken)}")
        lines.append("\n".join(f"🔴 {_domain(u)}" for u in broken[:10]))

    await interaction.response.send_message("\n".join(lines))


@tree.command(name="ping", description="Testaa botti")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong {round(client.latency * 1000)}ms")


@tree.command(name="watchlist", description="Näytä kaikki seurattavat tuotteet ja niiden tila")
async def watchlist_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    icon = {"in": "🟢", "out": "🔴", None: "⚪", "unknown": "⚪"}
    lines = []
    for u in URLS:
        s = store.get(u)
        lines.append(f"{icon.get(s.state, '⚪')} {_domain(u)}")
    chunk = "\n".join(lines)
    if len(chunk) > 1900:
        chunk = chunk[:1900] + "\n… (lyhennetty)"
    await interaction.followup.send(chunk or "Ei tuotteita listalla.")


@tree.command(name="test_telegram", description="Lähetä testiviesti Telegramiin")
async def test_telegram_cmd(interaction: discord.Interaction):
    if not CFG.telegram_token or not CFG.telegram_chat_id:
        await interaction.response.send_message("Telegram token tai chat_id puuttuu!", ephemeral=True)
        return
    try:
        await send_telegram("✅ Tämä on testiviesti Telegramista!")
        await interaction.response.send_message("Testiviesti lähetetty Telegramiin!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Virhe viestin lähetyksessä: {e}", ephemeral=True)


@tree.command(name="check", description="Pakota välitön tarkistus tietylle kaupalle (osittainen nimi)")
@app_commands.describe(domain="Esim. verkkokauppa, prisma, karkkainen")
async def check_cmd(interaction: discord.Interaction, domain: str):
    matches = [u for u in URLS if domain.lower() in u.lower()]
    if not matches:
        await interaction.response.send_message("Ei osumia.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    results = []
    for u in matches[:5]:
        html = await fetch(u)
        if html is None:
            results.append(f"❌ {_domain(u)}: haku epäonnistui")
            continue
        soup = BeautifulSoup(html, "html.parser")
        state = detect_state(soup, soup.get_text(" ", strip=True))
        results.append(f"{'🟢' if state == 'in' else '🔴' if state == 'out' else '⚪'} {_domain(u)}: {state}")
    await interaction.followup.send("\n".join(results), ephemeral=True)

# =========================================================================
# ENTRYPOINT
# =========================================================================

def main():
    problems = CFG.validate()
    if not CFG.token:
        log.critical("TOKEN puuttuu ympäristömuuttujista - botti ei voi käynnistyä.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)

    try:
        loop.run_until_complete(client.start(CFG.token))
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(shutdown())
        loop.close()


if __name__ == "__main__":
    main()
