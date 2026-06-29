from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance
from app.services.performance_tracker import update_performance_records


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_alert(db, price_at_alert=1.0, alerted_minutes_ago=20):
    alert = SolAlert(
        token_address="PerfMint1",
        filter_score=80,
        price_usd=price_at_alert,
        alerted_at=datetime.now(timezone.utc) - timedelta(minutes=alerted_minutes_ago),
    )
    db.add(alert)
    db.flush()
    perf = SolAlertPerformance(
        alert_id=alert.id,
        token_address="PerfMint1",
        price_at_alert=price_at_alert,
    )
    db.add(perf)
    db.commit()
    return alert, perf


class TestPerformanceTracker:
    def test_15m_return_populated(self, db):
        _seed_alert(db, price_at_alert=1.0, alerted_minutes_ago=20)
        with patch(
            "app.services.performance_tracker.dex_service.fetch_token_details",
            return_value={"price_usd": 1.2},
        ):
            update_performance_records(db)

        perf = db.query(SolAlertPerformance).first()
        assert perf.price_15m == 1.2
        assert perf.return_15m == pytest.approx(20.0)

    def test_already_updated_not_refetched(self, db):
        _, perf = _seed_alert(db, price_at_alert=1.0, alerted_minutes_ago=20)
        perf.price_15m = 1.1
        perf.return_15m = 10.0
        db.commit()

        with patch(
            "app.services.performance_tracker.dex_service.fetch_token_details",
        ) as mock_fetch:
            update_performance_records(db)
            mock_fetch.assert_not_called()

    def test_fetch_failure_does_not_crash(self, db):
        _seed_alert(db)
        with patch(
            "app.services.performance_tracker.dex_service.fetch_token_details",
            return_value=None,
        ):
            update_performance_records(db)
        perf = db.query(SolAlertPerformance).first()
        assert perf.price_15m is None

    def test_all_due_intervals_updated_in_one_pass(self, db):
        _seed_alert(db, price_at_alert=1.0, alerted_minutes_ago=25 * 60)
        with patch(
            "app.services.performance_tracker.dex_service.fetch_token_details",
            return_value={"price_usd": 1.5},
        ) as mock_fetch:
            update_performance_records(db)
            mock_fetch.assert_called_once()

        perf = db.query(SolAlertPerformance).first()
        assert perf.price_15m == 1.5
        assert perf.price_1h == 1.5
        assert perf.price_4h == 1.5
        assert perf.price_24h == 1.5
        assert perf.return_15m == pytest.approx(50.0)
        assert perf.return_1h == pytest.approx(50.0)
        assert perf.return_4h == pytest.approx(50.0)
        assert perf.return_24h == pytest.approx(50.0)
