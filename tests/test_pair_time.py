from datetime import datetime, timezone, timedelta

from app.utils.pair_time import pair_age_hours, parse_pair_created_at


class TestPairTime:
    def test_parse_milliseconds_timestamp(self):
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        ms = int(dt.timestamp() * 1000)
        assert parse_pair_created_at(ms) == dt

    def test_pair_age_hours_uses_shared_parser(self):
        created = datetime.now(timezone.utc) - timedelta(hours=6)
        ms = int(created.timestamp() * 1000)
        age = pair_age_hours(ms)
        assert age is not None
        assert 5.9 <= age <= 6.1
