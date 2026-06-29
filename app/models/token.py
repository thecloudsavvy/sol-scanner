from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String

from app.database.session import Base


class SolToken(Base):
    __tablename__ = "sol_tokens"

    address = Column(String, primary_key=True, index=True)
    symbol = Column(String, nullable=True)
    name = Column(String, nullable=True)

    liquidity_usd = Column(Float, default=0.0)
    price_usd = Column(Float, default=0.0)
    volume_5m = Column(Float, default=0.0)
    volume_1h = Column(Float, default=0.0)
    volume_24h = Column(Float, default=0.0)
    price_change_5m = Column(Float, default=0.0)
    price_change_1h = Column(Float, default=0.0)
    price_change_24h = Column(Float, default=0.0)
    buys_5m = Column(Integer, default=0)
    sells_5m = Column(Integer, default=0)
    buy_sell_ratio_5m = Column(Float, default=0.0)
    market_cap = Column(Float, default=0.0)
    fdv = Column(Float, default=0.0)

    pair_address = Column(String, nullable=True)
    dex_id = Column(String, nullable=True)
    quote_token_address = Column(String, nullable=True)
    pair_created_at = Column(DateTime(timezone=True), nullable=True)
    token_age_hours = Column(Float, nullable=True)

    has_website = Column(Integer, default=0)
    has_twitter = Column(Integer, default=0)
    has_telegram = Column(Integer, default=0)
    website_url = Column(String, nullable=True)
    twitter_url = Column(String, nullable=True)
    telegram_url = Column(String, nullable=True)

    rugcheck_score = Column(Float, nullable=True)
    rugcheck_risk_level = Column(String, nullable=True)
    rugcheck_flags = Column(JSON, nullable=True)
    rugcheck_checked_at = Column(DateTime(timezone=True), nullable=True)

    first_seen_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_scanned_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    alerted_count = Column(Integer, default=0)
    last_alerted_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String, nullable=True)
