import os

import psycopg2
from flask import Flask, jsonify


def _get_conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(database_url)


app = Flask(__name__)


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _cache_enabled() -> bool:
    return _env_flag("CACHE_ENABLED", "0")


def _cache_ttl_seconds() -> int:
    try:
        return max(1, int(os.environ.get("CACHE_TTL_PROFILE_SECONDS", "30")))
    except Exception:
        return 30


def _redis_client():
    if not _cache_enabled():
        return None
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/profile/<user_id>")
def profile(user_id: str):
    # Same stats as poll_manager/profile route, but served from a separate microservice.
    redis_client = _redis_client()
    cache_key = f"profile_stats:{user_id}"
    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return app.response_class(cached, mimetype="application/json")
        except Exception:
            pass

    with _get_conn() as conn:
        with conn.cursor() as cur:
            # 1) distinct polls you voted in
            cur.execute(
                "SELECT COUNT(DISTINCT poll_id) FROM votes WHERE user_id = %s",
                (user_id,),
            )
            (voted_polls_count,) = cur.fetchone()

            # 2) polls you created
            cur.execute(
                "SELECT COUNT(*) FROM polls WHERE created_by = %s",
                (user_id,),
            )
            (created_polls_count,) = cur.fetchone()

            # 3) total votes on polls you created
            cur.execute(
                "SELECT COUNT(*) FROM votes v JOIN polls p ON v.poll_id = p.id WHERE p.created_by = %s",
                (user_id,),
            )
            (created_polls_votes_count,) = cur.fetchone()

    payload = {
        "ok": True,
        "user_id": user_id,
        "voted_polls_count": int(voted_polls_count or 0),
        "created_polls_count": int(created_polls_count or 0),
        "created_polls_votes_count": int(created_polls_votes_count or 0),
    }

    if redis_client is not None:
        try:
            redis_client.setex(cache_key, _cache_ttl_seconds(), jsonify(payload).get_data(as_text=True))
        except Exception:
            pass

    return jsonify(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5002"))
    app.run(host="0.0.0.0", port=port)
