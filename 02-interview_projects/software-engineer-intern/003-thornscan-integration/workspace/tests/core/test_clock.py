import unittest
from datetime import datetime, timedelta, timezone

from ledger.core import clock


class ClockTest(unittest.TestCase):
    def test_isoformat_is_utc_seconds(self):
        berlin = datetime(2026, 9, 23, 14, 0, 30, 999, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(clock.isoformat(berlin), "2026-09-23T12:00:30Z")
        self.assertEqual(clock.parse_iso("2026-09-23T14:00:30+02:00"), berlin.replace(microsecond=0))
        self.assertEqual(clock.parse_iso("2026-09-23T12:00:30Z").tzinfo, clock.UTC)

    def test_naive_values_rejected(self):
        with self.assertRaises(ValueError):
            clock.isoformat(datetime(2026, 9, 23))
        for text in ("2026-09-23T12:00:00", "yesterday"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                clock.parse_iso(text)

    def test_frozen_restores_previous_source(self):
        at = datetime(2026, 9, 23, 12, 0, tzinfo=clock.UTC)
        with clock.frozen(at) as frozen:
            self.assertEqual(clock.now(), at)
            frozen.advance(days=1, hours=2)
            self.assertEqual(clock.now(), at + timedelta(days=1, hours=2))
        self.assertGreater(clock.now(), at)
        self.assertEqual(clock.zone("Europe/Berlin").utcoffset(datetime(2026, 9, 23)), timedelta(hours=2))
