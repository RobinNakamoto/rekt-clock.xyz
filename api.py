import asyncio
import json
import gzip
import os
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import websockets
import redis

app = FastAPI()

# Redis connection
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/summary")
def summary():
    now = datetime.utcnow()
    raw = redis_client.lrange("liquidations", 0, 5000)
    events = [json.loads(e) for e in raw]

    timeframes = {
        "24h": now - timedelta(hours=24),
        "12h": now - timedelta(hours=12),
        "4h": now - timedelta(hours=4),
        "1h": now - timedelta(hours=1),
    }

    summary = {side: {} for side in ["long", "short"]}
    summary["total"] = {}

    for tf, threshold in timeframes.items():
        for side in ["long", "short"]:
            total_btc = 0
            total_usd = 0
            for e in events:
                if e["side"] != side:
                    continue
                if datetime.fromisoformat(e["timestamp"]) < threshold:
                    continue
                total_btc += e["btc"]
                total_usd += e["usd"]
            summary[side][tf] = {"btc": total_btc, "usd": total_usd}

        summary["total"][tf] = {
            "btc": summary["long"][tf]["btc"] + summary["short"][tf]["btc"],
            "usd": summary["long"][tf]["usd"] + summary["short"][tf]["usd"]
        }

    out = ["rekt@rekt-clock % python global_liquidations.py", "", "Recent BTC liquidations:"]
    out += ["🟢 LONGS 🟢"]
    for tf in ["24h", "12h", "4h", "1h"]:
        d = summary["long"][tf]
        out.append(f"💥 {tf} REKT: {d['btc']:.2f} BTC / ${d['usd']:,.0f}")
    out += ["", "🔴 SHORTS 🔴"]
    for tf in ["24h", "12h", "4h", "1h"]:
        d = summary["short"][tf]
        out.append(f"💥 {tf} REKT: {d['btc']:.2f} BTC / ${d['usd']:,.0f}")
    out += ["", "💥  Total REKT: 💥"]
    for tf in ["24h", "12h", "4h", "1h"]:
        d = summary["total"][tf]
        out.append(f"{tf}: {d['btc']:.2f} BTC / ${d['usd']:,.0f}")
    out.append("")
    
    return PlainTextResponse("\n".join(out))


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

subscribers = set()
liquidation_count = 0
start_time = None

# Log to Redis
async def log_liquidation(exchange, side, btc, usd):
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "exchange": exchange,
        "side": side,
        "btc": btc,
        "usd": usd
    }
    redis_client.lpush("liquidations", json.dumps(event))
    redis_client.ltrim("liquidations", 0, 4999)

# Broadcast formatted event
async def handle_event_broadcast_and_log(source, label, qty, price):
    total = qty * price
    emoji = "🟢" if label == "Long REKT" else "🔴"
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {emoji} {source} {label} {emoji} {qty:.4f} BTC @ ${price:,.0f} 💥 ${total:,.2f} 💥"
    await broadcast(formatted)
    await log_liquidation(source, "long" if label == "Long REKT" else "short", qty, total)

# Send to subscribers
async def broadcast(msg):
    global liquidation_count
    liquidation_count += 1
    for q in list(subscribers):
        await q.put(msg)

# Startup: run all feeds
@app.on_event("startup")
async def startup_event():
    global start_time
    start_time = datetime.utcnow()

    print("\n🚀 Starting Unified BTC Liquidations API")
    print("=" * 50)
    print(f"Starting at: {start_time}")
    print("Exchanges: Binance, HTX, OKX, Bybit, BitMEX")
    print("=" * 50)

    asyncio.create_task(handle_binance_ws("Binance", "wss://fstream.binance.com/ws/btcusdt@forceOrder"))
    asyncio.create_task(handle_bybit_ws("Bybit", "wss://stream.bybit.com/v5/public/linear"))
    asyncio.create_task(handle_okx_ws("OKX", "wss://ws.okx.com:8443/ws/v5/public"))
    asyncio.create_task(handle_htx_ws("HTX", "wss://api.hbdm.com/linear-swap-notification"))
    asyncio.create_task(handle_bitmex_ws("BitMEX", "wss://www.bitmex.com/realtime"))


# Individual WebSocket handlers

async def handle_binance_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source}")
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("e") == "forceOrder":
                        o = data.get("o", {})
                        side = o.get("S", "SELL")
                        qty = float(o.get("q", 0))
                        price = float(o.get("p", 0))
                        label = "Long REKT" if side == "SELL" else "Short REKT"
                        await handle_event_broadcast_and_log(source, label, qty, price)
        except Exception as e:
            print(f"🔁 {source} reconnect in 3s... {e}")
            await asyncio.sleep(3)

async def handle_bybit_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source}")
                await ws.send(json.dumps({"op": "subscribe", "args": ["liquidation.BTCUSDT", "liquidation.BTCPERP"]}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("topic", "").startswith("liquidation."):
                        for item in data.get("data", []):
                            side = item.get("side", "Sell").upper()
                            size = float(item.get("size", 0))
                            price = float(item.get("price", 0))
                            label = "Long REKT" if side == "SELL" else "Short REKT"
                            await handle_event_broadcast_and_log(source, label, size, price)
        except Exception as e:
            print(f"🔁 {source} reconnect in 3s... {e}")
            await asyncio.sleep(3)

async def handle_okx_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source}")
                for inst_type in ["SWAP", "FUTURES"]:
                    await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": inst_type}]}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if 'arg' in data and 'data' in data:
                        for update in data['data']:
                            inst_id = update.get("instId", "")
                            if not "BTC" in inst_id:
                                continue
                            for detail in update.get("details", []):
                                qty = float(detail.get("sz", 0))
                                price = float(detail.get("bkPx", 0))
                                pos = detail.get("posSide", "")
                                label = "Long REKT" if pos == "long" else "Short REKT"
                                await handle_event_broadcast_and_log(source, label, qty, price)
        except Exception as e:
            print(f"🔁 {source} reconnect in 3s... {e}")
            await asyncio.sleep(3)

async def handle_htx_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source}")
                await ws.send(json.dumps({"op": "sub", "cid": "btc-rekt", "topic": "public.BTC-USDT.liquidation_orders"}))
                while True:
                    raw = await ws.recv()
                    try:
                        msg = gzip.decompress(raw).decode("utf-8")
                        data = json.loads(msg)
                        if data.get("op") == "notify":
                            for item in data["data"]:
                                side = item.get("direction", "").lower()
                                qty = float(item.get("amount", 0))
                                price = float(item.get("price", 0))
                                label = "Long REKT" if side == "sell" else "Short REKT"
                                await handle_event_broadcast_and_log(source, label, qty, price)
                    except Exception as e:
                        print(f"HTX decode error: {e}")
        except Exception as e:
            print(f"🔁 {source} reconnect in 3s... {e}")
            await asyncio.sleep(3)

async def handle_bitmex_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source}")
                await ws.send(json.dumps({"op": "subscribe", "args": ["liquidation"]}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("table") == "liquidation":
                        for item in data.get("data", []):
                            symbol = item.get("symbol", "")
                            if not any(t in symbol for t in ["XBT", "BTC"]):
                                continue
                            price = float(item.get("price", 0))
                            qty = float(item.get("leavesQty", 0))
                            qty_btc = qty / price if "XBT" in symbol and price > 0 else qty
                            side = item.get("side", "Sell").upper()
                            label = "Long REKT" if side == "SELL" else "Short REKT"
                            await handle_event_broadcast_and_log(source, label, qty_btc, price)
        except Exception as e:
            print(f"🔁 {source} reconnect in 3s... {e}")
            await asyncio.sleep(3)
