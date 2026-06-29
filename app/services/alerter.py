import logging
from typing import Any, Dict, Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


def format_usd(val: float) -> str:
    if val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"${val / 1_000:.1f}K"
    return f"${val:.4f}"


def format_alert_message(
    details: Dict[str, Any],
    filter_score: float,
    rugcheck_risk_level: str,
    rugcheck_score: Optional[float],
    source: str,
    no_socials: bool = False,
) -> str:
    symbol = details.get("symbol") or "UNKNOWN"
    price = float(details.get("price_usd") or 0)
    liquidity = float(details.get("liquidity_usd") or 0)
    vol5m = float(details.get("volume_5m") or 0)
    pct5m = float(details.get("price_change_5m") or 0)
    pct1h = float(details.get("price_change_1h") or 0)
    pct24h = float(details.get("price_change_24h") or 0)
    ratio = float(details.get("buy_sell_ratio_5m") or 0)
    age_hours = details.get("token_age_hours")
    address = details.get("address") or ""

    website = details.get("website_url") or "No website"
    twitter = details.get("twitter_url") or "No Twitter"
    telegram = details.get("telegram_url") or "No Telegram"

    dex_url = f"https://dexscreener.com/solana/{address}"
    rug_url = f"https://rugcheck.xyz/tokens/{address}"
    score_display = f"{rugcheck_score:.0f}" if rugcheck_score is not None else "N/A"
    age_line = f"{age_hours:.1f}h" if age_hours is not None else "unknown"

    social_flag = "\n⚠️ No socials on DexScreener" if no_socials else ""

    return (
        f"🟢 SOL ALERT — {symbol}\n\n"
        f"💰 Price: {format_usd(price)}\n"
        f"📊 Liq: {format_usd(liquidity)} | Vol 5m: {format_usd(vol5m)}\n"
        f"📈 5m: {pct5m:+.1f}% | 1h: {pct1h:+.1f}% | 24h: {pct24h:+.1f}%\n"
        f"🔄 B/S (5m): {ratio:.2f}\n"
        f"🛡 Rugcheck: {rugcheck_risk_level} ({score_display})\n"
        f"⭐ Filter Score: {filter_score:.0f}/100\n"
        f"{social_flag}\n\n"
        f"🌐 {website}\n"
        f"🐦 {twitter}\n"
        f"💬 {telegram}\n\n"
        f"📍 {dex_url}\n"
        f"🔍 {rug_url}\n\n"
        f"Source: {source} | Age: {age_line}"
    )


def send_sol_alert(message: str) -> tuple[bool, Optional[str]]:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.info("--- TELEGRAM ALERT SIMULATION ---\n%s\n---", message)
        return True, None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": False,
    }
    try:
        response = httpx.post(url, json=payload, timeout=15.0)
        if response.status_code == 200:
            data = response.json()
            msg_id = str(data.get("result", {}).get("message_id", ""))
            return True, msg_id or None
        logger.error("Telegram API error: %s", response.text)
        return False, None
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False, None
