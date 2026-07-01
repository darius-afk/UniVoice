import json

import redis_utils


class FakeRedisForRateLimit:
    def __init__(self):
        self._now = 1_000_000
        self._data = {}  # key -> (count:int, expires_at:int)

    def advance(self, seconds: int):
        self._now += int(seconds)

    def eval(self, _lua: str, _numkeys: int, key: str, window_seconds: int):
        window_seconds = int(window_seconds)

        # Expire key if needed
        if key in self._data:
            count, expires_at = self._data[key]
            if expires_at <= self._now:
                del self._data[key]

        if key not in self._data:
            count = 0
            expires_at = self._now + window_seconds
        else:
            count, expires_at = self._data[key]

        count += 1
        # If this is the first increment, set expiry (mimics the Lua)
        if count == 1:
            expires_at = self._now + window_seconds

        self._data[key] = (count, expires_at)
        ttl = max(-1, expires_at - self._now)
        return [count, ttl]


# Test: rate_limit_increment crește atomic și resetează după fereastra de timp.
def test_rate_limit_increment_resets_after_window():
    r = FakeRedisForRateLimit()
    key = "rl:login:ip:127.0.0.1"

    c1, ttl1 = redis_utils.rate_limit_increment(r, key, window_seconds=10)
    assert c1 == 1
    assert 0 <= ttl1 <= 10

    r.advance(1)
    c2, ttl2 = redis_utils.rate_limit_increment(r, key, window_seconds=10)
    assert c2 == 2
    assert ttl2 <= ttl1

    r.advance(20)
    c3, ttl3 = redis_utils.rate_limit_increment(r, key, window_seconds=10)
    assert c3 == 1
    assert 0 <= ttl3 <= 10


class FakeRedisKV:
    def __init__(self):
        self._kv = {}

    def get(self, key: str):
        return self._kv.get(key)

    def setex(self, key: str, _ttl_seconds: int, value: str):
        self._kv[key] = value


class _FakeCursor:
    def __init__(self, results):
        self._results = list(results)

    def execute(self, _sql, _params=None):
        return None

    def fetchone(self):
        return (self._results.pop(0),)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, results):
        self._results = results

    def cursor(self):
        return _FakeCursor(self._results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


# Test: profile_service pune răspunsul în cache și apoi servește din cache.
def test_profile_service_caches_profile_response(monkeypatch):
    import profile_service.app as ps

    fake_redis = FakeRedisKV()
    monkeypatch.setattr(ps, "_redis_client", lambda: fake_redis)

    db_calls = {"n": 0}

    def _fake_get_conn():
        db_calls["n"] += 1
        # voted_polls_count, created_polls_count, created_polls_votes_count
        return _FakeConn([2, 1, 7])

    monkeypatch.setattr(ps, "_get_conn", _fake_get_conn)

    client = ps.app.test_client()

    # First call => DB + cache
    resp1 = client.get("/profile/u1")
    assert resp1.status_code == 200
    body1 = json.loads(resp1.get_data(as_text=True))
    assert body1["ok"] is True
    assert body1["user_id"] == "u1"
    assert body1["voted_polls_count"] == 2
    assert db_calls["n"] == 1

    # Second call => should hit cache and NOT call DB again
    resp2 = client.get("/profile/u1")
    assert resp2.status_code == 200
    body2 = json.loads(resp2.get_data(as_text=True))
    assert body2 == body1
    assert db_calls["n"] == 1

    # Cache key exists
    assert fake_redis.get("profile_stats:u1") is not None
