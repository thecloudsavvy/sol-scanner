from datetime import datetime, timezone
from typing import Any, Optional


def parse_pair_created_at(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return None


def pair_age_hours(pair_created_at: Any) -> Optional[float]:
    created = parse_pair_created_at(pair_created_at)
    if created is None:
        return None
    delta = datetime.now(timezone.utc) - created
    return delta.total_seconds() / 3600.0
