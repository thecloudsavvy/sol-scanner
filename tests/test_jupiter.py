from unittest.mock import patch

import pytest

from app.services.jupiter import JupiterQuoteResult, JupiterService


class TestJupiter:
    def test_validate_routable_passes_with_buy_and_sell_quotes(self):
        service = JupiterService()
        buy_quote = {
            "routePlan": [{"swapInfo": {}}],
            "priceImpactPct": "1.2",
            "outAmount": "1000000",
        }
        sell_quote = {
            "routePlan": [{"swapInfo": {}}],
            "priceImpactPct": "0.8",
        }
        with patch.object(service, "_fetch_quote", side_effect=[buy_quote, sell_quote]):
            result = service.validate_routable("TokenMint123")
        assert result.passed
        assert result.buy_price_impact_pct == 1.2
        assert result.sell_price_impact_pct == 0.8

    def test_validate_routable_fails_without_buy_route(self):
        service = JupiterService()
        with patch.object(service, "_fetch_quote", return_value=None):
            result = service.validate_routable("TokenMint123")
        assert not result.passed
        assert result.skip_reason == "jupiter_no_buy_route"

    def test_validate_routable_fails_on_high_price_impact(self):
        service = JupiterService()
        buy_quote = {
            "routePlan": [{"swapInfo": {}}],
            "priceImpactPct": "8.5",
            "outAmount": "1000000",
        }
        with patch.object(service, "_fetch_quote", return_value=buy_quote):
            result = service.validate_routable("TokenMint123")
        assert not result.passed
        assert result.skip_reason == "jupiter_buy_impact_too_high"

    def test_validate_routable_disabled(self, monkeypatch):
        from app.config import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "JUPITER_QUOTE_ENABLED", False)
        service = JupiterService()
        result = service.validate_routable("TokenMint123")
        assert result.passed
