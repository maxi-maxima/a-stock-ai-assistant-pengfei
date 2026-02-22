import sqlite3
import pandas as pd
import os
import datetime
import json

DB_PATH = "data/skills.db"

class SkillRegistry:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        if not os.path.exists("data"): os.makedirs("data")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # 策略表现表
        c.execute('''CREATE TABLE IF NOT EXISTS strategy_stats (
            name TEXT PRIMARY KEY,
            total_calls INTEGER DEFAULT 0,    -- 策略被扫描次数
            hits INTEGER DEFAULT 0,           -- 交易命中(止盈)次数
            avg_return REAL DEFAULT 0.0,      -- 平均收益
            last_used TEXT,
            description TEXT,
            scan_hits INTEGER DEFAULT 0,      -- 扫描命中数
            reward_sum REAL DEFAULT 0.0,      -- 回报累计
            reward_count INTEGER DEFAULT 0,   -- 回报样本数
            last_reward REAL DEFAULT 0.0
        )''')
        # 兼容新增字段
        try:
            cols = [row[1] for row in c.execute("PRAGMA table_info(strategy_stats)")]
            if "last_params" not in cols:
                c.execute("ALTER TABLE strategy_stats ADD COLUMN last_params TEXT")
            if "scan_hits" not in cols:
                c.execute("ALTER TABLE strategy_stats ADD COLUMN scan_hits INTEGER DEFAULT 0")
            if "reward_sum" not in cols:
                c.execute("ALTER TABLE strategy_stats ADD COLUMN reward_sum REAL DEFAULT 0.0")
            if "reward_count" not in cols:
                c.execute("ALTER TABLE strategy_stats ADD COLUMN reward_count INTEGER DEFAULT 0")
            if "last_reward" not in cols:
                c.execute("ALTER TABLE strategy_stats ADD COLUMN last_reward REAL DEFAULT 0.0")
            if "last_reward_ts" not in cols:
                c.execute("ALTER TABLE strategy_stats ADD COLUMN last_reward_ts TEXT")
        except Exception:
            pass
        conn.commit()
        conn.close()

    def register_usage(self, strategy_name, hit_count, params=None, calls=1):
        """
        记录一次策略的使用
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 检查是否存在
        c.execute("SELECT name FROM strategy_stats WHERE name=?", (strategy_name,))
        if not c.fetchone():
            c.execute("INSERT INTO strategy_stats (name, total_calls, last_used) VALUES (?, ?, ?)", 
                      (strategy_name, 0, datetime.datetime.now().strftime("%Y-%m-%d")))
        
        # 更新触发次数
        try:
            calls = int(calls)
        except Exception:
            calls = 1
        try:
            hit_count = int(hit_count)
        except Exception:
            hit_count = 0

        if params is not None:
            try:
                params_str = json.dumps(params, ensure_ascii=False)
            except Exception:
                params_str = str(params)
            c.execute(
                "UPDATE strategy_stats SET total_calls = total_calls + ?, scan_hits = scan_hits + ?, last_used = ?, last_params = ? WHERE name = ?",
                (calls, hit_count, datetime.datetime.now().strftime("%Y-%m-%d"), params_str, strategy_name)
            )
        else:
            c.execute(
                "UPDATE strategy_stats SET total_calls = total_calls + ?, scan_hits = scan_hits + ?, last_used = ? WHERE name = ?",
                (calls, hit_count, datetime.datetime.now().strftime("%Y-%m-%d"), strategy_name)
            )
        
        conn.commit()
        conn.close()

    def update_performance(self, strategy_name, profit_pct):
        """
        (未来功能) 当一笔交易结束，更新该策略的胜率
        profit_pct: 收益率 (如 0.05 代表 5%)
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # ensure record exists
        c.execute("SELECT name FROM strategy_stats WHERE name=?", (strategy_name,))
        if not c.fetchone():
            c.execute(
                "INSERT INTO strategy_stats (name, total_calls, last_used) VALUES (?, ?, ?)",
                (strategy_name, 0, datetime.datetime.now().strftime("%Y-%m-%d"))
            )

        c.execute("SELECT hits, avg_return, total_calls, reward_sum, reward_count FROM strategy_stats WHERE name=?", (strategy_name,))
        res = c.fetchone()
        if res:
            hits, avg_ret, calls, reward_sum, reward_count = res
            
            # 简单的移动平均更新
            new_hits = hits + (1 if profit_pct > 0 else 0)
            # 这里的 avg_return 简单处理，实际应该加权
            try:
                reward_count_safe = int(reward_count or 0)
            except Exception:
                reward_count_safe = 0
            new_avg = (avg_ret * reward_count_safe + profit_pct) / (reward_count_safe + 1) if reward_count_safe > 0 else profit_pct

            try:
                reward = float(profit_pct)
            except Exception:
                reward = 0.0
            reward = max(-0.2, min(0.2, reward))
            try:
                reward_sum = float(reward_sum or 0.0)
            except Exception:
                reward_sum = 0.0
            try:
                reward_count = int(reward_count or 0)
            except Exception:
                reward_count = 0
            reward_sum = reward_sum + reward
            reward_count = reward_count + 1

            c.execute(
                "UPDATE strategy_stats SET hits=?, avg_return=?, reward_sum=?, reward_count=?, last_reward=?, last_reward_ts=? WHERE name=?",
                (new_hits, new_avg, reward_sum, reward_count, reward, datetime.datetime.now().isoformat(), strategy_name)
            )
        
        conn.commit()
        conn.close()

    def update_reward(self, strategy_name, reward, source="backtest"):
        """
        Update reward stats without touching hits/avg_return.
        reward: float (e.g. 0.05 for +5%)
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM strategy_stats WHERE name=?", (strategy_name,))
        if not c.fetchone():
            c.execute(
                "INSERT INTO strategy_stats (name, total_calls, last_used) VALUES (?, ?, ?)",
                (strategy_name, 0, datetime.datetime.now().strftime("%Y-%m-%d"))
            )
        try:
            reward = float(reward)
        except Exception:
            reward = 0.0
        reward = max(-0.2, min(0.2, reward))
        c.execute("SELECT reward_sum, reward_count FROM strategy_stats WHERE name=?", (strategy_name,))
        res = c.fetchone()
        reward_sum = 0.0
        reward_count = 0
        if res:
            try:
                reward_sum = float(res[0] or 0.0)
            except Exception:
                reward_sum = 0.0
            try:
                reward_count = int(res[1] or 0)
            except Exception:
                reward_count = 0
        reward_sum += reward
        reward_count += 1
        c.execute(
            "UPDATE strategy_stats SET reward_sum=?, reward_count=?, last_reward=?, last_reward_ts=?, last_used=? WHERE name=?",
            (reward_sum, reward_count, reward, datetime.datetime.now().isoformat(), datetime.datetime.now().strftime("%Y-%m-%d"), strategy_name)
        )
        conn.commit()
        conn.close()

    def get_leaderboard(self):
        """获取排行榜"""
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM strategy_stats ORDER BY total_calls DESC", conn)
        conn.close()
        return df
