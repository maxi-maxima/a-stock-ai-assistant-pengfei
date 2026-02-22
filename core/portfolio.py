import json
import os
import pandas as pd

class VirtualPortfolio:
    def __init__(self, filepath="data/real_portfolio.json"):
        self.filepath = filepath
        self.data = {"principal": 100000, "positions": {}}
        self._load()

    def _normalize_code(self, code):
        return str(code).strip().upper()

    def _load(self):
        if not os.path.exists(self.filepath):
            self.data = {"principal": 100000, "positions": {}}
            self._save()
        else:
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                
                if 'positions' not in self.data: self.data['positions'] = {}
                dirty = False
                for code, info in list(self.data['positions'].items()):
                    if not isinstance(info, dict):
                        self.data['positions'][code] = {"volume": 0, "cost": 0.0}
                        dirty = True
                        continue
                    if 'volume' not in info:
                        info['volume'] = info.get('vol', 0)
                        dirty = True
                    if 'cost' not in info:
                        info['cost'] = 0.0
                        dirty = True
                    if 'meta' in info and not isinstance(info.get('meta'), dict):
                        info['meta'] = {}
                        dirty = True
                if dirty: self._save()
            except:
                self.data = {"principal": 100000, "positions": {}}

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    def update_fund(self, amount):
        self.data['principal'] = float(amount)
        self._save()

    def update_available(self, available):
        """
        Manually set available cash; principal will be adjusted based on current positions.
        """
        try:
            available = float(available)
        except Exception:
            return
        if available < 0:
            available = 0.0
        invested = 0.0
        for _, info in self.data.get('positions', {}).items():
            if not isinstance(info, dict):
                continue
            vol = float(info.get("volume", 0) or 0)
            cost = float(info.get("cost", 0) or 0)
            invested += vol * cost
        self.data['principal'] = float(available + invested)
        self._save()

    def update_position(self, code, volume, cost, meta=None):
        code = self._normalize_code(code)
        if float(volume) <= 0:
            self.remove_position(code)
        else:
            pos = self.data.get('positions', {}).get(code, {})
            meta_existing = pos.get("meta", {}) if isinstance(pos, dict) else {}
            meta_new = meta_existing
            if isinstance(meta, dict):
                meta_new = dict(meta_existing)
                meta_new.update(meta)
            record = {"volume": int(volume), "cost": float(cost)}
            if meta_new:
                record["meta"] = meta_new
            self.data['positions'][code] = record
            self._save()

    def add_position(self, code, volume, price, meta=None):
        """
        Add to position and update average cost.
        """
        code = self._normalize_code(code)
        try:
            volume = int(volume)
        except Exception:
            return False
        if volume <= 0:
            return False
        try:
            price = float(price)
        except Exception:
            return False

        pos = self.data.get('positions', {}).get(code, {"volume": 0, "cost": 0.0})
        curr_vol = int(pos.get("volume", 0) or 0)
        curr_cost = float(pos.get("cost", 0) or 0)
        meta_existing = pos.get("meta", {}) if isinstance(pos.get("meta"), dict) else {}
        new_vol = curr_vol + volume
        if new_vol <= 0:
            return False
        # weighted average cost
        if curr_vol > 0:
            new_cost = (curr_cost * curr_vol + price * volume) / new_vol
        else:
            new_cost = price
        meta_new = meta_existing
        if isinstance(meta, dict):
            meta_new = dict(meta_existing)
            meta_new.update(meta)
        record = {"volume": int(new_vol), "cost": float(new_cost)}
        if meta_new:
            record["meta"] = meta_new
        self.data['positions'][code] = record
        self._save()
        return True

    def remove_position(self, code):
        code = self._normalize_code(code)
        if code in self.data['positions']:
            del self.data['positions'][code]
            self._save()
            return True
        return False

    def sell_position(self, code, volume, price):
        code = self._normalize_code(code)
        if code not in self.data.get('positions', {}):
            return False
        try:
            vol = int(volume)
        except Exception:
            return False
        if vol <= 0:
            return False
        pos = self.data['positions'].get(code, {})
        curr_vol = int(pos.get("volume", 0) or 0)
        cost = float(pos.get("cost", 0) or 0)
        if curr_vol <= 0:
            return False
        if vol > curr_vol:
            vol = curr_vol
        try:
            price = float(price)
        except Exception:
            price = cost
        # realize PnL into principal
        pnl = (price - cost) * vol
        self.data['principal'] = float(self.data.get('principal', 0)) + pnl

        remain = curr_vol - vol
        meta_existing = pos.get("meta", {}) if isinstance(pos.get("meta"), dict) else {}
        if remain <= 0:
            self.remove_position(code)
        else:
            record = {"volume": int(remain), "cost": float(cost)}
            if meta_existing:
                record["meta"] = meta_existing
            self.data['positions'][code] = record
            self._save()
        return True

    def get_fund_info(self):
        principal = float(self.data.get('principal', 100000))
        invested = 0.0
        for _, info in self.data.get('positions', {}).items():
            if not isinstance(info, dict):
                continue
            vol = float(info.get("volume", 0) or 0)
            cost = float(info.get("cost", 0) or 0)
            invested += vol * cost
        available = principal - invested
        if available < 0:
            available = 0.0
        return {
            "principal": principal,
            "cash": available,
            "available": available,
            "invested": invested
        }

    def get_all_positions(self):
        return self.data.get('positions', {})

    def get_balance(self):
        return float(self.get_fund_info().get("available", 0.0))

    def get_positions(self):
        rows = []
        for code, info in self.get_all_positions().items():
            if not isinstance(info, dict):
                continue
            rows.append({
                "stock_code": code,
                "amount": int(info.get("volume", 0)),
                "avg_cost": float(info.get("cost", 0.0))
            })
        return pd.DataFrame(rows, columns=["stock_code", "amount", "avg_cost"])

    def get_specific_position(self, query_code):
        positions = self.data.get('positions', {})
        query = self._normalize_code(query_code)
        if query in positions: return positions[query]
        
        query_pure = query.split('.')[0]
        for k, v in positions.items():
            if k.split('.')[0] == query_pure:
                return v
        return None

    def get_position_value_map(self, price_map=None):
        """
        Estimate position values using price_map (code->price).
        If price missing, fallback to cost.
        """
        price_map = price_map or {}
        per_code = {}
        total = 0.0
        for code, info in self.get_all_positions().items():
            if not isinstance(info, dict):
                continue
            vol = float(info.get("volume", 0) or 0)
            price = float(price_map.get(code, info.get("cost", 0) or 0))
            value = vol * price
            per_code[code] = value
            total += value
        return per_code, total
