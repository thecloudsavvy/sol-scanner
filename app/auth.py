import base64
import logging
import secrets
import sys

from fastapi import Request
from fastapi.responses import Response

from app.config.settings import settings

logger = logging.getLogger(__name__)

_DEFAULT_PASSWORDS = frozenset({"change-me", "changeme"})


def basic_auth_enabled() -> bool:
    if settings.LIVE_TRADING_ENABLED:
        return True
    if settings.SOL_SCANNER_ENABLED:
        return bool(settings.DASHBOARD_USERNAME and settings.DASHBOARD_PASSWORD)
    return bool(settings.DASHBOARD_USERNAME and settings.DASHBOARD_PASSWORD)


def validate_security_config() -> None:
    if not settings.SOL_SCANNER_ENABLED and not settings.LIVE_TRADING_ENABLED:
        return
    if not settings.DASHBOARD_USERNAME or not settings.DASHBOARD_PASSWORD:
        logger.critical(
            "SOL_SCANNER_ENABLED or LIVE_TRADING_ENABLED requires "
            "DASHBOARD_USERNAME and DASHBOARD_PASSWORD"
        )
        sys.exit(1)
    if settings.DASHBOARD_PASSWORD.lower() in _DEFAULT_PASSWORDS:
        logger.critical(
            "DASHBOARD_PASSWORD must be changed from the default placeholder "
            "when SOL_SCANNER_ENABLED or LIVE_TRADING_ENABLED"
        )
        sys.exit(1)


async def dashboard_basic_auth_middleware(request: Request, call_next):
    if not basic_auth_enabled():
        return await call_next(request)

    if request.url.path.startswith("/static"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Sol Scanner"'},
        )

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, _, password = decoded.partition(":")
    except Exception:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Sol Scanner"'},
        )

    valid_user = secrets.compare_digest(username, settings.DASHBOARD_USERNAME)
    valid_pass = secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)
    if not (valid_user and valid_pass):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Sol Scanner"'},
        )

    return await call_next(request)
