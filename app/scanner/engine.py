import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.auth import validate_security_config
from app.config.settings import settings
from app.database.session import SessionLocal, init_db
from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance
from app.models.candidate_observation import SolCandidateObservation
from app.models.token import SolToken
from app.services.alerter import format_alert_message, send_sol_alert
from app.services.dexscreener import dex_service
from app.services.geckoterminal import geckoterminal_service
from app.services.jupiter import jupiter_service
from app.services.performance_tracker import update_performance_records
from app.services.rugcheck import rugcheck_service
from app.services.score_tuning import refresh_score_weight_multipliers
from app.services.scorer import compute_filter_score
from app.utils.pair_time import pair_age_hours, parse_pair_created_at

logger = logging.getLogger(__name__)

_last_scan_at: Optional[datetime] = None
_scan_count: int = 0


def get_scanner_status() -> Dict[str, Any]:
    return {
        "enabled": settings.SOL_SCANNER_ENABLED,
        "last_scan_at": _last_scan_at.isoformat() if _last_scan_at else None,
        "scan_count": _scan_count,
        "scan_interval_seconds": settings.SOL_SCAN_INTERVAL_SECONDS,
    }


def _upsert_token(db: Session, details: Dict[str, Any], source: str) -> SolToken:
    address = details["address"]
    token = db.query(SolToken).filter(SolToken.address == address).first()
    if not token:
        token = SolToken(address=address, first_seen_at=datetime.now(timezone.utc))
        db.add(token)

    token.symbol = details.get("symbol")
    token.name = details.get("name")
    token.liquidity_usd = details.get("liquidity_usd", 0)
    token.price_usd = details.get("price_usd", 0)
    token.volume_5m = details.get("volume_5m", 0)
    token.volume_1h = details.get("volume_1h", 0)
    token.volume_24h = details.get("volume_24h", 0)
    token.price_change_5m = details.get("price_change_5m", 0)
    token.price_change_1h = details.get("price_change_1h", 0)
    token.price_change_24h = details.get("price_change_24h", 0)
    token.buys_5m = details.get("buys_5m", 0)
    token.sells_5m = details.get("sells_5m", 0)
    token.buy_sell_ratio_5m = details.get("buy_sell_ratio_5m", 0)
    token.market_cap = details.get("market_cap", 0)
    token.fdv = details.get("fdv", 0)
    token.pair_address = details.get("pair_address")
    token.dex_id = details.get("dex_id")
    token.quote_token_address = details.get("quote_token_address")
    token.pair_created_at = parse_pair_created_at(details.get("pair_created_at"))
    token.token_age_hours = pair_age_hours(details.get("pair_created_at"))
    token.has_website = 1 if details.get("has_website") else 0
    token.has_twitter = 1 if details.get("has_twitter") else 0
    token.has_telegram = 1 if details.get("has_telegram") else 0
    token.website_url = details.get("website_url")
    token.twitter_url = details.get("twitter_url")
    token.telegram_url = details.get("telegram_url")
    token.last_scanned_at = datetime.now(timezone.utc)
    token.source = source
    return token


def _record_observation(
    db: Session,
    token_address: str,
    source: str,
    outcome: str,
    skip_reason: Optional[str],
    filter_score: Optional[float],
    details: Dict[str, Any],
) -> None:
    obs = SolCandidateObservation(
        token_address=token_address,
        source=source,
        outcome=outcome,
        skip_reason=skip_reason,
        filter_score=filter_score,
        liquidity_usd=details.get("liquidity_usd"),
        volume_5m=details.get("volume_5m"),
        price_change_5m=details.get("price_change_5m"),
        buy_sell_ratio_5m=details.get("buy_sell_ratio_5m"),
    )
    db.add(obs)


def _cooldown_blocks_alert(token: SolToken) -> bool:
    if token.alerted_count >= settings.SOL_MAX_ALERTS_PER_TOKEN:
        return True
    if token.last_alerted_at is None:
        return False
    cooldown = timedelta(hours=settings.SOL_COOLDOWN_HOURS)
    last = token.last_alerted_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < cooldown


def process_token(db: Session, address: str, source: str) -> None:
    details = dex_service.fetch_token_details(address)
    if not details:
        _record_observation(
            db,
            address,
            source,
            "filter_rejected",
            "dexscreener_unavailable",
            None,
            {},
        )
        return

    token = _upsert_token(db, details, source)

    rugcheck = rugcheck_service.fetch_report(address)
    token.rugcheck_score = rugcheck.score
    token.rugcheck_risk_level = rugcheck.risk_level
    token.rugcheck_flags = rugcheck.flags
    token.rugcheck_checked_at = datetime.now(timezone.utc)

    if rugcheck.unavailable:
        _record_observation(
            db,
            address,
            source,
            "rugcheck_failed",
            "rugcheck_unavailable",
            None,
            details,
        )
        db.commit()
        return

    if not rugcheck.passed:
        _record_observation(
            db,
            address,
            source,
            "rugcheck_failed",
            "rugcheck_failed",
            None,
            details,
        )
        db.commit()
        return

    result = compute_filter_score(details, rugcheck)
    if not result.passed:
        _record_observation(
            db,
            address,
            source,
            "filter_rejected",
            result.skip_reason,
            result.score,
            details,
        )
        db.commit()
        return

    jupiter = jupiter_service.validate_routable(address)
    if not jupiter.passed:
        _record_observation(
            db,
            address,
            source,
            "filter_rejected",
            jupiter.skip_reason,
            result.score,
            details,
        )
        db.commit()
        return

    if _cooldown_blocks_alert(token):
        _record_observation(
            db,
            address,
            source,
            "cooldown_suppressed",
            "cooldown_or_max_alerts",
            result.score,
            details,
        )
        db.commit()
        return

    message = format_alert_message(
        details,
        result.score,
        rugcheck.risk_level or "Unknown",
        rugcheck.score,
        source,
        no_socials=result.no_socials,
    )
    sent, msg_id = send_sol_alert(message)
    if not sent:
        _record_observation(
            db,
            address,
            source,
            "filter_rejected",
            "telegram_send_failed",
            result.score,
            details,
        )
        db.commit()
        return

    alert = SolAlert(
        token_address=address,
        source=source,
        filter_score=result.score,
        score_breakdown=result.breakdown,
        liquidity_usd=details.get("liquidity_usd", 0),
        volume_5m=details.get("volume_5m", 0),
        price_usd=details.get("price_usd", 0),
        price_change_5m=details.get("price_change_5m", 0),
        price_change_1h=details.get("price_change_1h", 0),
        price_change_24h=details.get("price_change_24h", 0),
        buy_sell_ratio_5m=details.get("buy_sell_ratio_5m", 0),
        rugcheck_risk_level=rugcheck.risk_level,
        has_website=1 if details.get("has_website") else 0,
        has_twitter=1 if details.get("has_twitter") else 0,
        has_telegram=1 if details.get("has_telegram") else 0,
        website_url=details.get("website_url"),
        twitter_url=details.get("twitter_url"),
        telegram_url=details.get("telegram_url"),
        telegram_message_id=msg_id,
    )
    db.add(alert)
    db.flush()

    perf = SolAlertPerformance(
        alert_id=alert.id,
        token_address=address,
        price_at_alert=float(details.get("price_usd") or 0),
    )
    db.add(perf)

    token.alerted_count = (token.alerted_count or 0) + 1
    token.last_alerted_at = datetime.now(timezone.utc)

    _record_observation(
        db,
        address,
        source,
        "alerted",
        None,
        result.score,
        details,
    )
    db.commit()
    logger.info("Alert sent for %s (score=%.0f)", details.get("symbol"), result.score)


def run_scan_cycle(db: Session) -> int:
    global _last_scan_at, _scan_count

    try:
        refresh_score_weight_multipliers(db)
    except Exception as exc:
        logger.exception("Score tuning refresh error: %s", exc)

    candidates = geckoterminal_service.discover()
    logger.info("Scan cycle: %s candidates from GeckoTerminal", len(candidates))

    for address, source in candidates.items():
        try:
            process_token(db, address, source)
        except Exception as exc:
            db.rollback()
            logger.exception("Error processing %s: %s", address, exc)

    try:
        update_performance_records(db)
    except Exception as exc:
        logger.exception("Performance tracker error: %s", exc)

    _last_scan_at = datetime.now(timezone.utc)
    _scan_count += 1
    return len(candidates)


def run_standalone_loop(interval_seconds: Optional[int] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()
    validate_security_config()

    if not settings.SOL_SCANNER_ENABLED:
        logger.warning("SOL_SCANNER_ENABLED=false — scanner idle")
        while True:
            time.sleep(60)

    interval = interval_seconds or settings.SOL_SCAN_INTERVAL_SECONDS
    logger.info("Solana scanner started (interval=%ss)", interval)

    while True:
        db = SessionLocal()
        try:
            run_scan_cycle(db)
        except Exception as exc:
            logger.exception("Scan cycle failed: %s", exc)
            db.rollback()
        finally:
            db.close()
        time.sleep(interval)
