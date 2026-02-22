import datetime
import json
import os
import sqlite3


DB_PATH = "data/event_index.db"
STATE_PATH = "data/event_index_state.json"
EVENT_BUS_PATH = "data/event_bus.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            ts TEXT,
            code TEXT,
            event TEXT,
            action TEXT,
            suggested_action TEXT,
            pnl REAL,
            pnl_pct REAL,
            tags TEXT,
            payload TEXT
        )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_code ON events(code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
    conn.commit()
    conn.close()


def _load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _safe_json(obj, limit=2000):
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    if limit and isinstance(s, str) and len(s) > limit:
        return s[:limit] + "..."
    return s


def update_index(max_lines=5000):
    if not os.path.exists(EVENT_BUS_PATH):
        return 0
    _ensure_db()
    state = _load_state()
    try:
        offset = int(state.get("byte_offset", 0) or 0)
    except Exception:
        offset = 0
    inserted = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        with open(EVENT_BUS_PATH, "rb") as f:
            if offset > 0:
                try:
                    f.seek(offset)
                except Exception:
                    offset = 0
                    f.seek(0)
            for line in f:
                if not line:
                    continue
                try:
                    rec = json.loads(line.decode("utf-8", errors="ignore").strip() or "{}")
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                event_id = rec.get("event_id") or rec.get("id")
                if not event_id:
                    continue
                payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
                tags = payload.get("context_tags") or []
                if isinstance(tags, list):
                    tags_str = ",".join([str(t) for t in tags])
                else:
                    tags_str = str(tags or "")
                action = payload.get("action") or ""
                suggested_action = payload.get("suggested_action") or ""
                pnl = payload.get("pnl")
                pnl_pct = payload.get("pnl_pct")
                c.execute(
                    "INSERT OR IGNORE INTO events (event_id, ts, code, event, action, suggested_action, pnl, pnl_pct, tags, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(event_id),
                        str(rec.get("ts") or ""),
                        str(rec.get("code") or ""),
                        str(rec.get("event") or ""),
                        str(action),
                        str(suggested_action),
                        pnl,
                        pnl_pct,
                        tags_str,
                        _safe_json(payload)
                    )
                )
                inserted += 1
                if max_lines and inserted >= max_lines:
                    break
            new_offset = f.tell()
    except Exception:
        conn.commit()
        conn.close()
        return 0
    conn.commit()
    conn.close()
    state = {
        "byte_offset": new_offset,
        "updated_at": _now(),
        "last_batch": inserted
    }
    _save_state(state)
    return inserted


def _to_datestr(val):
    if not val:
        return ""
    if isinstance(val, datetime.date):
        return val.isoformat()
    if isinstance(val, str):
        return val[:10]
    return ""


def query_events(code=None, query_text="", start_date=None, end_date=None, limit=100):
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        where = []
        params = []
        if code:
            where.append("code LIKE ?")
            params.append(f"%{str(code).strip()}%")
        if query_text:
            where.append("(payload LIKE ? OR tags LIKE ? OR event LIKE ?)")
            q = f"%{str(query_text).strip()}%"
            params.extend([q, q, q])
        sql = "SELECT ts, code, event, action, suggested_action, pnl, pnl_pct, tags, payload FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(int(limit))
        rows = c.execute(sql, params).fetchall()
        conn.close()
    except Exception:
        return []

    start_s = _to_datestr(start_date)
    end_s = _to_datestr(end_date)
    out = []
    for ts, code, ev, action, s_action, pnl, pnl_pct, tags, payload in rows:
        if start_s and str(ts)[:10] < start_s:
            continue
        if end_s and str(ts)[:10] > end_s:
            continue
        out.append({
            "ts": ts,
            "code": code,
            "event": ev,
            "action": action,
            "suggested_action": s_action,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "tags": tags,
            "payload": payload
        })
    return out


def query_context(code=None, query_text="", limit=3, start_date=None, end_date=None):
    if not os.path.exists(DB_PATH):
        return []
    rows = query_events(code=code, query_text=query_text, start_date=start_date, end_date=end_date, limit=limit)
    out = []
    for row in rows:
        ts = row.get("ts")
        code = row.get("code")
        ev = row.get("event")
        action = row.get("action")
        s_action = row.get("suggested_action")
        pnl = row.get("pnl")
        pnl_pct = row.get("pnl_pct")
        tags = row.get("tags")
        if ev == "decision":
            line = f"{ts} {code}: decision action={action} suggested={s_action} tags={tags}"
        elif ev == "outcome":
            line = f"{ts} {code}: outcome pnl={pnl} pnl_pct={pnl_pct}"
        else:
            line = f"{ts} {code}: {ev}"
        out.append(line.strip())
    return out
