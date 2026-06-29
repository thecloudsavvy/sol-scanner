from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String

from app.database.session import Base


class SolAlert(Base):
    __tablename__ = "sol_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("sol_tokens.address"), index=True)
    alerted_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source = Column(String, nullable=True)
    filter_score = Column(Float, default=0.0)
    score_breakdown = Column(JSON, nullable=True)

    liquidity_usd = Column(Float, default=0.0)
    volume_5m = Column(Float, default=0.0)
    price_usd = Column(Float, default=0.0)
    price_change_5m = Column(Float, default=0.0)
    price_change_1h = Column(Float, default=0.0)
    price_change_24h = Column(Float, default=0.0)
    buy_sell_ratio_5m = Column(Float, default=0.0)
    rugcheck_risk_level = Column(String, nullable=True)

    has_website = Column(Integer, default=0)
    has_twitter = Column(Integer, default=0)
    has_telegram = Column(Integer, default=0)
    website_url = Column(String, nullable=True)
    twitter_url = Column(String, nullable=True)
    telegram_url = Column(String, nullable=True)

    telegram_message_id = Column(String, nullable=True)
