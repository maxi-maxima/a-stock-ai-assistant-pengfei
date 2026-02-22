class HedgeEngine:
    def __init__(self, data_skill):
        self.data_skill = data_skill

    def get_latest_price(self, code):
        try:
            df = self.data_skill.get_history(code, days=10)
            if df is not None and not df.empty:
                return float(df.iloc[-1]['close'])
        except Exception:
            pass
        return None

    def get_name(self, code):
        try:
            info = self.data_skill.get_stock_basic_info(code)
            if isinstance(info, dict):
                return info.get("name", code)
        except Exception:
            pass
        return code

    def portfolio_value(self, portfolio, price_cache=None):
        price_cache = price_cache or {}
        total = 0.0
        per_code = {}
        for code, info in portfolio.get_all_positions().items():
            if not isinstance(info, dict):
                continue
            vol = float(info.get("volume", 0) or 0)
            if vol <= 0:
                continue
            price = price_cache.get(code)
            if price is None:
                price = self.get_latest_price(code)
                price_cache[code] = price
            if price is None:
                price = float(info.get("cost", 0) or 0)
            val = vol * float(price or 0)
            per_code[code] = {"value": val, "price": price}
            total += val
        return total, per_code, price_cache

    def hedge_shares(self, portfolio_value, hedge_price, weight=1.0, hedge_ratio=1.0, lot=100):
        try:
            hedge_price = float(hedge_price)
        except Exception:
            return 0
        if hedge_price <= 0:
            return 0
        cash = float(portfolio_value) * float(weight) * float(hedge_ratio)
        if cash <= 0:
            return 0
        shares = int(cash / hedge_price / lot) * lot
        return max(0, shares)

    def suggest_index_hedge(self, exposure_ratio):
        """
        Simple index hedge suggestion based on exposure ratio.
        """
        if exposure_ratio >= 0.7:
            weight = 0.6
        elif exposure_ratio >= 0.4:
            weight = 0.4
        else:
            weight = 0.2
        return {
            "strategy": "指数对冲",
            "code": "510300.SH",
            "weight": weight,
            "ratio": 1.0
        }

    def suggest_industry_hedge(self, portfolio, top_n=2):
        """
        Suggest industry hedge legs based on concentration.
        """
        by_industry, _, _ = self.industry_exposure(portfolio)

        if not by_industry:
            return []
        # top industries
        top = sorted(by_industry.items(), key=lambda x: x[1], reverse=True)[:top_n]
        legs = []
        for ind, val in top:
            legs.append({
                "strategy": "行业对冲",
                "code": "512000.SH",  # default industry ETF placeholder
                "weight": 0.3,
                "ratio": 1.0,
                "industry": ind
            })
        return legs

    def industry_exposure(self, portfolio):
        """
        Return industry exposure mapping and top concentration ratio.
        """
        by_industry = {}
        total = 0.0
        for code, info in portfolio.get_all_positions().items():
            if not isinstance(info, dict):
                continue
            vol = float(info.get("volume", 0) or 0)
            if vol <= 0:
                continue
            price = self.get_latest_price(code) or float(info.get("cost", 0) or 0)
            val = vol * price
            industry = "未知"
            try:
                meta = self.data_skill.get_stock_basic_info(code)
                if isinstance(meta, dict):
                    industry = meta.get("industry", "未知")
            except Exception:
                pass
            by_industry[industry] = by_industry.get(industry, 0.0) + val
            total += val

        if not by_industry or total <= 0:
            return {}, 0.0, ""
        top_ind, top_val = sorted(by_industry.items(), key=lambda x: x[1], reverse=True)[0]
        top_ratio = top_val / total if total > 0 else 0.0
        return by_industry, top_ratio, top_ind
