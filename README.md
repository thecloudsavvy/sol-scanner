# Solana Meme Coin Scanner

Production-grade Solana meme coin scanner MVP — discovery, Rugcheck safety gating, filter scoring, Telegram alerts, and a FastAPI dashboard. **No live trading** in this version.

Standalone codebase; independent from the Base chain scanner.

## Features

- **Discovery**: GeckoTerminal new + trending Solana pools (60s poll)
- **Enrichment**: DexScreener (price, liquidity, volume, socials)
- **Safety**: Rugcheck.xyz hard gate with 10-minute cache
- **Scoring**: 0–100 filter score; alerts at ≥ 60
- **Alerts**: Telegram (🟢 SOL prefix)
- **Dashboard**: FastAPI + Jinja2 on port **8001**
- **Performance tracking**: 15m / 1h / 4h / 24h post-alert returns

## Quick start

```bash
cd sol-scanner
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp deploy/env.example .env
# Edit .env: TELEGRAM_*, DASHBOARD_*

pytest
python run_api.py      # http://localhost:8001
python run_scanner.py  # separate terminal
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SOL_SCANNER_ENABLED` | `true` | Enable scanner loop |
| `SOL_SCAN_INTERVAL_SECONDS` | `60` | Poll interval |
| `SOL_MIN_LIQUIDITY_USD` | `100000` | Hard gate |
| `SOL_MIN_VOLUME_5M` | `5000` | Hard gate |
| `SOL_MIN_BUY_SELL_RATIO` | `1.0` | Hard gate |
| `SOL_MAX_TOKEN_AGE_HOURS` | `72` | Hard gate |
| `SOL_ALERT_SCORE_THRESHOLD` | `60` | Min score to alert |
| `SOL_COOLDOWN_HOURS` | `4` | Between alerts per token |
| `SOL_MAX_ALERTS_PER_TOKEN` | `2` | Lifetime cap |
| `DATABASE_URL` | `sqlite:///./sol_scanner.db` | SQLite or PostgreSQL URL |
| `TELEGRAM_BOT_TOKEN` | — | Shared bot with Base scanner |
| `TELEGRAM_CHAT_ID` | — | Alert destination |
| `RUGCHECK_CACHE_TTL_SECONDS` | `600` | Rugcheck cache |
| `DASHBOARD_USERNAME` | — | Required when scanner enabled |
| `DASHBOARD_PASSWORD` | — | Required when scanner enabled |
| `API_PORT` | `8001` | Dashboard port |

## Filter score breakdown

| Signal | Max pts |
|--------|---------|
| Liquidity depth ($100k–$1M+) | 20 |
| Volume 5m momentum | 20 |
| Price action (early accumulation) | 20 |
| Buy/sell pressure 5m | 15 |
| Social presence (website/X/Telegram) | 15 |
| Rugcheck quality bonus | 10 |

Penalties: +30% in 5m (−10), −30% in 1h (−10).

## Azure deployment

1. Copy repo to `/opt/sol-scanner`
2. Create user: `sudo useradd -r -m solscanner`
3. Data dir: `sudo mkdir -p /var/lib/sol-scanner && sudo chown solscanner:solscanner /var/lib/sol-scanner`
4. Env: `sudo cp deploy/env.example /etc/sol-scanner/env && sudo chmod 600 /etc/sol-scanner/env`
5. Venv + deps: `sudo -u solscanner python3.11 -m venv /opt/sol-scanner/venv && sudo -u solscanner /opt/sol-scanner/venv/bin/pip install -r /opt/sol-scanner/requirements-prod.txt`
6. Install units:
   ```bash
   sudo cp deploy/sol-scanner.service deploy/sol-scanner-api.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now sol-scanner sol-scanner-api
   ```
7. Open port 8001 if needed; Base scanner stays on 8000.

## Tests

```bash
pytest -v
```

## Known limitations (v2 roadmap)

- No live trading / swaps
- No on-chain holder distribution (RPC)
- Social presence only — no engagement APIs
- No OHLCV technical analysis
- No smart-money wallet tracking
