from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance
from app.models.token import SolToken
from app.scanner.engine import _cooldown_blocks_alert, process_token
from app.services.scorer import compute_filter_score
from tests.conftest import base_details, good_jupiter, good_rugcheck


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestFilters:
    def test_token_too_old_rejected(self):
        old_ms = int((datetime.now(timezone.utc) - timedelta(hours=100)).timestamp() * 1000)
        result = compute_filter_score(
            base_details(pair_created_at=old_ms),
            good_rugcheck(),
        )
        assert not result.passed
        assert result.skip_reason == "token_too_old"

    def test_low_liquidity_rejected(self):
        result = compute_filter_score(base_details(liquidity_usd=150_000), good_rugcheck())
        assert not result.passed
        assert result.skip_reason == "liquidity_below_min"

    def test_low_buy_sell_rejected(self):
        result = compute_filter_score(base_details(buy_sell_ratio_5m=0.5), good_rugcheck())
        assert not result.passed
        assert result.skip_reason == "buy_sell_ratio_below_min"

    def test_min_sells_rejected(self):
        result = compute_filter_score(
            base_details(buys_5m=50, sells_5m=0, buy_sell_ratio_5m=50.0),
            good_rugcheck(),
        )
        assert not result.passed
        assert result.skip_reason == "min_sells_5m_below_min"

    def test_fdv_cap_rejected(self):
        result = compute_filter_score(base_details(fdv=60_000_000), good_rugcheck())
        assert not result.passed
        assert result.skip_reason == "fdv_above_max"

    def test_volume_liquidity_ratio_rejected(self):
        result = compute_filter_score(
            base_details(volume_5m=500_000, volume_liquidity_ratio_5m=4.0),
            good_rugcheck(),
        )
        assert not result.passed
        assert result.skip_reason == "volume_liquidity_ratio_above_max"

    def test_category_minimum_rejected(self):
        result = compute_filter_score(
            base_details(
                volume_5m=16_000,
                buy_sell_ratio_5m=1.2,
                buy_sell_ratio_1h=1.0,
                price_change_5m=40.0,
                price_change_1h=-40.0,
            ),
            good_rugcheck(),
        )
        assert not result.passed
        assert result.skip_reason == "momentum_score_below_min"

    def test_passing_score_generates_alert(self, db):
        token = SolToken(address="AlertMint1", symbol="ALRT")
        db.add(token)
        db.commit()

        details = base_details(address="AlertMint1")
        with (
            patch("app.scanner.engine.dex_service.fetch_token_details", return_value=details),
            patch("app.scanner.engine.rugcheck_service.fetch_report", return_value=good_rugcheck()),
            patch("app.scanner.engine.jupiter_service.validate_routable", return_value=good_jupiter()),
            patch("app.scanner.engine.send_sol_alert", return_value=(True, "123")),
        ):
            process_token(db, "AlertMint1", "test")

        alert = db.query(SolAlert).filter(SolAlert.token_address == "AlertMint1").first()
        assert alert is not None
        assert alert.filter_score >= 60

    def test_cooldown_suppresses_duplicate(self, db):
        token = SolToken(
            address="CoolMint1",
            symbol="COOL",
            alerted_count=1,
            last_alerted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(token)
        db.commit()
        assert _cooldown_blocks_alert(token)

        details = base_details(address="CoolMint1")
        with (
            patch("app.scanner.engine.dex_service.fetch_token_details", return_value=details),
            patch("app.scanner.engine.rugcheck_service.fetch_report", return_value=good_rugcheck()),
            patch("app.scanner.engine.jupiter_service.validate_routable", return_value=good_jupiter()),
            patch("app.scanner.engine.send_sol_alert") as mock_send,
        ):
            process_token(db, "CoolMint1", "test")
            mock_send.assert_not_called()

        assert db.query(SolAlert).count() == 0
