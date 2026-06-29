from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.config.settings import settings
from app.services.rugcheck import RugcheckResult


@dataclass
class FilterResult:
    passed: bool
    skip_reason: Optional[str] = None
    score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    no_socials: bool = False


def _pair_age_hours(pair_created_at: Any) -> Optional[float]:
    if pair_created_at is None:
        return None
    if isinstance(pair_created_at, (int, float)):
        created = datetime.fromtimestamp(pair_created_at / 1000, tz=timezone.utc)
    elif isinstance(pair_created_at, datetime):
        created = pair_created_at if pair_created_at.tzinfo else pair_created_at.replace(tzinfo=timezone.utc)
    else:
        return None
    delta = datetime.now(timezone.utc) - created
    return delta.total_seconds() / 3600.0


def check_hard_gates(
    details: Dict[str, Any],
    rugcheck: RugcheckResult,
) -> Tuple[bool, Optional[str]]:
    if rugcheck.unavailable:
        return False, "rugcheck_unavailable"
    if not rugcheck.passed:
        return False, "rugcheck_failed"

    liquidity = float(details.get("liquidity_usd") or 0)
    if liquidity < settings.SOL_MIN_LIQUIDITY_USD:
        return False, "liquidity_below_min"

    age_hours = details.get("token_age_hours")
    if age_hours is None:
        age_hours = _pair_age_hours(details.get("pair_created_at"))
    if age_hours is None or age_hours > settings.SOL_MAX_TOKEN_AGE_HOURS:
        return False, "token_too_old"

    volume_5m = float(details.get("volume_5m") or 0)
    if volume_5m < settings.SOL_MIN_VOLUME_5M:
        return False, "volume_5m_below_min"

    ratio = float(details.get("buy_sell_ratio_5m") or 0)
    if ratio < settings.SOL_MIN_BUY_SELL_RATIO:
        return False, "buy_sell_ratio_below_min"

    if details.get("chain") and details.get("chain") != "solana":
        return False, "wrong_chain"

    return True, None


def score_liquidity_depth(liquidity_usd: float) -> float:
    if liquidity_usd > 1_000_000:
        return 20.0
    if liquidity_usd >= 500_000:
        return 15.0
    if liquidity_usd >= 200_000:
        return 10.0
    if liquidity_usd >= 100_000:
        return 5.0
    return 0.0


def score_volume_momentum(volume_5m: float) -> float:
    if volume_5m >= 100_000:
        return 20.0
    if volume_5m >= 50_000:
        return 15.0
    if volume_5m >= 25_000:
        return 10.0
    if volume_5m >= 10_000:
        return 5.0
    return 0.0


def score_price_action(
    price_change_5m: float,
    price_change_1h: float,
    price_change_24h: float,
) -> Tuple[float, Dict[str, float]]:
    points = 0.0
    breakdown: Dict[str, float] = {}

    if 0 <= price_change_5m <= 15:
        points += 10.0
        breakdown["price_5m_range"] = 10.0
    if -20 <= price_change_1h <= 50:
        points += 5.0
        breakdown["price_1h_range"] = 5.0
    if price_change_24h <= 200:
        points += 5.0
        breakdown["price_24h_cap"] = 5.0

    if price_change_5m > 30:
        points -= 10.0
        breakdown["pumped_5m_penalty"] = -10.0
    if price_change_1h < -30:
        points -= 10.0
        breakdown["dump_1h_penalty"] = -10.0

    return max(0.0, points), breakdown


def score_buy_sell_pressure(ratio: float) -> float:
    if ratio >= 3.0:
        return 15.0
    if ratio >= 2.0:
        return 10.0
    if ratio >= 1.5:
        return 5.0
    return 0.0


def score_community(details: Dict[str, Any]) -> Tuple[float, bool]:
    points = 0.0
    if details.get("has_website"):
        points += 5.0
    if details.get("has_twitter"):
        points += 5.0
    if details.get("has_telegram"):
        points += 5.0
    no_socials = not (
        details.get("has_website") or details.get("has_twitter") or details.get("has_telegram")
    )
    return points, no_socials


def score_rugcheck_bonus(rugcheck: RugcheckResult) -> float:
    if not rugcheck.passed:
        return 0.0
    level = (rugcheck.risk_level or "").lower()
    if level == "good":
        if rugcheck.warning_count == 0:
            return 10.0
        if rugcheck.warning_count <= 2:
            return 5.0
    return 0.0


def compute_filter_score(
    details: Dict[str, Any],
    rugcheck: RugcheckResult,
) -> FilterResult:
    passed, skip_reason = check_hard_gates(details, rugcheck)
    if not passed:
        return FilterResult(passed=False, skip_reason=skip_reason, score=0.0)

    breakdown: Dict[str, float] = {}

    liq_pts = score_liquidity_depth(float(details.get("liquidity_usd") or 0))
    breakdown["liquidity_depth"] = liq_pts

    vol_pts = score_volume_momentum(float(details.get("volume_5m") or 0))
    breakdown["volume_momentum"] = vol_pts

    price_pts, price_bd = score_price_action(
        float(details.get("price_change_5m") or 0),
        float(details.get("price_change_1h") or 0),
        float(details.get("price_change_24h") or 0),
    )
    breakdown.update(price_bd)
    breakdown["price_action"] = price_pts

    bs_pts = score_buy_sell_pressure(float(details.get("buy_sell_ratio_5m") or 0))
    breakdown["buy_sell_pressure"] = bs_pts

    comm_pts, no_socials = score_community(details)
    breakdown["community"] = comm_pts

    rug_pts = score_rugcheck_bonus(rugcheck)
    breakdown["rugcheck_bonus"] = rug_pts

    total = liq_pts + vol_pts + price_pts + bs_pts + comm_pts + rug_pts
    total = max(0.0, min(100.0, total))

    if total < settings.SOL_ALERT_SCORE_THRESHOLD:
        return FilterResult(
            passed=False,
            skip_reason="score_below_threshold",
            score=total,
            breakdown=breakdown,
            no_socials=no_socials,
        )

    return FilterResult(
        passed=True,
        score=total,
        breakdown=breakdown,
        no_socials=no_socials,
    )
