import sys
import types
from datetime import timedelta

import pytest

from atlas.core import clock


@pytest.fixture(autouse=True)
def window_start_calls(monkeypatch):
    """Stand-in for atlas.notify.changes (notify component): elapsed hours, records calls."""
    calls = []

    def window_start(org, hours=24, *, now=None):
        calls.append((org.slug, hours))
        return (now or clock.now()) - timedelta(hours=hours)

    module = types.ModuleType("atlas.notify.changes")
    module.window_start = window_start
    monkeypatch.setitem(sys.modules, "atlas.notify.changes", module)
    return calls

