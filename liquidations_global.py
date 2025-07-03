import asyncio
import websockets
import json
from datetime import datetime
from playsound import playsound

ALERT_SOUND_PATH = "/Users/robinnakamoto/Library/Mobile Documents/com~apple~CloudDocs/Dev/binance-liquidations/liquidations_alert.wav"

BINANCE_PAIRS = [
    ("Binance", "wss://fstream.binance.com/ws/btcusdt@forceOrder"),
    ("Binance", "wss://fstream.binance.com/ws/btcusdc@forceOrder")
]

OKX_FEED = ("OKX", "wss://ws.okx.com:8443/ws/v5/public")
BYBIT_FEED = ("Bybit", "wss://stream.bybit.com/v5/public/linear")
BITMEX_FEED = ("BitMEX", "wss://www.bitmex.com/realtime")

FEEDS = BINANCE_PAIRS + [OKX_FEED, BYBIT_FEED, BITMEX_FEED]

def format_usd(amount):
    return f"${amount:,.2f}"

def format_price(price):
    return f"${price:,.0f}"

async def handle_binance(msg):
    data = json.loads(msg)
    if data.get("e") == "forceOrder":
        o = data.get("o", {})
        symbol = o.get("s", "BTCUSDT")
        side = o.get("S", "SELL")
        qty = float(o.get("q", 0))
        price = float(o.get("p", 0))
        total = qty * price

        if side == "SELL":
            emoji = "🟢"
            label = "Long REKT"
        else:
            emoji = "🔴"
            label = "Short REKT"

        print(f"{emoji} Binance {label} {emoji} {qty:.4f} BTC @ {format_price(price)} 💥  {format_usd(total)} 💥")
        playsound(ALERT_SOUND_PATH)

async def handle_bybit(msg):
    data = json.loads(msg)
    if data.get("topic") == "liquidation.linear":
        for item in data.get("data", []):
            symbol = item.get("symbol", "BTCUSDT")
            side = item.get("side", "Sell").upper()
            qty = float(item.get("qty", 0))
            price = float(item.get("price", 0))
            total = qty * price

            if side == "SELL":
                emoji = "🟢"
                label = "Long REKT"
            else:
                emoji = "🔴"
                label = "Short REKT"

            print(f"{emoji} Bybit {label} {emoji} {qty:.4f} BTC @ {format_price(price)} 💥  {format_usd(total)} 💥")
            playsound(ALERT_SOUND_PATH)

async def handle_bitmex(msg):
    data = json.loads(msg)
    if data.get("table") == "liquidation" and "data" in data:
        for item in data["data"]:
            symbol = item.get("symbol", "XBTUSD")
            side = item.get("side", "Sell").upper()
            price = float(item.get("price", 0))
            qty = float(item.get("leavesQty", 0))
            total = qty * price

            if side == "SELL":
                emoji = "🟢"
                label = "Long REKT"
            else:
                emoji = "🔴"
                label = "Short REKT"

            print(f"{emoji} BitMEX {label} {emoji} {qty:.4f} XBT @ {format_price(price)} 💥  {format_usd(total)} 💥")
            playsound(ALERT_SOUND_PATH)

async def handle_okx(msg):
    data = json.loads(msg)
    if data.get("arg", {}).get("channel") == "liquidation" and "data" in data:
        for item in data["data"]:
            symbol = item.get("instId", "BTC-USDT-SWAP")
            side = item.get("side", "sell").upper()
            price = float(item.get("bkPx", 0))
            qty = float(item.get("sz", 0))
            total = qty * price

            if side == "SELL":
                emoji = "🟢"
                label = "Long REKT"
            else:
                emoji = "🔴"
                label = "Short REKT"

            print(f"{emoji} OKX {label} {emoji} {qty:.4f} @ {format_price(price)} 💥  {format_usd(total)} 💥")
            playsound(ALERT_SOUND_PATH)

async def subscribe(source, uri):
    async with websockets.connect(uri) as ws:
        print(f"✅ Subscribed to {source} @ {uri}")

        if source == "Bybit":
            await ws.send(json.dumps({"op": "subscribe", "args": ["liquidation.linear"]}))
        elif source == "BitMEX":
            await ws.send(json.dumps({"op": "subscribe", "args": ["liquidation"]}))
        elif source == "OKX":
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": [{"channel": "liquidation", "instType": "SWAP", "instId": "BTC-USDT-SWAP"}]
            }))

        while True:
            msg = await ws.recv()
            if source == "Binance":
                await handle_binance(msg)
            elif source == "Bybit":
                await handle_bybit(msg)
            elif source == "BitMEX":
                await handle_bitmex(msg)
            elif source == "OKX":
                await handle_okx(msg)

async def main():
    await asyncio.gather(*(subscribe(source, uri) for source, uri in FEEDS))

asyncio.run(main())
