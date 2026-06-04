"""Print hours since last enrichment. Standalone (no src import) so valuebot.bat can call it."""
import os, sqlite3
from datetime import datetime, timezone

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = os.environ.get("DB_PATH") or os.path.join(root, "data", "soccer_value.sqlite")
if not os.path.isabs(db):
    db = os.path.join(root, db)

def age(ts):
    if not ts: return 9999.0
    try: return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 3600
    except Exception: return 9999.0

try:
    c = sqlite3.connect(db)
    a = c.execute("SELECT MAX(computed_at) FROM sf_features").fetchone()[0]
    try: b = c.execute("SELECT MAX(computed_at) FROM bb_features").fetchone()[0]
    except Exception: b = None
    c.close()
    print(f"{min(age(a), age(b)):.1f}")
except Exception:
    print("9999")
