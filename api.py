# BACKEND: `api.py` — this serves liquidations via SSE

import asyncio
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from websockets import connect

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

subscribers = set()

FEEDS = [
    ("Binance", "wss://fstream.binance.com/ws/btcusdt@forceOrder"),
    ("Binance", "wss://fstream.binance.com/ws/btcusdc@forceOrder"),
    ("OKX", "wss://ws.okx.com:8443/ws/v5/public"),
    ("Bybit", "wss://stream.bybit.com/v5/public/linear"),
    ("BitMEX", "wss://www.bitmex.com/realtime")
]

async def broadcast(msg):
    for q in list(subscribers):
        await q.put(msg)

async def stream_feed(source, uri):
    async with connect(uri) as ws:
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
            data = json.loads(msg)

            if source == "Binance" and data.get("e") == "forceOrder":
                o = data.get("o", {})
                side = o.get("S", "SELL")
                emoji = "🟢" if side == "SELL" else "🔴"
                label = "Long REKT" if side == "SELL" else "Short REKT"
                qty = float(o.get("q", 0))
                price = float(o.get("p", 0))
                total = qty * price
                formatted = f"{emoji} Binance {label} {emoji} {qty:.4f} BTC @ ${price:,.0f} 💥  ${total:,.2f} 💥"

            elif source == "Bybit" and data.get("topic") == "liquidation.linear":
                for item in data.get("data", []):
                    side = item.get("side", "Sell").upper()
                    emoji = "🟢" if side == "SELL" else "🔴"
                    label = "Long REKT" if side == "SELL" else "Short REKT"
                    qty = float(item.get("qty", 0))
                    price = float(item.get("price", 0))
                    total = qty * price
                    formatted = f"{emoji} Bybit {label} {emoji} {qty:.4f} BTC @ ${price:,.0f} 💥  ${total:,.2f} 💥"
                    await broadcast(formatted)
                continue

            elif source == "BitMEX" and data.get("table") == "liquidation":
                for item in data.get("data", []):
                    side = item.get("side", "Sell").upper()
                    emoji = "🟢" if side == "SELL" else "🔴"
                    label = "Long REKT" if side == "SELL" else "Short REKT"
                    qty = float(item.get("leavesQty", 0))
                    price = float(item.get("price", 0))
                    total = qty * price
                    formatted = f"{emoji} BitMEX {label} {emoji} {qty:.4f} XBT @ ${price:,.0f} 💥  ${total:,.2f} 💥"
                    await broadcast(formatted)
                continue

            elif source == "OKX" and data.get("arg", {}).get("channel") == "liquidation":
                for item in data.get("data", []):
                    side = item.get("side", "sell").upper()
                    emoji = "🟢" if side == "SELL" else "🔴"
                    label = "Long REKT" if side == "SELL" else "Short REKT"
                    qty = float(item.get("sz", 0))
                    price = float(item.get("bkPx", 0))
                    total = qty * price
                    formatted = f"{emoji} OKX {label} {emoji} {qty:.4f} @ ${price:,.0f} 💥  ${total:,.2f} 💥"
                    await broadcast(formatted)
                continue

            else:
                continue

            await broadcast(formatted)

@app.get("/events")
async def sse_endpoint():
    queue = asyncio.Queue()
    subscribers.add(queue)

    async def event_stream():
        try:
            while True:
                msg = await queue.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            subscribers.remove(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.on_event("startup")
async def startup_event():
    for source, uri in FEEDS:
        asyncio.create_task(stream_feed(source, uri))
