# rekt-clock.xyz

**Live Bitcoin Liquidation Feed** built for terminal freaks, degen traders, and anyone who wants to watch the market burn. No frontend frameworks, no distractions — just green and red rekt streams.

> Live: [rekt-clock.xyz](https://rekt-clock.xyz)

---

## ⚠️ Note (July 2025)
> Currently Bybit WebSocket integration is not working. Will be fixed soon.

---

## Features

- 💥 Real-time BTC liquidation stream (from Binance, OKX, HTX, BitMEX)
- 🧠 Memory + Redis-backed event logging (Upstash)
- 📊 24h / 12h / 4h / 1h summary logic
- 🔊 Audio alerts on REKT events
- ⌨️ Terminal-style HTML UI
- 🛠️ Fully self-hostable

---

## Demo

[rekt-clock.xyz](https://rekt-clock.xyz)

---

## Stack

- Backend: [FastAPI](https://fastapi.tiangolo.com/) (Python)
- Hosting: [Railway](https://railway.com?referralCode=-FAcZY) 
- Storage: [Upstash Redis](https://upstash.com)
- Frontend: Static HTML served via FastAPI

---

## Getting Started (Fork Required)

> You MUST fork this repo to deploy your own instance.

1. **Fork the repo**
   - Click "Fork" in the top right of [RobinNakamoto/rekt-clock.xyz](https://github.com/RobinNakamoto/rekt-clock.xyz)

2. **Create Upstash Redis DB**
   - Go to [Upstash](https://console.upstash.com/) and create a free Redis DB
   - Save the **connection string** (e.g. `rediss://default:XXXX@hostname:port`)

3. **Deploy to Railway**
   - Please use this referral link 😇: [https://railway.com?referralCode=-FAcZY](https://railway.com?referralCode=-FAcZY)
   - Connect your forked GitHub repo
   - Set environment variable:
     - `REDIS_URL=your-upstash-url`

4. **Done**
   - Your site will deploy to `https://your-project.up.railway.app`

---

## Environment Variables

| Name       | Description                              |
|------------|------------------------------------------|
| REDIS_URL  | Redis connection string from Upstash     |

---

## Google Analytics

This project includes a [Google Analytics](https://analytics.google.com/) tag owned by [@RobinNakamoto](https://twitter.com/RobinNakamoto).  
It is set up to **only run on the official domain `rekt-clock.xyz`**.

If you fork or self-host this project, please **remove or replace the GA tag** in `index.html` to avoid sending traffic to my analytics.

---

## License

This project is licensed under the **GNU General Public License v3.0**.

See [LICENSE](LICENSE) for details.

---

## Contributing

PRs welcome. Fork it, build something cool, make it for plebs.

Made by [@RobinNakamoto](https://twitter.com/RobinNakamoto)
