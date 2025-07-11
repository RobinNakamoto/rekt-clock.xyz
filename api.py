import asyncio
import json
import gzip
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import websockets
import redis

app = FastAPI()

# Redis client
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "exchanges": 5}

@app.get("/stats")
def stats():
    uptime = (datetime.now() - start_time).total_seconds() if start_time else 0
    return {
        "uptime_seconds": uptime,
        "active_connections": len(subscribers),
        "total_liquidations": liquidation_count
    }

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
            by_exchange = {}
            for e in events:
                if e["side"] != side:
                    continue
                if datetime.fromisoformat(e["timestamp"]) < threshold:
                    continue

                ex = e["exchange"]
                by_exchange.setdefault(ex, {"btc": 0, "usd": 0})
                by_exchange[ex]["btc"] += e["btc"]
                by_exchange[ex]["usd"] += e["usd"]

            total_btc = sum(v["btc"] for v in by_exchange.values())
            total_usd = sum(v["usd"] for v in by_exchange.values())

            summary[side][tf] = {
                "by_exchange": by_exchange,
                "total_btc": total_btc,
                "total_usd": total_usd
            }

        total_btc = summary["long"][tf]["total_btc"] + summary["short"][tf]["total_btc"]
        total_usd = summary["long"][tf]["total_usd"] + summary["short"][tf]["total_usd"]
        summary["total"][tf] = {
            "total_btc": total_btc,
            "total_usd": total_usd
        }

    out = ["Recent BTC liquidations:"]
    for side in ["long", "short"]:
        out.append(side.upper() + "S:")
        for ex in summary[side]["24h"]["by_exchange"]:
            out.append(f"{ex}:")
            for tf in ["24h", "12h", "4h", "1h"]:
                data = summary[side].get(tf, {}).get("by_exchange", {}).get(ex, {"btc": 0, "usd": 0})
                out.append(f"  {tf}: {data['btc']:.2f} BTC / ${data['usd']:,.0f}")
        out.append("")
        for tf in ["24h", "12h", "4h", "1h"]:
            data = summary[side].get(tf, {})
            out.append(f"Total {side} REKT {tf}: {data.get('total_btc', 0):.2f} BTC / ${data.get('total_usd', 0):,.0f}")
        out.append("")

    out.append("Total REKT (long + short):")
    for tf in ["24h", "12h", "4h", "1h"]:
        data = summary["total"].get(tf, {})
        out.append(f"  {tf}: {data.get('total_btc', 0):.2f} BTC / ${data.get('total_usd', 0):,.0f}")

    return PlainTextResponse("\n".join(out))

subscribers = set()
liquidation_count = 0
start_time = None

# Helper to log to Redis
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

async def handle_event_broadcast_and_log(source, label, qty, price):
    total = qty * price
    emoji = "🟢" if label == "Long REKT" else "🔴"
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {emoji} {source} {label} {emoji} {qty:.4f} BTC @ ${price:,.0f} 💥 ${total:,.2f} 💥"
    await broadcast(formatted)
    await log_liquidation(source, "long" if label == "Long REKT" else "short", qty, total)

@app.on_event("startup")
async def startup_event():

    global start_time
    start_time = datetime.now()
    print("🚀 Rekt Clock API Booted")
    print("Up and running...")
    print("Ready to receive events ✅")

    # Start exchange feeds
    asyncio.create_task(handle_binance_ws("Binance", "wss://fstream.binance.com/ws/btcusdt@forceOrder"))
    asyncio.create_task(handle_bybit_ws("Bybit", "wss://stream.bybit.com/v5/public/linear"))
    asyncio.create_task(handle_okx_ws("OKX", "wss://ws.okx.com:8443/ws/v5/public"))
    asyncio.create_task(handle_htx_ws("HTX", "wss://api.hbdm.com/linear-swap-notification"))
    asyncio.create_task(handle_bitmex_ws("BitMEX", "wss://www.bitmex.com/realtime"))


# Broadcast
async def broadcast(msg):
    global liquidation_count
    liquidation_count += 1
    for q in list(subscribers):
        await q.put(msg)

# Exchange Handlers

async def handle_binance_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
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
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

async def handle_bybit_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                await ws.send(json.dumps({"op": "subscribe", "args": ["liquidation.BTCUSDT", "liquidation.BTCPERP"]}))
                await ws.send(json.dumps({"op": "ping"}))
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
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

async def handle_okx_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                for inst_type in ["SWAP", "FUTURES", "MARGIN"]:
                    await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": inst_type}]}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if 'arg' in data and 'data' in data:
                        for update in data['data']:
                            inst_family = update.get("instFamily", "")
                            inst_id = update.get("instId", "")
                            if not ("BTC" in inst_family or "BTC" in inst_id):
                                continue
                            for detail in update.get("details", []):
                                sz = float(detail.get("sz", 0))
                                px = float(detail.get("bkPx", 0))
                                pos = detail.get("posSide", "")
                                label = "Long REKT" if pos == "long" else "Short REKT"
                                await handle_event_broadcast_and_log(source, label, sz, px)
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

async def handle_htx_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                await ws.send(json.dumps({"op": "sub", "cid": "btc-rekt", "topic": "public.BTC-USDT.liquidation_orders"}))
                while True:
                    raw = await ws.recv()
                    try:
                        msg = gzip.decompress(raw).decode("utf-8")
                        data = json.loads(msg)
                        if data.get("op") == "notify" and "data" in data:
                            for item in data["data"]:
                                if not item.get("contract_code", "").startswith("BTC"):
                                    continue
                                side = item.get("direction", "").lower()
                                qty = float(item.get("amount", 0))
                                price = float(item.get("price", 0))
                                label = "Long REKT" if side == "sell" else "Short REKT"
                                await handle_event_broadcast_and_log(source, label, qty, price)
                    except Exception as e:
                        print(f"HTX decode error: {e}")
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

async def handle_bitmex_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                await ws.send(json.dumps({"op": "subscribe", "args": ["liquidation"]}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("table") == "liquidation" and "data" in data:
                        for item in data["data"]:
                            symbol = item.get("symbol", "")
                            if not any(btc in symbol for btc in ["XBT", "BTC"]):
                                continue
                            side = item.get("side", "Sell").upper()
                            price = float(item.get("price", 0))
                            qty = float(item.get("leavesQty", 0))
                            qty_btc = qty / price if "XBT" in symbol and price > 0 else qty
                            label = "Long REKT" if side == "SELL" else "Short REKT"
                            await handle_event_broadcast_and_log(source, label, qty_btc, price)
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)
