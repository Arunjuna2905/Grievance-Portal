import pymysql
import pymysql.cursors
from flask import current_app, g


def get_db():
    if "db" not in g:
        cfg = current_app.config
        g.db = pymysql.connect(
            host=cfg["MYSQL_HOST"],
            port=cfg["MYSQL_PORT"],
            user=cfg["MYSQL_USER"],
            password=cfg["MYSQL_PASSWORD"],
            database=cfg["MYSQL_DATABASE"],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            charset="utf8mb4",
        )
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    """Create tables if they don't exist (runs on every startup safely)."""
    db = get_db()
    with current_app.open_resource("database/grievance_db.sql") as schema:
        sql = schema.read().decode("utf8")
    with db.cursor() as cur:
        # Execute each statement separately
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                cur.execute(stmt)
        try:
            cur.execute("ALTER TABLE complaints ADD COLUMN is_read TINYINT(1) NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN status_notifications_enabled TINYINT(1) NOT NULL DEFAULT 1")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE complaint_updates ADD COLUMN image_path VARCHAR(500)")
        except Exception:
            pass
    db.commit()
