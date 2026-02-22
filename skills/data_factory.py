import os
import json
import pandas as pd
import numpy as np
try:
    import tushare as ts
except Exception:
    ts = None
try:
    import akshare as ak
except Exception:
    ak = None
import yaml
import datetime
import time
import warnings
from core.ta_utils import resolve_ma_periods, ma_series
from core.env_loader import is_placeholder_value

warnings.filterwarnings("ignore")

NAME_CACHE_PATH = os.path.join("data", "stock_name_cache.json")
_AK_NAME_CACHE = None
_AK_NAME_FAILED = False

class TushareConnector:
    def __init__(self):
        self.pro = None
        self.token = ""
        self.source_name = "Tushare Pro (All-in-One)"
        self._init_token()
        self._trade_cal_cache = {"ts": 0, "last_open": None}
        self._name_cache = None

    def _init_token(self):
        try:
            # Priority: ENV > secure_settings.json > config/llm_config.yaml
            env_token = os.getenv("TUSHARE_TOKEN", "").strip()
            if env_token and not is_placeholder_value(env_token):
                self.token = env_token
            else:
                # secure storage (system page writes here)
                try:
                    if os.path.exists("data/secure_settings.json"):
                        with open("data/secure_settings.json", "r", encoding="utf-8") as f:
                            data = json.load(f)
                        self.token = str(data.get("tushare_token", "") or "").strip()
                except Exception:
                    self.token = ""
                if not self.token:
                    with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                        conf = yaml.safe_load(f)
                        self.token = conf.get('system', {}).get('tushare_token', '')
            if ts is None:
                return
            if self.token:
                ts.set_token(self.token)
                self.pro = ts.pro_api()
        except: pass

    def _get_date_range(self, days=30):
        end = datetime.datetime.now().strftime("%Y%m%d")
        start = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
        return start, end
    
    def _get_datetime_range(self, hours=24):
        now = datetime.datetime.now()
        end = now.strftime("%Y-%m-%d %H:%M:%S")
        start = (now - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        return start, end
    
    def _format_code(self, code):
        code = str(code).strip()
        if code.isdigit():
            if code.startswith('6'): return f"{code}.SH"
            if code.startswith('0') or code.startswith('3'): return f"{code}.SZ"
        return code

    def _load_name_cache(self):
        if self._name_cache is not None:
            return
        self._name_cache = {}
        try:
            if os.path.exists(NAME_CACHE_PATH):
                with open(NAME_CACHE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._name_cache = {str(k).strip().upper(): str(v) for k, v in data.items() if k and v}
        except Exception:
            self._name_cache = {}

    def _save_name_cache(self):
        if self._name_cache is None:
            return
        try:
            os.makedirs(os.path.dirname(NAME_CACHE_PATH), exist_ok=True)
            with open(NAME_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._name_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _cache_name(self, code, name):
        if not code or not name:
            return
        self._load_name_cache()
        if self._name_cache is None:
            self._name_cache = {}
        code_str = str(code).strip().upper()
        name_str = str(name).strip()
        if not name_str:
            return
        self._name_cache[code_str] = name_str
        digits = "".join([c for c in code_str if c.isdigit()])
        if digits:
            self._name_cache.setdefault(digits, name_str)
        self._save_name_cache()

    def _get_cached_name(self, code):
        if not code:
            return None
        self._load_name_cache()
        if not self._name_cache:
            return None
        code_str = str(code).strip().upper()
        if code_str in self._name_cache:
            return self._name_cache.get(code_str)
        digits = "".join([c for c in code_str if c.isdigit()])
        if digits and digits in self._name_cache:
            return self._name_cache.get(digits)
        return None

    def _get_akshare_name(self, code):
        global _AK_NAME_CACHE, _AK_NAME_FAILED
        if ak is None or _AK_NAME_FAILED:
            return None
        if _AK_NAME_CACHE is None:
            try:
                df = ak.stock_info_a_code_name()
                if df is None or df.empty:
                    _AK_NAME_FAILED = True
                    return None
                cols = list(df.columns)
                code_col = None
                name_col = None
                for c in ["code", "代码", "symbol", "ts_code"]:
                    if c in cols:
                        code_col = c
                        break
                for c in ["name", "名称", "简称"]:
                    if c in cols:
                        name_col = c
                        break
                if not code_col or not name_col:
                    _AK_NAME_FAILED = True
                    return None
                name_map = {}
                for _, row in df[[code_col, name_col]].iterrows():
                    rc = str(row.get(code_col, "")).strip()
                    rn = str(row.get(name_col, "")).strip()
                    if not rc or not rn:
                        continue
                    ts_code = self._format_code(rc).upper()
                    name_map[ts_code] = rn
                    name_map[rc.upper()] = rn
                _AK_NAME_CACHE = name_map
                # persist to local cache for future offline use
                if name_map:
                    self._load_name_cache()
                    if self._name_cache is None:
                        self._name_cache = {}
                    for k, v in name_map.items():
                        if k and v and k not in self._name_cache:
                            self._name_cache[k] = v
                    self._save_name_cache()
            except Exception:
                _AK_NAME_FAILED = True
                return None

        if not _AK_NAME_CACHE:
            return None
        code_str = self._format_code(code).upper()
        name = _AK_NAME_CACHE.get(code_str)
        if name:
            return name
        digits = "".join([c for c in code_str if c.isdigit()])
        if digits:
            return _AK_NAME_CACHE.get(digits)
        return None

    def _df_to_records(self, df, limit=20):
        if df is None or df.empty:
            return []
        try:
            return df.head(limit).to_dict("records")
        except Exception:
            return []

    def _get_last_trade_date(self):
        now = time.time()
        if self._trade_cal_cache["last_open"] and (now - self._trade_cal_cache["ts"] < 3600):
            return self._trade_cal_cache["last_open"]
        if not self.pro:
            return None
        try:
            end = datetime.datetime.now().strftime("%Y%m%d")
            start = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y%m%d")
            cal = self.pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open=1)
            if cal is not None and not cal.empty:
                last = cal.iloc[-1]['cal_date']
                last_dt = datetime.datetime.strptime(str(last), "%Y%m%d").date()
                self._trade_cal_cache = {"ts": now, "last_open": last_dt}
                return last_dt
        except Exception:
            pass
        return None

    def _normalize_history(self, df):
        if df is None or df.empty:
            return pd.DataFrame()
        # 统一列结构
        cols = ['date', 'open', 'close', 'high', 'low', 'vol', 'pct_chg']
        df = df.copy()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        # 数值列强制转换
        for c in cols:
            if c in df.columns and c != 'date':
                df[c] = pd.to_numeric(df[c], errors='coerce')
        # 去重、排序、清理
        if 'date' in df.columns:
            df = df.dropna(subset=['date'])
            df = df.drop_duplicates(subset=['date'])
            df = df.sort_values('date')
        if all(c in df.columns for c in cols):
            df = df[cols]
        return df.dropna(subset=['open', 'close', 'high', 'low'])

# 1. 基础行情
class MarketData(TushareConnector):
    _cache = {}
    _cache_ttl = 300  # seconds
    _disk_cache_dir = os.path.join("data", "cache", "history")

    def _cache_path(self, ts_code, days):
        safe_code = str(ts_code).replace("/", "_").replace("\\", "_").replace(":", "_")
        return os.path.join(self._disk_cache_dir, f"{safe_code}_{int(days)}.csv")

    def _load_disk_cache(self, ts_code, days):
        path = self._cache_path(ts_code, days)
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            return self._normalize_history(df)
        except Exception:
            return pd.DataFrame()

    def _save_disk_cache(self, ts_code, days, df):
        if df is None or df.empty:
            return
        try:
            os.makedirs(self._disk_cache_dir, exist_ok=True)
            path = self._cache_path(ts_code, days)
            df.to_csv(path, index=False)
        except Exception:
            pass

    def get_history(self, code, days=365):
        ts_code = self._format_code(code)
        s, e = self._get_date_range(days)
        cache_key = (ts_code, days)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached["ts"] < self._cache_ttl):
            return cached["df"].copy()
        if self.pro:
            try:
                if ts_code == '000001.SH':
                    df = self.pro.index_daily(ts_code=ts_code, start_date=s, end_date=e)
                    df = df.rename(columns={'trade_date':'date','vol':'vol'}).sort_values('date')
                else:
                    df = ts.pro_bar(ts_code=ts_code, adj='qfq', start_date=s, end_date=e, api=self.pro)
                    if df is not None: df = df.rename(columns={'trade_date':'date'}).sort_values('date')
                if df is not None and not df.empty:
                    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                    df = df[['date', 'open', 'close', 'high', 'low', 'vol', 'pct_chg']]
                    df = self._normalize_history(df)
                    self._cache[cache_key] = {"ts": now, "df": df}
                    self._save_disk_cache(ts_code, days, df)
                    return df.copy()
            except: pass
        try:
            if ak is None:
                return self._load_disk_cache(ts_code, days)
            symbol = ts_code.split('.')[0]
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=s, end_date=e, adjust="qfq")
            if not df.empty:
                df = df.rename(columns={'日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'vol', '涨跌幅': 'pct_chg'})
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                df = df[['date', 'open', 'close', 'high', 'low', 'vol', 'pct_chg']]
                df = self._normalize_history(df)
                self._cache[cache_key] = {"ts": now, "df": df}
                self._save_disk_cache(ts_code, days, df)
                return df.copy()
        except: pass
        return self._load_disk_cache(ts_code, days)

    def get_history_weekly(self, code, weeks=104):
        ts_code = self._format_code(code)
        if self.pro:
            try:
                df = self.pro.weekly(ts_code=ts_code, start_date=None, end_date=None)
                if df is not None and not df.empty:
                    df = df.rename(columns={'trade_date':'date'}).sort_values('date')
                    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                    df = df[['date', 'open', 'close', 'high', 'low', 'vol', 'pct_chg']]
                    return self._normalize_history(df).tail(weeks)
            except Exception:
                pass
        # fallback: resample daily
        df = self.get_history(code, days=weeks*7)
        if df.empty: return df
        df['date'] = pd.to_datetime(df['date'])
        w = df.set_index('date').resample('W').agg({
            'open': 'first', 'close': 'last', 'high': 'max', 'low': 'min', 'vol': 'sum', 'pct_chg': 'sum'
        }).dropna().reset_index()
        w['date'] = w['date'].dt.strftime('%Y-%m-%d')
        return w

    def get_history_monthly(self, code, months=36):
        ts_code = self._format_code(code)
        if self.pro:
            try:
                df = self.pro.monthly(ts_code=ts_code, start_date=None, end_date=None)
                if df is not None and not df.empty:
                    df = df.rename(columns={'trade_date':'date'}).sort_values('date')
                    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                    df = df[['date', 'open', 'close', 'high', 'low', 'vol', 'pct_chg']]
                    return self._normalize_history(df).tail(months)
            except Exception:
                pass
        df = self.get_history(code, days=months*30)
        if df.empty: return df
        df['date'] = pd.to_datetime(df['date'])
        m = df.set_index('date').resample('M').agg({
            'open': 'first', 'close': 'last', 'high': 'max', 'low': 'min', 'vol': 'sum', 'pct_chg': 'sum'
        }).dropna().reset_index()
        m['date'] = m['date'].dt.strftime('%Y-%m-%d')
        return m
    
    def get_market_index(self):
        try:
            df = self.get_history("000001.SH", days=30)
            if not df.empty:
                latest = df.iloc[-1]
                periods = resolve_ma_periods()
                p_mid1 = periods.get('mid1', 20)
                ma20 = ma_series(df['close'], p_mid1).iloc[-1]
                trend = "牛市" if latest['close'] > ma20 else "熊市"
                return {"trend": trend, "pct_chg": latest['pct_chg'], "vol_status": "放量" if latest['vol'] > df['vol'].mean() else "缩量"}
        except: pass
        return {}

    def get_stock_basic_info(self, code):
        info = {"name": code, "industry": "未知", "area": "未知", "market": "未知"}
        ts_code = self._format_code(code)
        cached = self._get_cached_name(ts_code)
        if cached:
            info["name"] = cached
        if not self.pro:
            # AkShare fallback
            try:
                ak_name = self._get_akshare_name(ts_code)
                if ak_name:
                    info["name"] = ak_name
                    self._cache_name(ts_code, ak_name)
            except Exception:
                pass
            return info
        try:
            df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,area,market,list_date')
            if not df.empty:
                row = df.iloc[0]
                info = {"name": row['name'], "industry": row['industry'], "area": row['area'], "market": row['market'], "list_date": row['list_date']}
                self._cache_name(ts_code, row['name'])
        except: pass
        return info

    def get_all_stocks(self):
        if not self.pro: return []
        try:
            df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name')
            if df.empty: return []
            df = df[~df['name'].str.contains('ST')]
            # 仅保留沪深A股 + 创业板（排除科创板 68）
            valid_starts = ('00', '30', '60')
            df = df[df['symbol'].str.startswith(valid_starts)]
            return df.rename(columns={'ts_code': 'code'}).to_dict('records')
        except: return []

# 2. 资金流向
class CapitalData(TushareConnector):
    def get_individual_money_flow(self, code):
        if not self.pro: return {}
        try:
            ts_code = self._format_code(code)
            s, e = self._get_date_range(days=10)
            df = self.pro.moneyflow(ts_code=ts_code, start_date=s, end_date=e)
            if not df.empty:
                df = df.sort_values('trade_date', ascending=False)
                row = df.iloc[0]
                buy_main = row.get('buy_elg_amount', 0) + row.get('buy_lg_amount', 0)
                sell_main = row.get('sell_elg_amount', 0) + row.get('sell_lg_amount', 0)
                net_main = buy_main - sell_main
                buy_retail = row.get('buy_md_amount', 0) + row.get('buy_sm_amount', 0)
                sell_retail = row.get('sell_md_amount', 0) + row.get('sell_sm_amount', 0)
                net_retail = buy_retail - sell_retail
                return {
                    "net_mf_amount": row.get('net_mf_amount', 0),
                    "main_force_net": net_main,
                    "retail_net": net_retail,
                    "trade_date": row.get('trade_date')
                }
        except: pass 
        return {"net_mf_amount": 0, "main_force_net": 0, "retail_net": 0}
    
    def get_sector_money_flow(self):
        if not self.pro: return []
        try:
            trade_date = datetime.datetime.now().strftime("%Y%m%d")
            df = self.pro.moneyflow_ind_dc(trade_date=trade_date, fields='trade_date,name,pct_change,net_amount,rank')
            if df.empty:
                yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
                df = self.pro.moneyflow_ind_dc(trade_date=yesterday, fields='trade_date,name,pct_change,net_amount,rank')
            if not df.empty: return df.sort_values('net_amount', ascending=False).head(5)[['name', 'net_amount', 'pct_change']].to_dict('records')
        except: pass
        return []

# 3. 筹码分布
class ChipData(TushareConnector):
    def get_cyq_perf(self, code):
        ts_code = self._format_code(code)
        if self.pro:
            try:
                s, e = self._get_date_range(days=10)
                df = self.pro.cyq_perf(ts_code=ts_code, start_date=s, end_date=e)
                if not df.empty:
                    df = df.sort_values('trade_date', ascending=False)
                    l = df.iloc[0]
                    win_rate = l.get('winner_rate', 0)
                    cost_low = l.get('cost_5pct', 0)
                    cost_high = l.get('cost_95pct', 0)
                    return {"win_rate": win_rate, "cost_low": cost_low, "cost_high": cost_high}
            except: pass

        try:
            market = MarketData()
            df = market.get_history(code, days=60)
            if not df.empty and len(df) > 1:
                current_price = df.iloc[-1]['close']
                total_vol = df['vol'].sum()
                if total_vol > 0:
                    df['avg_price'] = (df['open'] + df['close']) / 2
                    profitable_vol = df[df['avg_price'] < current_price]['vol'].sum()
                    win_rate = (profitable_vol / total_vol) * 100
                    cost_low = df['low'].min()
                    cost_high = df['high'].max()
                    return {
                        "win_rate": round(win_rate, 2),
                        "cost_low": round(cost_low, 2),
                        "cost_high": round(cost_high, 2)
                    }
        except: pass
        return {"win_rate": 0, "cost_low": 0, "cost_high": 0}

# 4. 个股新闻
class NewsData(TushareConnector):
    def get_stock_news(self, code):
        try:
            if ak is None:
                return ["暂无最新个股新闻"]
            symbol = code.split('.')[0]
            df = ak.stock_news_em(symbol=symbol)
            if df is not None: return [f"[{r.get('发布时间','')}] {r.get('新闻标题','')}" for _, r in df.head(5).iterrows()]
        except: pass
        return ["暂无最新个股新闻"]
    def get_cctv_news(self): return []

# 5. 基本面
class FundamentalData(TushareConnector):
    def get_valuation(self, code):
        if not self.pro: return {}
        try:
            c = self._format_code(code)
            df = self.pro.daily_basic(ts_code=c, fields='pe,pb,total_mv')
            if not df.empty: return {"PE": df.iloc[0]['pe'], "PB": df.iloc[0]['pb']}
        except: pass
        return {}

# 🔥 新增：财务数据类 (FinancialData)
class FinancialData(TushareConnector):
    def get_income_statement(self, code, period=None, with_error=False):
        """
        获取利润表
        period: 报告期 YYYYMMDD (如 20231231)，为空则获取最近的所有报告
        """
        if not self.pro:
            return (pd.DataFrame(), "Tushare 未连接或 token 无效") if with_error else pd.DataFrame()
        ts_code = self._format_code(code)
        
        # 核心字段筛选，防止列太多撑爆屏幕
        fields = 'ts_code,ann_date,end_date,total_revenue,n_income,basic_eps,total_cogs,oper_cost,sell_exp,admin_exp,rd_exp,fin_exp'
        
        try:
            if period:
                # 获取指定季度
                df = self.pro.income(ts_code=ts_code, period=period, fields=fields)
            else:
                # 获取最近历史 (比如最近 2 年)
                s, e = self._get_date_range(days=730)
                df = self.pro.income(ts_code=ts_code, start_date=s, end_date=e, fields=fields)
            
            if not df.empty:
                # 排序
                df = df.sort_values('end_date', ascending=False)
                return (df, "") if with_error else df
        except Exception as e:
            return (pd.DataFrame(), f"接口异常: {e}") if with_error else pd.DataFrame()
        return (pd.DataFrame(), "无数据") if with_error else pd.DataFrame()

    def get_forecast(self, code, with_error=False):
        """
        获取业绩预告 (最近一年)
        """
        if not self.pro:
            return (pd.DataFrame(), "Tushare 未连接或 token 无效") if with_error else pd.DataFrame()
        ts_code = self._format_code(code)
        try:
            s, e = self._get_date_range(days=365)
            df = self.pro.forecast(ts_code=ts_code, start_date=s, end_date=e)
            if not df.empty:
                df = df.sort_values('ann_date', ascending=False)
                return (df, "") if with_error else df
        except Exception as e:
            return (pd.DataFrame(), f"接口异常: {e}") if with_error else pd.DataFrame()
        return (pd.DataFrame(), "无数据") if with_error else pd.DataFrame()

    def get_balance_sheet(self, code, period=None, with_error=False):
        """
        获取资产负债表
        """
        if not self.pro:
            return (pd.DataFrame(), "Tushare 未连接或 token 无效") if with_error else pd.DataFrame()
        ts_code = self._format_code(code)
        fields = 'ts_code,ann_date,end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int,accounts_receiv,inventories,monetary_cap'
        try:
            if period:
                df = self.pro.balancesheet(ts_code=ts_code, period=period, fields=fields)
            else:
                s, e = self._get_date_range(days=730)
                df = self.pro.balancesheet(ts_code=ts_code, start_date=s, end_date=e, fields=fields)
            if not df.empty:
                df = df.sort_values('end_date', ascending=False)
                return (df, "") if with_error else df
        except Exception as e:
            return (pd.DataFrame(), f"接口异常: {e}") if with_error else pd.DataFrame()
        return (pd.DataFrame(), "无数据") if with_error else pd.DataFrame()

    def get_cashflow(self, code, period=None, with_error=False):
        """
        获取现金流量表
        """
        if not self.pro:
            return (pd.DataFrame(), "Tushare 未连接或 token 无效") if with_error else pd.DataFrame()
        ts_code = self._format_code(code)
        fields = 'ts_code,ann_date,end_date,n_cashflow_act,n_cashflow_inv,n_cashflow_fin,net_cash_flows_oper_act'
        try:
            if period:
                df = self.pro.cashflow(ts_code=ts_code, period=period, fields=fields)
            else:
                s, e = self._get_date_range(days=730)
                df = self.pro.cashflow(ts_code=ts_code, start_date=s, end_date=e, fields=fields)
            if not df.empty:
                df = df.sort_values('end_date', ascending=False)
                return (df, "") if with_error else df
        except Exception as e:
            return (pd.DataFrame(), f"接口异常: {e}") if with_error else pd.DataFrame()
        return (pd.DataFrame(), "无数据") if with_error else pd.DataFrame()

# 6. 聪明钱
class FundData(TushareConnector):
    def get_smart_money(self): return []

# 7. 技术因子
class TechnicalCalculator:
    @staticmethod
    def calculate(df):
        if df.empty or len(df) < 26: return {}
        periods = resolve_ma_periods()
        p_mid1 = periods.get('mid1', 20)
        df['ma20'] = ma_series(df['close'], p_mid1)
        df['std20'] = df['close'].rolling(p_mid1).std()
        df['up'] = df['ma20'] + 2 * df['std20']
        df['dn'] = df['ma20'] - 2 * df['std20']
        prev_close = df['close'].shift(1)
        h_l = df['high'] - df['low']
        h_pc = (df['high'] - prev_close).abs()
        l_pc = (df['low'] - prev_close).abs()
        df['tr'] = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()
        low_list = df['low'].rolling(9, min_periods=9).min()
        high_list = df['high'].rolling(9, min_periods=9).max()
        rsv = (df['close'] - low_list) / (high_list - low_list) * 100
        df['k'] = rsv.ewm(com=2).mean()
        df['d'] = df['k'].ewm(com=2).mean()
        df['j'] = 3 * df['k'] - 2 * df['d']
        latest = df.iloc[-1]
        return {"boll_up": float(latest['up']), "boll_mid": float(latest['ma20']), "boll_low": float(latest['dn']), "atr": float(latest['atr']), "kdj": f"K:{latest['k']:.1f} D:{latest['d']:.1f}"}

# 8. 宏观数据
class MacroData(TushareConnector):
    def get_global_indices(self):
        indices = {
            "A50 (XIN9)": {"code": "XIN9", "price": 0, "pct": 0},
            "恒生指数 (HSI)": {"code": "HSI", "price": 0, "pct": 0},
            "道琼斯 (DJI)": {"code": "DJI", "price": 0, "pct": 0},
            "纳斯达克 (IXIC)": {"code": "IXIC", "price": 0, "pct": 0}
        }
        if not self.pro: return indices
        try:
            s, e = self._get_date_range(days=5)
            for name, item in indices.items():
                try:
                    df = self.pro.index_global(ts_code=item['code'], start_date=s, end_date=e)
                    if not df.empty:
                        latest = df.iloc[0]
                        indices[name]['price'] = latest['close']
                        indices[name]['pct'] = latest['pct_chg']
                except: pass
        except: pass
        return indices

    def get_macro_news(self):
        news_list = []
        if not self.pro: return ["Token无效"]
        try:
            s, e = self._get_datetime_range(hours=24)
            # 重磅
            try:
                df_major = self.pro.major_news(src='新浪财经', start_date=s, end_date=e, fields='title,content')
                if not df_major.empty:
                    for _, row in df_major.head(10).iterrows():
                        news_list.append(f"【重磅】{row['title'].strip()}")
            except: pass
            # 快讯
            try:
                df_news = self.pro.news(src='sina', start_date=s, end_date=e)
                if not df_news.empty:
                    keywords = ['A股', '央行', '美联储', '证监会', 'GDP', 'CPI', '资金', '北向', '利好', '利空']
                    filtered = df_news[df_news['content'].str.contains('|'.join(keywords), na=False)]
                    final_df = filtered.head(25) if len(filtered) > 5 else df_news.head(20)
                    for _, row in final_df.iterrows():
                        time_str = str(row['datetime'])[11:16]
                        news_list.append(f"[{time_str}] {row['title'].strip()}")
            except: pass
            
            if not news_list: news_list.append("无重要新闻")
            return news_list[:35]
        except: return ["新闻接口异常"]

    def get_macro_summary(self):
        if not self.pro: return {}
        out = {}
        try:
            # 常用宏观指标，若无权限会返回空
            for name, endpoint in [
                ("gdp", "cn_gdp"),
                ("cpi", "cn_cpi"),
                ("ppi", "cn_ppi"),
                ("m2", "cn_m2")
            ]:
                try:
                    df = self.pro.query(endpoint, start_date=None, end_date=None)
                    if df is not None and not df.empty:
                        out[name] = df.head(5).to_dict("records")
                except Exception:
                    pass
        except Exception:
            pass
        return out


class BaseData(TushareConnector):
    def get_stock_list(self):
        if not self.pro: return []
        try:
            df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,market,list_date')
            return self._df_to_records(df, limit=5000)
        except Exception:
            return []

    def get_etf_list(self):
        if not self.pro: return []
        try:
            df = self.pro.fund_basic(market='E', fields='ts_code,name,management,purpose,found_date,issue_amount')
            return self._df_to_records(df, limit=2000)
        except Exception:
            return []

    def get_option_list(self):
        if not self.pro: return []
        # 兼容不同命名
        for ep in ["opt_basic", "option_basic"]:
            try:
                df = self.pro.query(ep)
                if df is not None and not df.empty:
                    return self._df_to_records(df, limit=2000)
            except Exception:
                continue
        return []

    def get_st_list(self):
        if not self.pro: return []
        try:
            df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
            if df is not None and not df.empty:
                df = df[df['name'].str.contains('ST')]
                return self._df_to_records(df, limit=5000)
        except Exception:
            pass
        return []

    def get_hk_connect_list(self):
        if not self.pro: return []
        try:
            df = self.pro.hs_const(hs_type='SH', is_new='1')
            if df is not None and not df.empty:
                return self._df_to_records(df, limit=5000)
        except Exception:
            pass
        return []

    def get_trade_calendar(self):
        if not self.pro: return []
        try:
            end = datetime.datetime.now().strftime("%Y%m%d")
            start = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y%m%d")
            df = self.pro.trade_cal(exchange="SSE", start_date=start, end_date=end)
            return self._df_to_records(df, limit=500)
        except Exception:
            return []

class ReferenceData(TushareConnector):
    def get_broker_recommend(self, month, with_error=False):
        if not self.pro:
            if with_error:
                return pd.DataFrame(), "Tushare 未连接或 token 无效"
            return pd.DataFrame()
        try:
            df = self.pro.broker_recommend(month=month)
            if df is None or df.empty:
                if with_error:
                    return pd.DataFrame(), "该月份无数据或权限不足"
                return pd.DataFrame()
            if with_error:
                return df, ""
            return df
        except Exception as e:
            if with_error:
                return pd.DataFrame(), f"接口异常: {e}"
            return pd.DataFrame()

    def get_pledge_stat(self, code):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            df = self.pro.pledge_stat(ts_code=ts_code)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_share_float(self, code):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            df = self.pro.share_float(ts_code=ts_code)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_repurchase(self, code):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            df = self.pro.repurchase(ts_code=ts_code)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_holder_trade(self, code):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            df = self.pro.stk_holdertrade(ts_code=ts_code)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_top_list(self, code, days=20):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            end = datetime.datetime.now().strftime("%Y%m%d")
            start = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
            df = self.pro.top_list(ts_code=ts_code, start_date=start, end_date=end)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_margin(self, code=None):
        if not self.pro: return []
        try:
            end = datetime.datetime.now().strftime("%Y%m%d")
            start = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y%m%d")
            if code:
                ts_code = self._format_code(code)
                df = self.pro.margin_detail(ts_code=ts_code, start_date=start, end_date=end)
            else:
                df = self.pro.margin(start_date=start, end_date=end)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []


class FeatureData(TushareConnector):
    def get_concept_list(self):
        if not self.pro: return []
        try:
            df = self.pro.concept()
            return self._df_to_records(df, limit=5000)
        except Exception:
            return []

    def get_concept_detail(self, concept_id):
        if not self.pro: return []
        try:
            df = self.pro.concept_detail(id=concept_id)
            return self._df_to_records(df, limit=5000)
        except Exception:
            return []

    def get_moneyflow_hsgt(self):
        if not self.pro: return []
        try:
            end = datetime.datetime.now().strftime("%Y%m%d")
            start = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y%m%d")
            df = self.pro.moneyflow_hsgt(start_date=start, end_date=end)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_moneyflow_industry(self):
        if not self.pro: return []
        try:
            trade_date = datetime.datetime.now().strftime("%Y%m%d")
            df = self.pro.moneyflow_ind_ths(trade_date=trade_date)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_factors(self, code):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            df = self.pro.stk_factor(ts_code=ts_code)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_forecast(self, code):
        if not self.pro: return []
        try:
            ts_code = self._format_code(code)
            df = self.pro.forecast(ts_code=ts_code)
            return self._df_to_records(df, limit=50)
        except Exception:
            return []

    def get_research(self, code):
        if not self.pro: return []
        for ep in ["report_rc", "report"]:
            try:
                df = self.pro.query(ep, ts_code=self._format_code(code))
                if df is not None and not df.empty:
                    return self._df_to_records(df, limit=50)
            except Exception:
                continue
        return []

    def get_auction(self, code):
        if not self.pro: return []
        for ep in ["stk_auction", "stk_auction_o"]:
            try:
                df = self.pro.query(ep, ts_code=self._format_code(code))
                if df is not None and not df.empty:
                    return self._df_to_records(df, limit=50)
            except Exception:
                continue
        return []

# 9. 核心控制器 (全能代理模式)
class TushareMaster:
    def __init__(self):
        self.market = MarketData()
        self.news = NewsData()
        self.fundamental = FundamentalData()
        self.capital = CapitalData() 
        self.chip = ChipData()       
        self.macro = MacroData()
        self.reference = ReferenceData()
        self.financial = FinancialData() # 🔥 挂载新模块
        self.base = BaseData()
        self.feature = FeatureData()
        
        self.source_name = "Tushare Pro (All-in-One)"

    def get_history(self, code, days=365):
        return self.market.get_history(code, days)
    
    def get_market_index(self):
        return self.market.get_market_index()
    
    def get_stock_basic_info(self, code):
        return self.market.get_stock_basic_info(code)
    
    def get_all_stocks(self):
        return self.market.get_all_stocks()

    def get_full_analysis_pack(self, code):
        hist = self.market.get_history(code)
        tech_factors = TechnicalCalculator.calculate(hist)
        indices = self.macro.get_global_indices()
        a50 = indices.get("A50 (XIN9)", {})
        return {
            "history": hist, "market_index": self.market.get_market_index(),
            "stock_info": self.market.get_stock_basic_info(code), "valuation": self.fundamental.get_valuation(code),
            "stock_news": self.news.get_stock_news(code), "money_flow": self.capital.get_individual_money_flow(code),
            "macro_news": self.macro.get_macro_news(),
            "sector_flow": self.capital.get_sector_money_flow(), "chip_perf": self.chip.get_cyq_perf(code),
            "global_index": {"pct_chg": a50.get('pct', 0)}, "tech_factors": tech_factors 
        }
    
    def get_morning_pack(self):
        return { "indices": self.macro.get_global_indices(), "news": self.macro.get_macro_news() }

    def get_reference_pack(self, code):
        return {
            "pledge": self.reference.get_pledge_stat(code),
            "unlock": self.reference.get_share_float(code),
            "repurchase": self.reference.get_repurchase(code),
            "holdertrade": self.reference.get_holder_trade(code),
            "top_list": self.reference.get_top_list(code),
            "margin": self.reference.get_margin(code)
        }

    def get_feature_pack(self, code):
        concepts = self.feature.get_concept_list()
        concept_members = []
        # 尝试匹配该股票所在概念（若概念列表包含 ts_code 字段）
        try:
            ts_code = self.feature._format_code(code)
            matched = [c for c in concepts if isinstance(c, dict) and (c.get("ts_code") == ts_code or c.get("ts_code") == ts_code.replace(".",""))]
            if matched:
                concept_id = matched[0].get("id")
                if concept_id:
                    concept_members = self.feature.get_concept_detail(concept_id)
        except Exception:
            pass
        return {
            "concepts": concepts,
            "concept_members": concept_members,
            "moneyflow_hsgt": self.feature.get_moneyflow_hsgt(),
            "moneyflow_industry": self.feature.get_moneyflow_industry(),
            "chip": self.chip.get_cyq_perf(code),
            "factors": self.feature.get_factors(code),
            "forecast": self.feature.get_forecast(code),
            "research": self.feature.get_research(code),
            "auction": self.feature.get_auction(code)
        }

    def get_macro_pack(self):
        return self.macro.get_macro_summary()

    def get_last_trade_date(self):
        return self.market._get_last_trade_date()

class DataSkillFactory:
    @staticmethod
    def get_skill(source_type="tushare"):
        return TushareMaster()
