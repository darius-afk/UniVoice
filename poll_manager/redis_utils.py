from __future__ import annotations

import os
from typing import Any


def _redis_url() -> str | None:
    url = os.environ.get("REDIS_URL")
    return url.strip() if url and url.strip() else None


def get_redis():
    """Returns a redis client if REDIS_URL is set, otherwise None."""
    url = _redis_url()
    if not url:
        return None

    # Lazy import so local dev/tests without redis don't fail.
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


_RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


def rate_limit_increment(redis_client: Any, key: str, *, window_seconds: int) -> tuple[int, int]:
    """Atomically increments a rate-limit counter and returns (count, ttl_seconds)."""
    res = redis_client.eval(_RATE_LIMIT_LUA, 1, key, int(window_seconds))
    # redis-py returns list[str|int]
    count = int(res[0])
    ttl = int(res[1])
    return count, ttl
