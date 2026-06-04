"""Print hours since last enrichment (sf_features + bb_features), or 999 if none."""
from datetime import datetime, timezone
from src.db.db import connect
def _age(ts):
    if not ts: return 9999.0
    try: return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()/3600
    except Exception: return 9999.0
with connect() as c:
    a = c.execute("SELECT MAX(computed_at) FROM sf_features").fetchone()[0]
    try: b = c.execute("SELECT MAX(computed_at) FROM bb_features").fetchone()[0]
    except Exception: b = None
print(f"{min(_age(a), _age(b)):.1f}")
