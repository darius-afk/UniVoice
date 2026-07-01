import os

import psycopg2
from flask import Flask, jsonify, request


def _get_conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(database_url)


app = Flask(__name__)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/promote/<int:poll_id>")
def promote(poll_id: int):
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "missing_user_id"}), 400

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT created_by, target_audience FROM polls WHERE id = %s",
                (poll_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"ok": False, "error": "poll_not_found"}), 404

            created_by, target_audience = row

            if created_by != user_id:
                return jsonify({"ok": False, "error": "not_creator"}), 403

            cur.execute("SELECT COUNT(*) FROM votes WHERE poll_id = %s", (poll_id,))
            (total_votes,) = cur.fetchone()

            if total_votes < 3:
                return jsonify({"ok": False, "error": "not_enough_votes", "total_votes": total_votes}), 400

            if (target_audience or "").strip() != "students":
                return jsonify({"ok": False, "error": "not_student_target", "target_audience": target_audience}), 400

            cur.execute(
                "UPDATE polls SET target_audience = 'all' WHERE id = %s",
                (poll_id,),
            )

    return jsonify({"ok": True, "poll_id": poll_id, "new_target_audience": "all"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port)
