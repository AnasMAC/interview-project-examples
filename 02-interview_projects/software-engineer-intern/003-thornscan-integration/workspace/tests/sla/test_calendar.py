import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from ledger.core import clock
from ledger.core.config import ROOT
from ledger.core.errors import ConfigError
from ledger.core.models import Severity
from ledger.sla.calendar import BusinessCalendar, load_calendar
from ledger.sla.policy import SlaPolicy, due_at, load_policy
from tests.helpers import TODAY

CALENDAR = load_calendar(ROOT / "config/holidays.toml", "Europe/Berlin")
POLICY = load_policy(ROOT / "config/sla.toml")


def at(text):
    return clock.parse_iso(text)


def due(severity, opened):
    value = due_at(severity, at(opened), policy=POLICY, calendar=CALENDAR)
    return value and clock.isoformat(value)


class CheckedInConfigTest(unittest.TestCase):
    def test_holidays_and_policy(self):
        self.assertEqual(len(CALENDAR.holidays), 11)
        self.assertEqual({day.year for day in CALENDAR.holidays}, {2026})
        self.assertIn(date(2026, 11, 18), CALENDAR.holidays)  # Buß- und Bettag, Saxony only
        self.assertEqual(str(CALENDAR.tz), "Europe/Berlin")
        self.assertEqual(dict(POLICY.days), {Severity.CRITICAL: 3, Severity.HIGH: 10, Severity.MEDIUM: 30, Severity.LOW: 60})
        self.assertIsNone(POLICY.days_for(Severity.INFO))


class DueDateTest(unittest.TestCase):
    def test_canonical_due_dates_from_today(self):
        opened = clock.isoformat(TODAY)  # Wed 2026-09-23 14:00 in Leipzig
        self.assertEqual(due(Severity.CRITICAL, opened), "2026-09-28T21:59:59Z")
        self.assertEqual(due(Severity.HIGH, opened), "2026-10-07T21:59:59Z")
        self.assertEqual(due(Severity.MEDIUM, opened), "2026-11-04T22:59:59Z")  # winter time by then
        self.assertEqual(due(Severity.LOW, opened), "2026-12-17T22:59:59Z")
        self.assertIsNone(due(Severity.INFO, opened))

    def test_local_date_decides_the_start_day(self):
        # 23:30 Thursday vs 00:30 Friday in Leipzig: both are Thursday evening in UTC.
        self.assertEqual(due(Severity.CRITICAL, "2026-10-01T21:30:00Z"), "2026-10-06T21:59:59Z")
        self.assertEqual(due(Severity.CRITICAL, "2026-10-01T22:30:00Z"), "2026-10-07T21:59:59Z")

    def test_friday_before_unity_day(self):
        # 3 October 2026 is a Saturday, so the holiday moves nothing: Mon, Tue, Wed.
        self.assertEqual(due(Severity.CRITICAL, "2026-10-02T10:00:00+02:00"), "2026-10-07T21:59:59Z")
        self.assertEqual(due(Severity.HIGH, "2026-10-02T10:00:00+02:00"), "2026-10-16T21:59:59Z")

    def test_due_date_after_dst_end(self):
        # Summer time ends Sun 2026-10-25; the due day is in CET (+01:00).
        self.assertEqual(due(Severity.CRITICAL, "2026-10-22T09:00:00+02:00"), "2026-10-27T22:59:59Z")
        self.assertEqual(due(Severity.CRITICAL, "2026-10-23T16:00:00+02:00"), "2026-10-28T22:59:59Z")

    def test_weekday_holidays_are_skipped(self):
        self.assertEqual(due(Severity.CRITICAL, "2026-11-17T09:00:00+01:00"), "2026-11-23T22:59:59Z")  # Wed 18th
        self.assertEqual(due(Severity.CRITICAL, "2026-12-23T09:00:00+01:00"), "2026-12-29T22:59:59Z")  # Fri 25th

    def test_weekend_start_counts_from_monday(self):
        self.assertEqual(due(Severity.CRITICAL, "2026-09-26T11:00:00+02:00"), "2026-09-30T21:59:59Z")

    def test_year_without_holidays_warns_once(self):
        calendar = load_calendar(ROOT / "config/holidays.toml", "Europe/Berlin")
        with self.assertLogs("ledger.sla.calendar", "WARNING") as logs:
            # Fri 2027-01-01 counts as a business day until 2027 is added to the file.
            ends = calendar.add_business_days(at("2026-12-30T09:00:00+01:00"), 3)
            calendar.add_business_days(at("2026-12-30T09:00:00+01:00"), 10)
        self.assertEqual(clock.isoformat(ends), "2027-01-04T22:59:59Z")
        self.assertEqual([(r.getMessage(), r.year) for r in logs.records], [("sla.holidays_missing", 2027)])

    def test_zero_negative_and_naive(self):
        self.assertEqual(clock.isoformat(CALENDAR.add_business_days(TODAY, 0)), "2026-09-23T21:59:59Z")
        with self.assertRaises(ValueError):
            CALENDAR.add_business_days(TODAY, -1)
        with self.assertRaises(ValueError):
            CALENDAR.add_business_days(datetime(2026, 9, 23, 14, 0), 3)

    def test_policy_accepts_plain_mappings(self):
        policy = SlaPolicy({"critical": 1})
        self.assertEqual(policy.days_for(Severity.CRITICAL), 1)
        self.assertIsNone(policy.days_for("high"))


class BusinessDaysBetweenTest(unittest.TestCase):
    def test_inverse_of_add_business_days(self):
        for start in ("2026-09-23T12:00:00Z", "2026-10-02T22:30:00Z", "2026-10-24T08:00:00Z", "2026-11-13T18:00:00Z"):
            for days in (0, 1, 3, 10, 30):
                with self.subTest(start=start, days=days):
                    end = CALENDAR.add_business_days(at(start), days)
                    self.assertEqual(CALENDAR.business_days_between(at(start), end), days)

    def test_across_dst_and_reversed(self):
        due_friday = at("2026-10-23T21:59:59Z")  # Fri 23:59:59 CEST
        monday_morning = at("2026-10-26T00:30:00+01:00")
        self.assertEqual(CALENDAR.business_days_between(due_friday, monday_morning), 1)
        self.assertEqual(CALENDAR.business_days_between(monday_morning, due_friday), -1)
        self.assertEqual(CALENDAR.business_days_between(due_friday, at("2026-10-25T12:00:00Z")), 0)


class LoadErrorsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, text):
        path = self.dir / "file.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_calendar_errors(self):
        bad = [
            '[[holiday]]\ndate = "2026-10-03"\nname = "Tag der Deutschen Einheit"\n',
            "[[holiday]]\ndate = 2026-10-03T00:00:00\nname = \"Tag der Deutschen Einheit\"\n",
            "[[holiday]]\ndate = 2026-10-03\n",
            "holiday = 3\n",
            "[[holiday]\n",
        ]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ConfigError):
                load_calendar(self.write(text), "Europe/Berlin")
        with self.assertRaises(ConfigError):
            load_calendar(self.dir / "missing.toml", "Europe/Berlin")
        with self.assertRaises(ConfigError):
            load_calendar(ROOT / "config/holidays.toml", "Europe/Leipzig")
        self.assertEqual(load_calendar(self.write("# none yet\n"), "UTC"), BusinessCalendar(clock.zone("UTC")))

    def test_policy_errors(self):
        for text in ("[days]\nurgent = 1\n", "[days]\nhigh = -1\n", "[days]\nhigh = 2.5\n", "critical = 3\n"):
            with self.subTest(text=text), self.assertRaises(ConfigError):
                load_policy(self.write(text))
        with self.assertRaises(ConfigError):
            load_policy(self.dir / "missing.toml")


if __name__ == "__main__":
    unittest.main()
