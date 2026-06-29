import pytest

from app.auth import validate_security_config
from app.config.settings import Settings


class TestValidateSecurityConfig:
    def test_rejects_default_password_when_scanner_enabled(self, monkeypatch):
        monkeypatch.setattr(
            "app.auth.settings",
            Settings(
                SOL_SCANNER_ENABLED=True,
                DASHBOARD_USERNAME="admin",
                DASHBOARD_PASSWORD="change-me",
            ),
        )
        with pytest.raises(SystemExit) as exc:
            validate_security_config()
        assert exc.value.code == 1

    def test_accepts_custom_password_when_scanner_enabled(self, monkeypatch):
        monkeypatch.setattr(
            "app.auth.settings",
            Settings(
                SOL_SCANNER_ENABLED=True,
                DASHBOARD_USERNAME="admin",
                DASHBOARD_PASSWORD="secure-password-123",
            ),
        )
        validate_security_config()

    def test_skips_validation_when_scanner_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "app.auth.settings",
            Settings(
                SOL_SCANNER_ENABLED=False,
                LIVE_TRADING_ENABLED=False,
                DASHBOARD_PASSWORD="change-me",
            ),
        )
        validate_security_config()
