import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

TARGET_CHAIN = "solana"
SOL_QUOTE_SYMBOLS = {"SOL", "WSOL", "USDC", "USDT"}


class DexScreenerService:
    def __init__(self) -> None:
        self.base_url = "https://api.dexscreener.com"
        self.headers = {
            "User-Agent": "SolScanner/1.0",
            "Accept": "application/json",
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
            self._circuit_open_until = time.time() + settings.DEXSCREENER_CIRCUIT_BREAK_SECONDS
            logger.warning(
                "DexScreener circuit breaker open for %ss after %s consecutive failures",
                settings.DEXSCREENER_CIRCUIT_BREAK_SECONDS,
                self._failure_count,
            )

    def _get_json(self, url: str) -> Optional[Any]:
        if self._circuit_is_open():
            logger.warning("DexScreener circuit breaker open — skipping %s", url)
            return None
        try:
            response = self.client.get(url)
            if response.status_code == 429:
                time.sleep(2.0)
                response = self.client.get(url)
            if response.status_code == 200:
                self._record_success()
                return response.json()
            logger.error("DexScreener HTTP %s for %s", response.status_code, url)
            self._record_failure()
            return None
        except Exception as exc:
            logger.error("DexScreener error for %s: %s", url, exc)
            self._record_failure()
            return None

    @staticmethod
    def _is_sol_quote_pair(pair: dict) -> bool:
        quote = pair.get("quoteToken", {})
        symbol = (quote.get("symbol") or "").upper()
        return symbol in SOL_QUOTE_SYMBOLS

    def _solana_pairs(self, pairs: List[dict]) -> List[dict]:
        return [p for p in pairs if p.get("chainId") == TARGET_CHAIN]

    def _select_primary_pair(self, pairs: List[dict]) -> Optional[dict]:
        sol_pairs = [p for p in self._solana_pairs(pairs) if self._is_sol_quote_pair(p)]
        if not sol_pairs:
            sol_pairs = self._solana_pairs(pairs)
        if not sol_pairs:
            return None
        sol_pairs.sort(
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
            reverse=True,
        )
        return sol_pairs[0]

    @staticmethod
    def _pair_liquidity_usd(pair: dict) -> float:
        return float(pair.get("liquidity", {}).get("usd", 0) or 0)

    @staticmethod
    def _pair_volume_5m(pair: dict) -> float:
        return float(pair.get("volume", {}).get("m5", 0) or 0)

    def _liquidity_concentration(self, sol_pairs: List[dict], primary_pair: dict) -> float:
        total_liq = sum(self._pair_liquidity_usd(p) for p in sol_pairs)
        if total_liq <= 0:
            return 1.0
        return self._pair_liquidity_usd(primary_pair) / total_liq

    @staticmethod
    def _buy_sell_ratio(buys: int, sells: int) -> float:
        if sells > 0:
            return buys / sells
        return float(buys)

    @staticmethod
    def _extract_socials(data: dict) -> Dict[str, Any]:
        info = data.get("info") or {}
        websites = info.get("websites") or []
        socials = info.get("socials") or []

        website_url = None
        if websites:
            website_url = websites[0].get("url") if isinstance(websites[0], dict) else websites[0]

        twitter_url = None
        telegram_url = None
        for social in socials:
            if not isinstance(social, dict):
                continue
            stype = (social.get("type") or "").lower()
            url = social.get("url")
            if stype in {"twitter", "x"} and url:
                twitter_url = url
            elif stype == "telegram" and url:
                telegram_url = url

        return {
            "has_website": bool(website_url),
            "has_twitter": bool(twitter_url),
            "has_telegram": bool(telegram_url),
            "website_url": website_url,
            "twitter_url": twitter_url,
            "telegram_url": telegram_url,
        }

    def fetch_token_details(self, token_address: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/latest/dex/tokens/{token_address}"
        data = self._get_json(url)
        if not data:
            return None

        pairs = data.get("pairs") or []
        sol_pairs = self._solana_pairs(pairs)
        primary_pair = self._select_primary_pair(pairs)
        if not primary_pair:
            return None

        base_info = primary_pair.get("baseToken", {})
        txns = primary_pair.get("txns", {})
        volume = primary_pair.get("volume", {})
        liquidity = primary_pair.get("liquidity", {})
        price_change = primary_pair.get("priceChange", {})

        buys_5m = int(txns.get("m5", {}).get("buys", 0) or 0)
        sells_5m = int(txns.get("m5", {}).get("sells", 0) or 0)
        buys_1h = int(txns.get("h1", {}).get("buys", 0) or 0)
        sells_1h = int(txns.get("h1", {}).get("sells", 0) or 0)

        liquidity_usd = float(liquidity.get("usd") or 0)
        volume_5m = float(volume.get("m5") or 0)
        volume_liquidity_ratio_5m = volume_5m / liquidity_usd if liquidity_usd > 0 else 0.0

        socials = self._extract_socials(data)

        return {
            "chain": TARGET_CHAIN,
            "address": base_info.get("address") or token_address,
            "name": base_info.get("name"),
            "symbol": base_info.get("symbol"),
            "market_cap": float(primary_pair.get("marketCap") or 0),
            "fdv": float(primary_pair.get("fdv") or 0),
            "liquidity_usd": liquidity_usd,
            "total_liquidity_usd": sum(self._pair_liquidity_usd(p) for p in sol_pairs),
            "primary_liquidity_share": self._liquidity_concentration(sol_pairs, primary_pair),
            "solana_pair_count": len(sol_pairs),
            "price_usd": float(primary_pair.get("priceUsd") or 0),
            "volume_5m": volume_5m,
            "volume_1h": float(volume.get("h1") or 0),
            "volume_24h": float(volume.get("h24") or 0),
            "volume_liquidity_ratio_5m": volume_liquidity_ratio_5m,
            "price_change_5m": float(price_change.get("m5") or 0),
            "price_change_1h": float(price_change.get("h1") or 0),
            "price_change_24h": float(price_change.get("h24") or 0),
            "buys_5m": buys_5m,
            "sells_5m": sells_5m,
            "buy_sell_ratio_5m": self._buy_sell_ratio(buys_5m, sells_5m),
            "buys_1h": buys_1h,
            "sells_1h": sells_1h,
            "buy_sell_ratio_1h": self._buy_sell_ratio(buys_1h, sells_1h),
            "pair_created_at": primary_pair.get("pairCreatedAt"),
            "pair_address": primary_pair.get("pairAddress"),
            "dex_id": primary_pair.get("dexId"),
            "quote_token_address": primary_pair.get("quoteToken", {}).get("address"),
            **socials,
        }


dex_service = DexScreenerService()
