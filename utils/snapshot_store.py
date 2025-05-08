import sqlite3
import pandas as pd
from datetime import datetime
import io

# Path to your SQLite DB file (relative to project root)
DB_PATH = "snapshots.db"

def init_db():
    """Initialize the SQLite database and create listings table if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zip_code TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        conn.commit()

def save_snapshot(zip_code, df):
    """
    Save a new snapshot of Zillow data for a given ZIP code.
    Stores the DataFrame as a JSON string.
    """
    df_json = df.to_json(orient="records")
    snapshot_date = datetime.now().strftime("%Y-%m-%d")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO listings (zip_code, snapshot_date, data)
            VALUES (?, ?, ?)
        """, (zip_code, snapshot_date, df_json))
        conn.commit()

def load_snapshot(zip_code, max_age_days=None):
    """
    Load the most recent snapshot for the given ZIP code.
    Optionally limit by `max_age_days` to ensure freshness.
    """
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT snapshot_date, data FROM listings
            WHERE zip_code = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
        """
        row = conn.execute(query, (zip_code,)).fetchone()

        if row:
            snapshot_date, data_json = row
            df = df = pd.read_json(io.StringIO(data_json))
            return df
        return None
