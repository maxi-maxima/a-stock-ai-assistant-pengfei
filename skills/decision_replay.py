import datetime
import json
import os

import pandas as pd

from core.experience_store import ExperienceStore
from skills.data_factory import DataSkillFactory


REPLAY_PATH = "data/decision_replay.jsonl"


class DecisionReplayer:
    def __init__(self, source="tushare"):
        self.data_skill = DataSkillFactory.get_skill(source)
        self.store = ExperienceStore()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(REPLAY_PATH), exist_ok=True)

    def _parse_date(self, ts):
        if isinstance(ts, datetime.datetime):
            return ts.date().isoformat()
        if isinstance(ts, str):
            return ts[:10]
        return ""

    def _find_index(self, df, date_str):
        if df is None or df.empty or "date" not in df.columns:
            return None
        try:
            idx = df.index[df["date"] >= date_str]
            if len(idx) == 0:
                return None
            return int(idx[0])
        except Exception:
            return None

    def _calc_forward_returns(self, df, start_idx, horizons):
        out = {}
        if start_idx is None:
            return out
        base = float(df.iloc[start_idx]["close"])
        for h in horizons:
            idx = start_idx + int(h)
            if idx >= len(df):
                out[str(h)] = None
                continue
            price = float(df.iloc[idx]["close"])
            if base <= 0:
                out[str(h)] = None
            else:
                out[str(h)] = (price - base) / base * 100
        return out

    def replay(self, limit=200, horizons=(1, 5, 10), save=True):
        events = self.store.load_events(limit=limit * 3)
        decisions = [e for e in events if isinstance(e, dict) and e.get("event") == "decision"]
        results = []
        for ev in decisions[-limit:]:
            payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
            code = payload.get("code")
            action = str(payload.get("action", "")).upper()
            if not code:
                continue
            ts = ev.get("ts")
            date_str = self._parse_date(ts)
            df = self.data_skill.get_history(code, days=180)
            if df is None or df.empty:
                continue
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
            idx = self._find_index(df, date_str)
            if idx is None:
                continue
            fwd = self._calc_forward_returns(df, idx, horizons)
            hit = {}
            for h, ret in fwd.items():
                if ret is None:
                    hit[h] = None
                elif action == "BUY":
                    hit[h] = ret > 0
                elif action == "SELL":
                    hit[h] = ret < 0
                else:
                    hit[h] = None
            row = {
                "ts": ts,
                "code": code,
                "action": action,
                "decision_id": payload.get("decision_id"),
                "forward_returns": fwd,
                "hit": hit
            }
            results.append(row)
        if save and results:
            self._ensure_dir()
            try:
                with open(REPLAY_PATH, "a", encoding="utf-8") as f:
                    for r in results:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return results
