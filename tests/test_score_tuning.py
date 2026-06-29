from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance
from app.services.score_tuning import (
    apply_weighted_total,
    get_score_weight_multipliers,
    refresh_score_weight_multipliers,
)


def _seed_alert_with_return(db, breakdown, return_1h):
    alert = SolAlert(
        token_address="TuneMint1",
        filter_score=80,
        score_breakdown=breakdown,
        alerted_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db.add(alert)
    db.flush()
    perf = SolAlertPerformance(
        alert_id=alert.id,
        token_address="TuneMint1",
        price_at_alert=1.0,
        return_1h=return_1h,
    )
    db.add(perf)
    db.commit()


class TestScoreTuning:
    def test_refresh_requires_minimum_samples(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        for idx in range(5):
            _seed_alert_with_return(
                db,
                {"volume_momentum": 10.0, "price_action": 0.0},
                5.0 if idx % 2 == 0 else -5.0,
            )

        multipliers = refresh_score_weight_multipliers(db)
        assert multipliers["volume_momentum"] == 1.0
        db.close()

    def test_refresh_adjusts_weights_with_enough_samples(self, monkeypatch):
        from app.config import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "SCORE_TUNING_MIN_SAMPLES", 6)

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        for _ in range(6):
            _seed_alert_with_return(
                db,
                {"volume_momentum": 10.0, "price_action": 0.0},
                20.0,
            )
        for _ in range(6):
            _seed_alert_with_return(
                db,
                {"volume_momentum": 0.0, "price_action": 0.0},
                -10.0,
            )

        multipliers = refresh_score_weight_multipliers(db)
        assert multipliers["volume_momentum"] > 1.0
        db.close()

    def test_apply_weighted_total_caps_at_100(self, monkeypatch):
        from app.services import score_tuning

        monkeypatch.setitem(score_tuning._cached_multipliers, "liquidity_depth", 2.0)
        total = apply_weighted_total({"liquidity_depth": 80.0})
        assert total == 100.0
        multipliers = get_score_weight_multipliers()
        assert multipliers["liquidity_depth"] == 2.0
