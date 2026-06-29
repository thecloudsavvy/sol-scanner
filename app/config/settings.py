from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solana Meme Coin Scanner"

    # Scanner
    SOL_SCANNER_ENABLED: bool = True
    SOL_SCAN_INTERVAL_SECONDS: int = 60
    SOL_MIN_LIQUIDITY_USD: float = 100_000.0
    SOL_MIN_VOLUME_5M: float = 5_000.0
    SOL_MIN_BUY_SELL_RATIO: float = 1.0
    SOL_MAX_TOKEN_AGE_HOURS: float = 72.0
    SOL_ALERT_SCORE_THRESHOLD: float = 60.0
    SOL_COOLDOWN_HOURS: float = 4.0
    SOL_MAX_ALERTS_PER_TOKEN: int = 2
    SOL_POSITION_USD: float = 20.0

    # Database
    DATABASE_URL: str = "sqlite:///./sol_scanner.db"

    # Telegram (shared with Base scanner in production)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Rugcheck
    RUGCHECK_CACHE_TTL_SECONDS: int = 600

    # Circuit breakers
    DEXSCREENER_CIRCUIT_BREAK_SECONDS: int = 60
    GECKOTERMINAL_CIRCUIT_BREAK_SECONDS: int = 60

    # Dashboard auth (mandatory when SOL_SCANNER_ENABLED or LIVE_TRADING_ENABLED)
    LIVE_TRADING_ENABLED: bool = False
    DASHBOARD_USERNAME: str = ""
    DASHBOARD_PASSWORD: str = ""

    # API
    API_PORT: int = 8001

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
