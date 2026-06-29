from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from app.config.settings import settings
from app.services.rugcheck import RugcheckResult
from app.services.score_tuning import apply_weighted_total
from app.utils.pair_time import pair_age_hours


@dataclass
class FilterResult:
    passed: bool
    skip_reason: Optional[str] = None
    score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    no_socials: bool = False


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
        age_hours = pair_age_hours(details.get("pair_created_at"))
    if age_hours is None or age_hours > settings.SOL_MAX_TOKEN_AGE_HOURS:
        return False, "token_too_old"

    volume_5m = float(details.get("volume_5m") or 0)
    if volume_5m < settings.SOL_MIN_VOLUME_5M:
        return False, "volume_5m_below_min"

    ratio_5m = float(details.get("buy_sell_ratio_5m") or 0)
    if ratio_5m < settings.SOL_MIN_BUY_SELL_RATIO:
        return False, "buy_sell_ratio_below_min"

    ratio_1h = float(details.get("buy_sell_ratio_1h") or 0)
    if ratio_1h < settings.SOL_MIN_BUY_SELL_RATIO_1H:
        return False, "buy_sell_ratio_1h_below_min"

    sells_5m = int(details.get("sells_5m") or 0)
    if sells_5m < settings.SOL_MIN_SELLS_5M:
        return False, "min_sells_5m_below_min"

    fdv = float(details.get("fdv") or 0)
    if fdv > settings.SOL_MAX_FDV_USD:
        return False, "fdv_above_max"

    if liquidity > 0 and fdv > 0:
        fdv_liq_ratio = fdv / liquidity
        if fdv_liq_ratio > settings.SOL_MAX_FDV_LIQUIDITY_RATIO:
            return False, "fdv_liquidity_ratio_above_max"

    vol_liq_ratio = float(details.get("volume_liquidity_ratio_5m") or 0)
    if vol_liq_ratio > settings.SOL_MAX_VOLUME_LIQUIDITY_RATIO:
        return False, "volume_liquidity_ratio_above_max"

    liq_share = float(details.get("primary_liquidity_share") or 1.0)
    pair_count = int(details.get("solana_pair_count") or 1)
    if pair_count > 1 and liq_share < settings.SOL_MIN_PRIMARY_LIQUIDITY_SHARE:
        return False, "liquidity_too_fragmented"

    if details.get("chain") and details.get("chain") != "solana":
        return False, "wrong_chain"

    return True, None


def score_liquidity_depth(liquidity_usd: float) -> float:
    if liquidity_usd > 1_000_000:
        return 20.0
    if liquidity_usd >= 500_000:
        return 15.0
    if liquidity_usd >= 300_000:
        return 10.0
    if liquidity_usd >= 200_000:
        return 5.0
    return 0.0


def score_volume_momentum(volume_5m: float) -> float:
    if volume_5m >= 100_000:
        return 20.0
    if volume_5m >= 50_000:
        return 15.0
    if volume_5m >= 30_000:
        return 10.0
    if volume_5m >= 15_000:
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


def score_buy_sell_pressure(ratio_5m: float, ratio_1h: float) -> float:
    points = 0.0
    if ratio_5m >= 3.0:
        points += 10.0
    elif ratio_5m >= 2.0:
        points += 7.0
    elif ratio_5m >= 1.5:
        points += 4.0

    if ratio_1h >= 2.0:
        points += 5.0
    elif ratio_1h >= 1.5:
        points += 3.0
    elif ratio_1h >= 1.2:
        points += 1.0

    return min(15.0, points)


def score_community(details: Dict[str, Any]) -> Tuple[float, bool]:
    points = 0.0
    if details.get("has_website"):
        points += 3.0
    if details.get("has_twitter"):
        points += 3.0
    if details.get("has_telegram"):
        points += 3.0
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


def _check_category_minimums(breakdown: Dict[str, float]) -> Optional[str]:
    volume_pts = breakdown.get("volume_momentum", 0.0)
    if volume_pts < settings.SOL_MIN_VOLUME_SCORE:
        return "volume_score_below_min"

    momentum_pts = breakdown.get("price_action", 0.0) + breakdown.get("buy_sell_pressure", 0.0)
    if momentum_pts < settings.SOL_MIN_MOMENTUM_SCORE:
        return "momentum_score_below_min"

    return None


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

    bs_pts = score_buy_sell_pressure(
        float(details.get("buy_sell_ratio_5m") or 0),
        float(details.get("buy_sell_ratio_1h") or 0),
    )
    breakdown["buy_sell_pressure"] = bs_pts

    comm_pts, no_socials = score_community(details)
    breakdown["community"] = comm_pts

    rug_pts = score_rugcheck_bonus(rugcheck)
    breakdown["rugcheck_bonus"] = rug_pts

    category_reason = _check_category_minimums(breakdown)
    if category_reason:
        raw_total = sum(
            breakdown.get(key, 0.0)
            for key in (
                "liquidity_depth",
                "volume_momentum",
                "price_action",
                "buy_sell_pressure",
                "community",
                "rugcheck_bonus",
            )
        )
        return FilterResult(
            passed=False,
            skip_reason=category_reason,
            score=max(0.0, min(100.0, raw_total)),
            breakdown=breakdown,
            no_socials=no_socials,
        )

    total = apply_weighted_total(breakdown)

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
