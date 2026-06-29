from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.database.session import Base


class SolCandidateObservation(Base):
    __tablename__ = "sol_candidate_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("sol_tokens.address"), index=True)
    observed_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source = Column(String, nullable=True)
    outcome = Column(String, nullable=False)
    skip_reason = Column(String, nullable=True)
    filter_score = Column(Float, nullable=True)

    liquidity_usd = Column(Float, nullable=True)
    volume_5m = Column(Float, nullable=True)
    price_change_5m = Column(Float, nullable=True)
    buy_sell_ratio_5m = Column(Float, nullable=True)
