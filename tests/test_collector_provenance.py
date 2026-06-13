"""
Tests for collector soft-failure provenance (rank 2).

A transient fetch failure must be visible and distinguishable from a real
"no data" source — previously both silently became None, which is how partial
fetches wrote skeleton rows. Garmin session is mocked; no network.
"""


class _FakeGarmin:
    """Each method either returns a value or raises, per the spec dict."""

    def __init__(self, spec):
        self._spec = spec

    def _do(self, key):
        v = self._spec[key]
        if isinstance(v, Exception):
            raise v
        return v

    def get_sleep_data(self, *a, **k):        return self._do("sleep")
    def get_hrv_data(self, *a, **k):          return self._do("hrv")
    def get_user_summary(self, *a, **k):      return self._do("summary")
    def get_activities_by_date(self, *a, **k): return self._do("activities")
    def get_max_metrics(self, *a, **k):       return self._do("vo2max")


def _patch(monkeypatch, spec):
    from runforlife.sync import collector
    monkeypatch.setattr(collector, "get_session", lambda user: _FakeGarmin(spec))
    return collector


def test_provenance_marks_ok_empty_and_error(monkeypatch):
    collector = _patch(monkeypatch, {
        "sleep": {"dailySleepDTO": {}},   # ok
        "hrv": None,                       # empty
        "summary": ValueError("boom"),     # error (caught + logged)
        "activities": [],                  # ok (empty list is still a value)
        "vo2max": None,                    # empty
    })
    res = collector.collect_day("tezuesh", "2026-06-01", delay_seconds=0)
    prov = res["_provenance"]
    assert prov["sleep"] == "ok"
    assert prov["hrv"] == "empty"
    assert prov["summary"].startswith("error:")
    assert prov["activities"] == "ok"
    assert prov["vo2max"] == "empty"
    # The errored source is None in results, not a crash
    assert res["summary"] is None


def test_all_errors_do_not_crash(monkeypatch):
    err = RuntimeError("down")
    collector = _patch(monkeypatch, {k: err for k in ("sleep", "hrv", "summary", "activities", "vo2max")})
    res = collector.collect_day("tezuesh", "2026-06-01", delay_seconds=0)
    assert all(res[k] is None for k in ("sleep", "hrv", "summary", "activities", "vo2max"))
    assert all(v.startswith("error:") for v in res["_provenance"].values())
