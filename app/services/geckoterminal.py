import logging
import time
from typing import Dict, List, Optional, Tuple

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

SOLANA_NETWORK = "solana"
SOURCE_TRENDING = "geckoterminal_trending"
SOURCE_NEW = "geckoterminal_new"


class GeckoTerminalService:
    def __init__(self) -> None:
        self.base_url = "https://api.geckoterminal.com/api/v2"
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
            self._circuit_open_until = time.time() + settings.GECKOTERMINAL_CIRCUIT_BREAK_SECONDS
            logger.warning(
                "GeckoTerminal circuit breaker open for %ss after %s consecutive failures",
                settings.GECKOTERMINAL_CIRCUIT_BREAK_SECONDS,
                self._failure_count,
            )

    def _get_json(self, url: str) -> Optional[dict]:
        if self._circuit_is_open():
            logger.warning("GeckoTerminal circuit breaker open — skipping %s", url)
            return None
        try:
            response = self.client.get(url)
            if response.status_code == 429:
                time.sleep(2.0)
                response = self.client.get(url)
            if response.status_code == 200:
                self._record_success()
                return response.json()
            logger.error("GeckoTerminal HTTP %s for %s", response.status_code, url)
            self._record_failure()
            return None
        except Exception as exc:
            logger.error("GeckoTerminal error for %s: %s", url, exc)
            self._record_failure()
            return None

    @staticmethod
    def _extract_base_token_address(pool: dict) -> Optional[str]:
        rel = pool.get("relationships", {}).get("base_token", {}).get("data", {})
        token_id = rel.get("id", "")
        prefix = f"{SOLANA_NETWORK}_"
        if token_id.startswith(prefix):
            return token_id[len(prefix) :]
        return None

    def _fetch_pool_tokens(self, endpoint: str, source: str) -> List[Tuple[str, str]]:
        url = f"{self.base_url}/networks/{SOLANA_NETWORK}/{endpoint}?page=1"
        data = self._get_json(url)
        if not data:
            return []

        results: List[Tuple[str, str]] = []
        seen: set[str] = set()
        for pool in data.get("data", []):
            address = self._extract_base_token_address(pool)
            if address and address not in seen:
                seen.add(address)
                results.append((address, source))
        return results

    def fetch_trending_tokens(self) -> List[Tuple[str, str]]:
        return self._fetch_pool_tokens("trending_pools", SOURCE_TRENDING)

    def fetch_new_pool_tokens(self) -> List[Tuple[str, str]]:
        return self._fetch_pool_tokens("new_pools", SOURCE_NEW)

    def discover(self) -> Dict[str, str]:
        if self._circuit_is_open():
            logger.warning("GeckoTerminal circuit breaker open — skipping discovery")
            return {}

        candidates: Dict[str, str] = {}
        for fetch_fn in (self.fetch_trending_tokens, self.fetch_new_pool_tokens):
            for address, source in fetch_fn():
                if address not in candidates:
                    candidates[address] = source
            time.sleep(0.3)

        logger.info("GeckoTerminal discovered %s Solana token candidates", len(candidates))
        return candidates


geckoterminal_service = GeckoTerminalService()
