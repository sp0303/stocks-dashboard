"""Angel account pool: throttling is retried once on the same account, the candle gate is
shared across accounts, and an auth error still re-authenticates exactly once."""
from app.services import angel


def _acct(name="primary"):
    a = angel._Account(name, "k", "c", "p", "t")
    a.candle_limiter = angel._RateLimiter(0, per_min=10_000, per_hour=10_000)
    a.quote_limiter = angel._RateLimiter(0, per_min=10_000, per_hour=10_000)
    return a


def _setup(monkeypatch, gate_ok=True):
    monkeypatch.setattr(angel, "_ensure_session", lambda acct: object())
    monkeypatch.setattr(angel, "_RATE_LIMIT_BACKOFF", 0)
    monkeypatch.setattr(angel, "_invalidate_session", lambda acct: None)
    gate = angel._RateLimiter(0, per_min=10_000 if gate_ok else 0, per_hour=10_000)
    monkeypatch.setattr(angel, "_CANDLE_GATE", gate)


def _seq(*responses):
    it = iter(responses)
    calls = []

    def fn(smart, params):
        calls.append(1)
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    return fn, calls


OK = {"status": True, "data": [["2026-10-30T00:00:00+05:30", 1, 1, 1, 1, 1]]}
THROTTLED = {"status": False, "message": "Access denied because of exceeding access rate"}


def test_throttle_is_retried_once_on_same_account(monkeypatch):
    _setup(monkeypatch)
    fn, calls = _seq(THROTTLED, OK)
    assert angel._call_account(_acct(), fn, {}, "candle", "getCandleData") == OK
    assert len(calls) == 2


def test_throttle_raised_as_exception_is_retried_too(monkeypatch):
    _setup(monkeypatch)
    fn, calls = _seq(Exception("Couldn't parse the JSON response: Access denied because of exceeding access rate"), OK)
    assert angel._call_account(_acct(), fn, {}, "candle", "getCandleData") == OK


def test_second_throttle_fails_over(monkeypatch):
    _setup(monkeypatch)
    fn, calls = _seq(THROTTLED, THROTTLED)
    assert angel._call_account(_acct(), fn, {}, "candle", "getCandleData") is angel._OVER_BUDGET
    assert len(calls) == 2


def test_shared_candle_gate_blocks_every_account(monkeypatch):
    _setup(monkeypatch, gate_ok=False)
    fn, calls = _seq(OK)
    for name in ("primary", "secondary"):
        assert angel._call_account(_acct(name), fn, {}, "candle", "getCandleData") is angel._OVER_BUDGET
    assert calls == []


def test_quotes_do_not_use_candle_gate(monkeypatch):
    _setup(monkeypatch, gate_ok=False)
    fn, _ = _seq(OK)
    assert angel._call_account(_acct(), fn, {}, "quote", "getMarketData") == OK


def test_auth_error_reauthenticates_once(monkeypatch):
    _setup(monkeypatch)
    bad = {"status": False, "errorCode": "AG8001", "message": "Invalid Token"}
    fn, calls = _seq(bad, bad)
    assert angel._call_account(_acct(), fn, {}, "candle", "getCandleData") == bad
    assert len(calls) == 2
