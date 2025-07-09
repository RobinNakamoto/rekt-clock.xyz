import asyncio
import json
import gzip
from datetime import datetime
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import websockets

app = FastAPI()

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Block common bot paths
@app.middleware("http")
async def block_bots(request, call_next):
    bot_paths = [
        "/wp-admin", "/wordpress", "/wp-includes", 
        "/wp-content", "/xmlrpc.php", ".xml",
        "/phpmyadmin", "/.env", "/config.php"
    ]
    
    path = request.url.path.lower()
    if any(bot_path in path for bot_path in bot_paths):
        return Response(status_code=404)
    
    response = await call_next(request)
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html on root
@app.get("/")
def root():
    return FileResponse("static/index.html")

subscribers = set()

# Exchange configurations
BINANCE_PAIRS = [
    ("Binance", "wss://fstream.binance.com/ws/btcusdt@forceOrder"),
    ("Binance", "wss://fstream.binance.com/ws/btcusdc@forceOrder")
]
HTX_WS = ("HTX", "wss://api.hbdm.com/linear-swap-notification")
OKX_FEED = ("OKX", "wss://ws.okx.com:8443/ws/v5/public")
BYBIT_FEED = ("Bybit", "wss://stream.bybit.com/v5/public/linear")
BITMEX_FEED = ("BitMEX", "wss://www.bitmex.com/realtime")

def get_timestamp():
    return datetime.now().strftime('%H:%M:%S')

async def broadcast(msg):
    for q in list(subscribers):
        await q.put(msg)

# BINANCE Handler
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
                        total = qty * price
                        
                        emoji = "🟢" if side == "SELL" else "🔴"
                        label = "Long REKT" if side == "SELL" else "Short REKT"
                        
                        formatted = f"[{get_timestamp()}] {emoji} {source} {label} {emoji} {qty:.4f} BTC @ ${price:,.0f} 💥 ${total:,.2f} 💥"
                        await broadcast(formatted)
                        
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

# HTX Handler
async def handle_htx_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                
                # Subscribe to BTC liquidations
                await ws.send(json.dumps({
                    "op": "sub",
                    "cid": "btc-rekt",
                    "topic": "public.BTC-USDT.liquidation_orders"
                }))
                
                while True:
                    msg = await ws.recv()
                    try:
                        # HTX sends gzipped messages
                        decompressed = gzip.decompress(msg).decode("utf-8")
                        data = json.loads(decompressed)
                        
                        # Handle ping/pong
                        if data.get("op") == "ping":
                            await ws.send(json.dumps({"op": "pong", "ts": data["ts"]}))
                            continue
                            
                        # Handle liquidations
                        if data.get("op") == "notify" and "data" in data:
                            for item in data["data"]:
                                if not item.get("contract_code", "").startswith("BTC"):
                                    continue
                                    
                                side = item.get("direction", "").lower()
                                qty = float(item.get("amount", 0))  # Use amount, not volume
                                price = float(item.get("price", 0))
                                total = qty * price
                                
                                emoji = "🟢" if side == "sell" else "🔴"
                                label = "Long REKT" if side == "sell" else "Short REKT"
                                
                                formatted = f"[{get_timestamp()}] {emoji} {source} {label} {emoji} {qty:.4f} BTC @ ${price:,.0f} 💥 ${total:,.2f} 💥"
                                await broadcast(formatted)
                                
                    except Exception as e:
                        print(f"HTX decode error: {e}")
                        
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

# BYBIT Handler
async def handle_bybit_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                
                # Subscribe to BTC liquidations
                await ws.send(json.dumps({
                    "op": "subscribe",
                    "args": ["liquidation.BTCUSDT", "liquidation.BTCPERP"]
                }))
                
                # Send initial ping
                await ws.send(json.dumps({"op": "ping"}))
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    # Handle pong
                    if data.get("ret_msg") == "pong":
                        await asyncio.sleep(20)
                        await ws.send(json.dumps({"op": "ping"}))
                        continue
                        
                    # Handle liquidations
                    if data.get("topic", "").startswith("liquidation."):
                        for item in data.get("data", []):
                            side = item.get("side", "Sell").upper()
                            size = float(item.get("size", 0))  # Changed from qty
                            price = float(item.get("price", 0))
                            total = size * price
                            
                            emoji = "🟢" if side == "SELL" else "🔴"
                            label = "Long REKT" if side == "SELL" else "Short REKT"
                            
                            formatted = f"[{get_timestamp()}] {emoji} {source} {label} {emoji} {size:.4f} BTC @ ${price:,.0f} 💥 ${total:,.2f} 💥"
                            await broadcast(formatted)
                            
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

# BITMEX Handler
async def handle_bitmex_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                
                # Subscribe to liquidations
                await ws.send(json.dumps({
                    "op": "subscribe",
                    "args": ["liquidation"]
                }))
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if data.get("table") == "liquidation" and "data" in data:
                        for item in data["data"]:
                            symbol = item.get("symbol", "")
                            
                            # Filter for BTC only
                            if not any(btc in symbol for btc in ["XBT", "BTC"]):
                                continue
                                
                            side = item.get("side", "Sell").upper()
                            price = float(item.get("price", 0))
                            qty = float(item.get("leavesQty", 0))
                            
                            # Handle XBT contracts
                            if "XBT" in symbol:
                                total = qty
                                qty_btc = qty / price if price > 0 else 0
                            else:
                                total = qty * price
                                qty_btc = qty
                                
                            emoji = "🟢" if side == "SELL" else "🔴"
                            label = "Long REKT" if side == "SELL" else "Short REKT"
                            
                            formatted = f"[{get_timestamp()}] {emoji} {source} {label} {emoji} {qty_btc:.4f} BTC @ ${price:,.0f} 💥 ${total:,.2f} 💥"
                            await broadcast(formatted)
                            
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

# OKX Handler
async def handle_okx_ws(source, uri):
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                print(f"✅ Connected to {source} @ {uri}")
                
                # Subscribe to liquidations
                for inst_type in ["SWAP", "FUTURES", "MARGIN"]:
                    sub_msg = {
                        "op": "subscribe",
                        "args": [{
                            "channel": "liquidation-orders",
                            "instType": inst_type
                        }]
                    }
                    await ws.send(json.dumps(sub_msg))
                
                while True:
                    msg = await ws.recv()
                    try:
                        data = json.loads(msg)
                        
                        if 'arg' in data and 'data' in data:
                            for update in data['data']:
                                # Filter for BTC only
                                inst_family = update.get("instFamily", "")
                                inst_id = update.get("instId", "")
                                
                                if not ("BTC" in inst_family or "BTC" in inst_id):
                                    continue
                                    
                                for detail in update.get("details", []):
                                    sz = float(detail.get("sz", 0))
                                    px = float(detail.get("bkPx", 0))
                                    pos = detail.get("posSide", "")
                                    liq_value = sz * px
                                    
                                    emoji = "🟢" if pos == "long" else "🔴"
                                    label = "Long REKT" if pos == "long" else "Short REKT"
                                    
                                    formatted = f"[{get_timestamp()}] {emoji} {source} {label} {emoji} {sz:.4f} BTC @ ${px:,.0f} 💥 ${liq_value:,.2f} 💥"
                                    await broadcast(formatted)
                                    
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            print(f"🔁 {source} reconnecting in 3s... Error: {e}")
            await asyncio.sleep(3)

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
    print("🚀 Starting Unified BTC Liquidations API")
    print("=" * 50)
    
    # Start Binance handlers
    for source, uri in BINANCE_PAIRS:
        asyncio.create_task(handle_binance_ws(source, uri))
    
    # Start other exchange handlers
    asyncio.create_task(handle_htx_ws(*HTX_WS))
    asyncio.create_task(handle_bybit_ws(*BYBIT_FEED))
    asyncio.create_task(handle_bitmex_ws(*BITMEX_FEED))
    asyncio.create_task(handle_okx_ws(*OKX_FEED))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
