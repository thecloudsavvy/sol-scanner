from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.database.session import Base


class SolAlertPerformance(Base):
    __tablename__ = "sol_alert_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("sol_alerts.id"), unique=True, index=True)
    token_address = Column(String, index=True)
    price_at_alert = Column(Float, nullable=False)

    price_15m = Column(Float, nullable=True)
    price_1h = Column(Float, nullable=True)
    price_4h = Column(Float, nullable=True)
    price_24h = Column(Float, nullable=True)

    return_15m = Column(Float, nullable=True)
    return_1h = Column(Float, nullable=True)
    return_4h = Column(Float, nullable=True)
    return_24h = Column(Float, nullable=True)

    last_updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
