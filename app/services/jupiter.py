import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@dataclass
class JupiterQuoteResult:
    passed: bool
    unavailable: bool = False
    buy_price_impact_pct: Optional[float] = None
    sell_price_impact_pct: Optional[float] = None
    skip_reason: Optional[str] = None


class JupiterService:
    def __init__(self) -> None:
        self.base_url = settings.JUPITER_QUOTE_API_URL.rstrip("/")
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "SolScanner/1.0",
        }
        self.client = httpx.Client(headers=self.headers, timeout=15.0)
        self._failure_count = 0
        self._circuit_open_until = 0.0

    def _circuit_is_open(self) -> bool:
        return time.time() < self._circuit_open_until

    def _record_success(self) -> None:
        self._failure_count = 0
        self._circuit_open_until = 0.0

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= 3:
            self._circuit_open_until = time.time() + settings.JUPITER_CIRCUIT_BREAK_SECONDS
            logger.warning(
                "Jupiter circuit breaker open for %ss after %s consecutive failures",
                settings.JUPITER_CIRCUIT_BREAK_SECONDS,
                self._failure_count,
            )

    def _fetch_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
    ) -> Optional[dict]:
        if self._circuit_is_open():
            logger.warning("Jupiter circuit breaker open — skipping quote")
            return None
        try:
            response = self.client.get(
                f"{self.base_url}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": amount,
                    "slippageBps": settings.JUPITER_SLIPPAGE_BPS,
                },
            )
            if response.status_code == 429:
                time.sleep(2.0)
                response = self.client.get(
                    f"{self.base_url}/quote",
                    params={
                        "inputMint": input_mint,
                        "outputMint": output_mint,
                        "amount": amount,
                        "slippageBps": settings.JUPITER_SLIPPAGE_BPS,
                    },
                )
            if response.status_code == 200:
                data = response.json()
                if data.get("routePlan"):
                    self._record_success()
                    return data
                logger.warning(
                    "Jupiter no route %s -> %s: %s",
                    input_mint,
                    output_mint,
                    data.get("error") or data,
                )
                return None
            logger.error("Jupiter HTTP %s for %s -> %s", response.status_code, input_mint, output_mint)
            self._record_failure()
            return None
        except Exception as exc:
            logger.error("Jupiter quote error %s -> %s: %s", input_mint, output_mint, exc)
            self._record_failure()
            return None

    @staticmethod
    def _price_impact(quote: dict) -> float:
        try:
            return abs(float(quote.get("priceImpactPct") or 0))
        except (TypeError, ValueError):
            return 0.0

    def validate_routable(self, token_mint: str) -> JupiterQuoteResult:
        if not settings.JUPITER_QUOTE_ENABLED:
            return JupiterQuoteResult(passed=True)

        usdc_amount = int(settings.SOL_POSITION_USD * 1_000_000)
        buy_quote = self._fetch_quote(USDC_MINT, token_mint, usdc_amount)
        if not buy_quote:
            if self._circuit_is_open() or self._failure_count >= 3:
                return JupiterQuoteResult(
                    passed=False,
                    unavailable=True,
                    skip_reason="jupiter_unavailable",
                )
            return JupiterQuoteResult(
                passed=False,
                skip_reason="jupiter_no_buy_route",
            )

        buy_impact = self._price_impact(buy_quote)
        if buy_impact > settings.JUPITER_MAX_PRICE_IMPACT_PCT:
            return JupiterQuoteResult(
                passed=False,
                buy_price_impact_pct=buy_impact,
                skip_reason="jupiter_buy_impact_too_high",
            )

        out_amount = buy_quote.get("outAmount")
        if not out_amount:
            return JupiterQuoteResult(
                passed=False,
                skip_reason="jupiter_no_buy_route",
            )

        sell_quote = self._fetch_quote(token_mint, USDC_MINT, int(out_amount))
        if not sell_quote:
            if self._circuit_is_open():
                return JupiterQuoteResult(
                    passed=False,
                    unavailable=True,
                    skip_reason="jupiter_unavailable",
                )
            return JupiterQuoteResult(
                passed=False,
                buy_price_impact_pct=buy_impact,
                skip_reason="jupiter_no_sell_route",
            )

        sell_impact = self._price_impact(sell_quote)
        if sell_impact > settings.JUPITER_MAX_PRICE_IMPACT_PCT:
            return JupiterQuoteResult(
                passed=False,
                buy_price_impact_pct=buy_impact,
                sell_price_impact_pct=sell_impact,
                skip_reason="jupiter_sell_impact_too_high",
            )

        return JupiterQuoteResult(
            passed=True,
            buy_price_impact_pct=buy_impact,
            sell_price_impact_pct=sell_impact,
        )


jupiter_service = JupiterService()
