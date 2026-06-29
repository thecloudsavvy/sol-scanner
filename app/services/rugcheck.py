import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

FAIL_FLAGS = {
    "freeze_authority_enabled",
    "mint_authority_enabled",
    "high_holder_concentration",
    "no_liquidity_locked",
    "honeypot_like_token",
}


@dataclass
class RugcheckResult:
    passed: bool
    unavailable: bool = False
    score: Optional[float] = None
    risk_level: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    warning_count: int = 0
    skip_reason: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class RugcheckService:
    def __init__(self) -> None:
        self.base_url = "https://api.rugcheck.xyz/v1"
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "SolScanner/1.0",
        }
        self.client = httpx.Client(headers=self.headers, timeout=15.0)
        self._failure_count = 0
        self._cache: Dict[str, tuple[float, RugcheckResult]] = {}

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= 3:
            logger.warning(
                "Rugcheck circuit: %s consecutive failures — tokens will be skipped",
                self._failure_count,
            )

    def _record_success(self) -> None:
        self._failure_count = 0

    def _cache_get(self, mint: str) -> Optional[RugcheckResult]:
        entry = self._cache.get(mint)
        if not entry:
            return None
        expires_at, result = entry
        if time.time() < expires_at:
            return result
        del self._cache[mint]
        return None

    def _cache_set(self, mint: str, result: RugcheckResult) -> None:
        self._cache[mint] = (
            time.time() + settings.RUGCHECK_CACHE_TTL_SECONDS,
            result,
        )

    @staticmethod
    def _normalize_risk_level(report: dict) -> str:
        for key in ("riskLevel", "risk_level", "overallRisk"):
            val = report.get(key)
            if isinstance(val, str):
                return val
            if isinstance(val, dict):
                level = val.get("level") or val.get("name")
                if isinstance(level, str):
                    return level
        score = report.get("score")
        if isinstance(score, (int, float)):
            if score >= 80:
                return "Good"
            if score >= 50:
                return "Warn"
            return "Danger"
        return "Warn"

    @staticmethod
    def _extract_flags(report: dict) -> List[str]:
        flags: List[str] = []
        risks = report.get("risks") or report.get("riskFlags") or []
        if isinstance(risks, list):
            for item in risks:
                if isinstance(item, str):
                    flags.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("key") or item.get("type")
                    if name:
                        flags.append(str(name))
        token_meta = report.get("tokenMeta") or report.get("token") or {}
        if isinstance(token_meta, dict):
            if token_meta.get("freezeAuthority"):
                flags.append("freeze_authority_enabled")
            if token_meta.get("mintAuthority"):
                flags.append("mint_authority_enabled")
        if report.get("freezeAuthority"):
            flags.append("freeze_authority_enabled")
        if report.get("mintAuthority"):
            flags.append("mint_authority_enabled")
        if report.get("highHolderConcentration"):
            flags.append("high_holder_concentration")
        if report.get("noLiquidityLocked"):
            flags.append("no_liquidity_locked")
        if report.get("honeypotLikeToken"):
            flags.append("honeypot_like_token")
        return list(dict.fromkeys(flags))

    @staticmethod
    def _count_warnings(report: dict, flags: List[str]) -> int:
        risks = report.get("risks") or []
        if isinstance(risks, list):
            return sum(
                1
                for r in risks
                if isinstance(r, dict) and (r.get("level") or "").lower() in {"warn", "warning"}
            )
        return max(0, len(flags) - len(FAIL_FLAGS.intersection(flags)))

    def evaluate_report(self, report: dict) -> RugcheckResult:
        risk_level = self._normalize_risk_level(report)
        flags = self._extract_flags(report)
        warning_count = self._count_warnings(report, flags)
        score = report.get("score")
        if score is not None:
            score = float(score)

        if risk_level.lower() == "danger":
            return RugcheckResult(
                passed=False,
                score=score,
                risk_level=risk_level,
                flags=flags,
                warning_count=warning_count,
                skip_reason="rugcheck_failed",
                raw=report,
            )

        for flag in FAIL_FLAGS:
            if flag in flags:
                return RugcheckResult(
                    passed=False,
                    score=score,
                    risk_level=risk_level,
                    flags=flags,
                    warning_count=warning_count,
                    skip_reason="rugcheck_failed",
                    raw=report,
                )

        return RugcheckResult(
            passed=True,
            score=score,
            risk_level=risk_level,
            flags=flags,
            warning_count=warning_count,
            raw=report,
        )

    def fetch_report(self, mint: str) -> RugcheckResult:
        cached = self._cache_get(mint)
        if cached is not None:
            return cached

        url = f"{self.base_url}/tokens/{mint}/report"
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                self._record_success()
                result = self.evaluate_report(response.json())
                self._cache_set(mint, result)
                return result
            logger.error("Rugcheck HTTP %s for %s", response.status_code, mint)
            self._record_failure()
        except Exception as exc:
            logger.error("Rugcheck error for %s: %s", mint, exc)
            self._record_failure()

        result = RugcheckResult(
            passed=False,
            unavailable=True,
            skip_reason="rugcheck_unavailable",
        )
        return result


rugcheck_service = RugcheckService()
