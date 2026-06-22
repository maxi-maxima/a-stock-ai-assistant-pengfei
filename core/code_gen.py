import os
import ast
import json
import yaml
import traceback
import multiprocessing
from datetime import datetime
import pandas as pd
import numpy as np
from openai import OpenAI
from core.llm_resolver import resolve_preferred_settings

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed = {"pandas", "numpy", "math"}
    root = name.split(".")[0]
    if root not in allowed:
        raise ImportError(f"模块不允许: {name}")
    return __import__(name, globals, locals, fromlist, level)


def _build_safe_builtins():
    base = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    safe_keys = [
        "abs", "min", "max", "sum", "len", "range", "enumerate", "zip",
        "all", "any", "sorted",
        "float", "int", "str", "bool", "list", "tuple", "dict", "set",
        "Exception", "ValueError", "TypeError", "print"
    ]
    safe = {k: base[k] for k in safe_keys if k in base}
    safe["__import__"] = _safe_import
    return safe


def _validate_strategy_worker(code, sample_df, queue):
    try:
        ast.parse(code)
    except Exception as e:
        queue.put((False, f"语法错误: {e}", None))
        return

    env = {"pd": pd, "np": np, "__builtins__": _build_safe_builtins()}
    try:
        exec(code, env, env)
    except Exception as e:
        tb = traceback.format_exc(limit=5)
        queue.put((False, f"执行失败: {e}\n{tb}", None))
        return

    func = env.get("check")
    if not callable(func):
        queue.put((False, "未找到 check(df)", None))
        return

    df = sample_df
    try:
        result = func(df)
    except Exception as e:
        tb = traceback.format_exc(limit=5)
        queue.put((False, f"试跑失败: {e}\n{tb}", None))
        return

    if not isinstance(result, (tuple, list)) or len(result) != 2:
        queue.put((False, "返回值必须是 (bool, str)", None))
        return
    flag, reason = result[0], result[1]
    if not isinstance(flag, (bool, np.bool_)):
        queue.put((False, "返回值第1项必须是 bool", None))
        return
    if not isinstance(reason, str):
        queue.put((False, "返回值第2项必须是 str", None))
        return

    queue.put((True, "", result))

class StrategyGenerator:
    def __init__(self):
        self._load_config()

    def _load_config(self):
        self.config = {}
        self.client = None
        self.model = None
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
        except Exception:
            self.config = {}
        try:
            setting = resolve_preferred_settings(
                preferred=("blue", "general"),
                conf=self.config,
                load_environment=True,
            )
            api_key = setting.get("api_key")
            model = setting.get("model")
            if not api_key or not model:
                return
            self.client = OpenAI(api_key=api_key, base_url=setting.get("base_url") or None)
            self.model = model
        except Exception:
            self.client = None

    def _build_sample_df(self, rows=120):
        try:
            n = int(rows) if rows else 120
        except Exception:
            n = 120
        if n < 60:
            n = 60

        if hasattr(np.random, "default_rng"):
            rng = np.random.default_rng(42)
            noise = rng.normal(0, 1, n)
            open_noise = rng.normal(0, 0.5, n)
            close_noise = rng.normal(0, 0.5, n)
            rand = rng.random(n)
            vol = rng.integers(1000, 100000, n)
        else:
            np.random.seed(42)
            noise = np.random.normal(0, 1, n)
            open_noise = np.random.normal(0, 0.5, n)
            close_noise = np.random.normal(0, 0.5, n)
            rand = np.random.random(n)
            vol = np.random.randint(1000, 100000, n)

        base = 100 + np.cumsum(noise)
        open_p = base + open_noise
        close_p = base + close_noise
        high = np.maximum(open_p, close_p) + rand * 1.5
        low = np.minimum(open_p, close_p) - rand * 1.5
        pct = np.concatenate([[0], (close_p[1:] / close_p[:-1] - 1) * 100])

        amount = close_p * vol
        turnover_rate = rand * 5
        pe = 10 + rand * 30
        pb = 1 + rand * 5
        total_mv = close_p * (vol * 100)
        circ_mv = total_mv * (0.6 + rand * 0.4)

        df = pd.DataFrame({
            "open": open_p,
            "close": close_p,
            "high": high,
            "low": low,
            "vol": vol,
            "pct_chg": pct,
            "amount": amount,
            "turnover_rate": turnover_rate,
            "pe": pe,
            "pb": pb,
            "total_mv": total_mv,
            "circ_mv": circ_mv
        })
        periods = resolve_ma_periods()
        p_short1 = periods.get('short1', 5)
        p_mid1 = periods.get('mid1', 20)
        df[f'ma{p_short1}'] = ma_series(df['close'], p_short1)
        df[f'ma{p_mid1}'] = ma_series(df['close'], p_mid1)
        return df

    def _get_draft_meta_path(self):
        return os.path.join("skills", "strategies_draft", "_meta.json")

    def _load_draft_meta(self):
        path = self._get_draft_meta_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_draft_meta(self, meta):
        path = self._get_draft_meta_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not meta:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_draft_meta(self):
        return self._load_draft_meta()

    def _validate_with_timeout(self, code, sample_df=None, timeout_s=4):
        df = sample_df if sample_df is not None else self._build_sample_df()
        try:
            ctx = multiprocessing.get_context("spawn")
            q = ctx.Queue()
            p = ctx.Process(target=_validate_strategy_worker, args=(code, df, q))
            p.daemon = True
            p.start()
            p.join(timeout_s)
            if p.is_alive():
                p.terminate()
                p.join(1)
                return False, f"校验超时({timeout_s}s)，请检查是否存在死循环", None
            try:
                ok, err, result = q.get_nowait()
            except Exception:
                return False, "校验失败：未返回结果", None
            return ok, err, result
        except Exception as e:
            return False, f"校验进程启动失败: {e}", None

    def validate_strategy(self, code, sample_df=None):
        ok, err, _ = self._validate_with_timeout(code, sample_df)
        return ok, err

    def test_strategy(self, code, sample_df=None):
        return self._validate_with_timeout(code, sample_df)

    def generate_code(self, description):
        if not self.client: return "# ❌ LLM 未配置，请检查 config/llm_config.yaml"

        # 🔥 Kimi 专属的高级编程 Prompt
        sys_prompt = '''
        你就是 Kimi，一位精通 Python 和 Pandas 的资深量化交易架构师。
        你的任务是将用户的【自然语言策略】转化为【标准 Python 代码】。
        
        【输入数据 df 结构】
        - df 是一个 pandas DataFrame，包含个股历史日线数据。
        - 必须使用的列名: 'open', 'close', 'high', 'low', 'vol', 'pct_chg'。
        - 数据按时间正序排列，iloc[-1] 为最新一行（今天），iloc[-2] 为昨天。
        - df includes EMA columns: ema{period} (periods from config/ma_periods.json).
        
        【代码规范 (Strict Rules)】
        1. **函数签名**：必须且只能是 `def check(df):`。
        2. **返回值**：必须返回元组 `(bool, str)`。True 代表命中策略，str 是命中理由（简短中文）。
        3. **容错性**：必须检查 `len(df)` 是否足够计算指标。
        4. **矢量化**：尽量使用 Pandas 内置函数（如 .rolling, .diff, .shift），严禁使用 for 循环遍历 DataFrame。
        5. **输出格式**：只返回 Python 代码本身，不要包含 ```python 或 ``` 标记，不要包含任何解释性文字。
        6. **指标计算**：如果用户提到 MACD、KDJ、RSI 等复杂指标，你必须在函数内部现场计算，不要假设 df 里有。
        
        【示例】
        用户：买入收盘价站上5日线的股票。
        Kimi：
        import pandas as pd
        def check(df):
            if len(df) < 5: return False, "数据不足"
            curr = df.iloc[-1]
            if curr['close'] > curr['ema5']:
                return True, "above EMA5"
            return False, ""
        '''
        
        user_prompt = f"用户策略描述：{description}"
        
        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1 # 代码生成需要低温度，保证严谨
            )
            code = res.choices[0].message.content
            # 二次清洗，防止 Kimi 偶尔还是会打 markdown 标记
            code = code.replace("```python", "").replace("```", "").strip()
            return code
        except Exception as e:
            return f"# ❌ Kimi 生成失败: {e}"

    def save_strategy(self, name, code):
        # 简单清洗文件名，防止非法字符
        safe_name = "".join([c for c in name if c.isalnum() or c == '_'])
        if safe_name.startswith("user_"):
            safe_name = safe_name[5:]
        if not safe_name:
            return False, "策略名无效，只能包含字母、数字和下划线", "", False

        filename = f"user_{safe_name}.py"
        enable_dir = "skills/strategies"
        draft_dir = "skills/strategies_draft"
        os.makedirs(enable_dir, exist_ok=True)
        os.makedirs(draft_dir, exist_ok=True)

        ok, err = self.validate_strategy(code)
        path = os.path.join(enable_dir if ok else draft_dir, filename)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return False, str(e), "", False

        if ok:
            meta = self._load_draft_meta()
            if filename in meta:
                del meta[filename]
                self._save_draft_meta(meta)
            return True, f"{filename} 已保存", path, False
        meta = self._load_draft_meta()
        meta[filename] = {
            "error": err,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_draft_meta(meta)
        return False, f"校验失败，已保存到草稿区: {err}", path, True
            
    def delete_strategy(self, filename):
        removed = False
        for d in ["skills/strategies", "skills/strategies_draft"]:
            path = os.path.join(d, filename)
            if os.path.exists(path):
                os.remove(path)
                removed = True
                break
        if removed:
            meta = self._load_draft_meta()
            if filename in meta:
                del meta[filename]
                self._save_draft_meta(meta)
        return removed
