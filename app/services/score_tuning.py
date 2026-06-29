import logging
from typing import Dict

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance

logger = logging.getLogger(__name__)

SCORE_COMPONENTS = (
    "liquidity_depth",
    "volume_momentum",
    "price_action",
    "buy_sell_pressure",
    "community",
    "rugcheck_bonus",
)

_cached_multipliers: Dict[str, float] = {key: 1.0 for key in SCORE_COMPONENTS}


def get_score_weight_multipliers() -> Dict[str, float]:
    return dict(_cached_multipliers)


def refresh_score_weight_multipliers(db: Session) -> Dict[str, float]:
    global _cached_multipliers

    if not settings.SCORE_TUNING_ENABLED:
        _cached_multipliers = {key: 1.0 for key in SCORE_COMPONENTS}
        return dict(_cached_multipliers)

    rows = (
        db.query(SolAlert.score_breakdown, SolAlertPerformance.return_1h)
        .join(SolAlertPerformance, SolAlertPerformance.alert_id == SolAlert.id)
        .filter(SolAlertPerformance.return_1h.isnot(None))
        .filter(SolAlert.score_breakdown.isnot(None))
        .all()
    )

    if len(rows) < settings.SCORE_TUNING_MIN_SAMPLES:
        return dict(_cached_multipliers)

    multipliers = {key: 1.0 for key in SCORE_COMPONENTS}
    for component in SCORE_COMPONENTS:
        with_points: list[float] = []
        without_points: list[float] = []
        for breakdown, ret in rows:
            if not isinstance(breakdown, dict):
                continue
            points = float(breakdown.get(component) or 0)
            if points > 0:
                with_points.append(float(ret))
            else:
                without_points.append(float(ret))

        if len(with_points) < 3 or len(without_points) < 3:
            continue

        with_avg = sum(with_points) / len(with_points)
        without_avg = sum(without_points) / len(without_points)
        delta = with_avg - without_avg
        adjustment = max(
            -settings.SCORE_TUNING_MAX_ADJUSTMENT,
            min(settings.SCORE_TUNING_MAX_ADJUSTMENT, delta / 100.0),
        )
        multipliers[component] = round(1.0 + adjustment, 3)

    _cached_multipliers = multipliers
    logger.info("Score tuning multipliers refreshed: %s", multipliers)
    return dict(_cached_multipliers)


def apply_weighted_total(breakdown: Dict[str, float]) -> float:
    total = 0.0
    for component in SCORE_COMPONENTS:
        total += breakdown.get(component, 0.0) * _cached_multipliers.get(component, 1.0)
    return max(0.0, min(100.0, total))
