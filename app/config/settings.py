from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solana Meme Coin Scanner"

    # Scanner
    SOL_SCANNER_ENABLED: bool = True
    SOL_SCAN_INTERVAL_SECONDS: int = 60
    SOL_MIN_LIQUIDITY_USD: float = 200_000.0
    SOL_MIN_VOLUME_5M: float = 15_000.0
    SOL_MIN_BUY_SELL_RATIO: float = 1.2
    SOL_MIN_BUY_SELL_RATIO_1H: float = 1.0
    SOL_MIN_SELLS_5M: int = 3
    SOL_MAX_TOKEN_AGE_HOURS: float = 48.0
    SOL_MAX_FDV_USD: float = 50_000_000.0
    SOL_MAX_FDV_LIQUIDITY_RATIO: float = 100.0
    SOL_MAX_VOLUME_LIQUIDITY_RATIO: float = 3.0
    SOL_MIN_PRIMARY_LIQUIDITY_SHARE: float = 0.5
    SOL_ALERT_SCORE_THRESHOLD: float = 60.0
    SOL_MIN_VOLUME_SCORE: float = 5.0
    SOL_MIN_MOMENTUM_SCORE: float = 5.0
    SOL_COOLDOWN_HOURS: float = 4.0
    SOL_MAX_ALERTS_PER_TOKEN: int = 2
    SOL_POSITION_USD: float = 20.0

    # Jupiter quote validation (hard gate before alert)
    JUPITER_QUOTE_ENABLED: bool = True
    JUPITER_QUOTE_API_URL: str = "https://lite-api.jup.ag/swap/v1"
    JUPITER_SLIPPAGE_BPS: int = 300
    JUPITER_MAX_PRICE_IMPACT_PCT: float = 5.0
    JUPITER_CIRCUIT_BREAK_SECONDS: int = 60

    # Performance-based score weight tuning
    SCORE_TUNING_ENABLED: bool = True
    SCORE_TUNING_MIN_SAMPLES: int = 10
    SCORE_TUNING_MAX_ADJUSTMENT: float = 0.25

    # Database
    DATABASE_URL: str = "sqlite:///./sol_scanner.db"

    # Telegram (shared with Base scanner in production)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Rugcheck
    RUGCHECK_CACHE_TTL_SECONDS: int = 300

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
