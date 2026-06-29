from unittest.mock import patch

from app.services.rugcheck import RugcheckResult, RugcheckService


class TestRugcheck:
    def setup_method(self):
        self.svc = RugcheckService()

    def test_freeze_authority_fails(self):
        report = {"score": 70, "riskLevel": "Good", "freezeAuthority": True}
        result = self.svc.evaluate_report(report)
        assert not result.passed
        assert result.skip_reason == "rugcheck_failed"
        assert "freeze_authority_enabled" in result.flags

    def test_mint_authority_fails(self):
        report = {"score": 70, "riskLevel": "Good", "mintAuthority": True}
        result = self.svc.evaluate_report(report)
        assert not result.passed
        assert "mint_authority_enabled" in result.flags

    def test_high_holder_concentration_fails(self):
        report = {"score": 70, "riskLevel": "Good", "highHolderConcentration": True}
        result = self.svc.evaluate_report(report)
        assert not result.passed
        assert "high_holder_concentration" in result.flags

    def test_danger_level_fails(self):
        report = {"score": 20, "riskLevel": "Danger"}
        result = self.svc.evaluate_report(report)
        assert not result.passed
        assert result.skip_reason == "rugcheck_failed"

    def test_cache_hit_no_api_call(self):
        mint = "CacheMint111"
        cached = RugcheckResult(passed=True, score=80, risk_level="Good")
        self.svc._cache_set(mint, cached)
        with patch.object(self.svc.client, "get") as mock_get:
            result = self.svc.fetch_report(mint)
            mock_get.assert_not_called()
        assert result.passed

    def test_api_failure_skips_token(self):
        mint = "FailMint222"
        with patch.object(self.svc.client, "get", side_effect=Exception("network")):
            result = self.svc.fetch_report(mint)
        assert not result.passed
        assert result.unavailable
        assert result.skip_reason == "rugcheck_unavailable"
