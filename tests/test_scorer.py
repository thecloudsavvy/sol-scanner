from tests.conftest import base_details, good_rugcheck
from app.services.scorer import compute_filter_score, score_price_action


class TestScorer:
    def test_strong_setup_scores_high(self):
        result = compute_filter_score(base_details(), good_rugcheck())
        assert result.passed
        assert result.score >= 80.0

    def test_liquidity_floor_rejects_before_scoring(self):
        result = compute_filter_score(
            base_details(liquidity_usd=150_000),
            good_rugcheck(),
        )
        assert not result.passed
        assert result.skip_reason == "liquidity_below_min"
        assert result.score == 0.0

    def test_pumped_5m_penalty(self):
        pts, bd = score_price_action(35.0, 10.0, 50.0)
        assert bd.get("pumped_5m_penalty") == -10.0
        assert pts < 20.0

    def test_no_socials_zero_community(self):
        result = compute_filter_score(
            base_details(has_website=False, has_twitter=False, has_telegram=False),
            good_rugcheck(),
        )
        assert result.breakdown.get("community", -1) == 0.0
        assert result.no_socials

    def test_threshold_gates_alerts(self):
        borderline = compute_filter_score(
            base_details(
                liquidity_usd=220_000,
                volume_5m=16_000,
                buy_sell_ratio_5m=1.2,
                buy_sell_ratio_1h=1.0,
                buys_5m=10,
                sells_5m=8,
                price_change_5m=2.0,
                price_change_1h=0.0,
                price_change_24h=150.0,
                has_website=False,
                has_twitter=False,
                has_telegram=False,
            ),
            good_rugcheck(risk_level="Warn", warning_count=5),
        )
        assert not borderline.passed
        assert borderline.skip_reason == "score_below_threshold"
