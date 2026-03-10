import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "properties.db")
MAX_PROPERTIES = int(os.environ.get("MAX_PROPERTIES", 100))


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id          TEXT PRIMARY KEY,
                title       TEXT,
                price       INTEGER,
                location    TEXT,
                zip_code    TEXT,
                prop_type   TEXT,
                bedrooms    INTEGER,
                area        INTEGER,
                url         TEXT,
                image_url   TEXT,
                scraped_at  TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price ON properties(price)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_type  ON properties(prop_type)")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_property(prop: dict):
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO properties
              (id, title, price, location, zip_code, prop_type,
               bedrooms, area, url, image_url, scraped_at)
            VALUES
              (:id, :title, :price, :location, :zip_code, :prop_type,
               :bedrooms, :area, :url, :image_url, :scraped_at)
            """,
            prop,
        )
        # Keep DB within MAX_PROPERTIES limit — delete oldest rows by scraped_at
        conn.execute(
            """
            DELETE FROM properties WHERE id IN (
                SELECT id FROM properties ORDER BY scraped_at ASC
                LIMIT MAX(0, (SELECT COUNT(*) FROM properties) - ?)
            )
            """,
            (MAX_PROPERTIES,),
        )


def get_properties(
    min_price: int | None = None,
    max_price: int | None = None,
    prop_type: str | None = None,
    limit: int = 48,
    offset: int = 0,
) -> list[dict]:
    query = "SELECT * FROM properties WHERE price > 0"
    params: list = []
    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)
    if prop_type and prop_type != "all":
        query += " AND prop_type LIKE ?"
        params.append(f"%{prop_type}%")
    query += " ORDER BY price ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    with _conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM properties WHERE price > 0"
        ).fetchone()[0]
        row = conn.execute(
            "SELECT MIN(price), MAX(price) FROM properties WHERE price > 0"
        ).fetchone()
        return {
            "count": count,
            "min_price": row[0] or 0,
            "max_price": row[1] or 0,
        }
