import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from app.services.rugcheck import RugcheckResult


def base_details(**overrides):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    data = {
        "chain": "solana",
        "address": "So11111111111111111111111111111111111111112",
        "symbol": "TEST",
        "liquidity_usd": 1_500_000,
        "volume_5m": 120_000,
        "price_change_5m": 8.0,
        "price_change_1h": 15.0,
        "price_change_24h": 80.0,
        "buy_sell_ratio_5m": 3.5,
        "pair_created_at": now_ms - 12 * 3600 * 1000,
        "has_website": True,
        "has_twitter": True,
        "has_telegram": True,
    }
    data.update(overrides)
    return data


def good_rugcheck(**overrides):
    rc = RugcheckResult(
        passed=True,
        score=90.0,
        risk_level="Good",
        flags=[],
        warning_count=0,
    )
    for k, v in overrides.items():
        setattr(rc, k, v)
    return rc
