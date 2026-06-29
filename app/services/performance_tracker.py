import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance
from app.services.dexscreener import dex_service

logger = logging.getLogger(__name__)

INTERVAL_SCHEDULE = [
    (timedelta(minutes=15), "price_15m", "return_15m"),
    (timedelta(hours=1), "price_1h", "return_1h"),
    (timedelta(hours=4), "price_4h", "return_4h"),
    (timedelta(hours=24), "price_24h", "return_24h"),
]


def _next_due_interval(
    perf: SolAlertPerformance,
    alerted_at: datetime,
    now: datetime,
) -> Optional[Tuple[str, str]]:
    for delta, price_field, return_field in INTERVAL_SCHEDULE:
        if now - alerted_at >= delta and getattr(perf, price_field) is None:
            return price_field, return_field
    return None


def _compute_return(entry: float, current: float) -> Optional[float]:
    if entry <= 0:
        return None
    return ((current - entry) / entry) * 100.0


def update_performance_records(db: Session) -> None:
    now = datetime.now(timezone.utc)

    pending = (
        db.query(SolAlertPerformance)
        .filter(
            (SolAlertPerformance.price_15m == None)  # noqa: E711
            | (SolAlertPerformance.price_1h == None)  # noqa: E711
            | (SolAlertPerformance.price_4h == None)  # noqa: E711
            | (SolAlertPerformance.price_24h == None)  # noqa: E711
        )
        .all()
    )

    if not pending:
        return

    for perf in pending:
        alert = db.query(SolAlert).filter(SolAlert.id == perf.alert_id).first()
        if not alert:
            continue

        alerted_at = alert.alerted_at
        if alerted_at.tzinfo is None:
            alerted_at = alerted_at.replace(tzinfo=timezone.utc)

        due = _next_due_interval(perf, alerted_at, now)
        if not due:
            continue

        price_field, return_field = due
        details = dex_service.fetch_token_details(perf.token_address)
        if not details or not details.get("price_usd"):
            logger.warning(
                "Price fetch failed for %s (%s) — will retry",
                perf.token_address,
                price_field,
            )
            continue

        current_price = float(details["price_usd"])
        setattr(perf, price_field, current_price)
        ret = _compute_return(perf.price_at_alert, current_price)
        setattr(perf, return_field, ret)
        perf.last_updated_at = now

        try:
            db.add(perf)
            db.commit()
            logger.info(
                "Updated %s for alert %s: price=%s return=%s",
                price_field,
                perf.alert_id,
                current_price,
                ret,
            )
        except Exception as exc:
            db.rollback()
            logger.error("Failed to save performance for alert %s: %s", perf.alert_id, exc)
