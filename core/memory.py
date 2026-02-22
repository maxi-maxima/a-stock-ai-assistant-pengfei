import os
import json
import datetime
import yaml
try:
    import requests
except Exception:
    requests = None
from core.learning_log import log_event
try:
    import chromadb
    from chromadb.utils import embedding_functions
except Exception:
    chromadb = None
    embedding_functions = None

DB_PATH = "data/chroma_db"
RULES_PATH = "config/house_rules.json"
MEMORY_BACKUP_PATH = "data/memory_backup.jsonl"
LEGACY_BACKUP_PATH = "data/memory_backup.json"
EVENT_BUS_PATH = "data/event_bus.jsonl"

class MemoryManager:
    def __init__(self):
        self._init_db()
        self._init_rules()

    def _load_system_config(self):
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                conf = yaml.safe_load(f) or {}
            return conf.get("system", {}) if isinstance(conf, dict) else {}
        except Exception:
            return {}

    def _parse_endpoint_candidates(self, sys_conf):
        endpoints = []
        env_eps = os.getenv("HF_ENDPOINTS", "").strip()
        if env_eps:
            endpoints.extend([u.strip() for u in env_eps.split(",") if u.strip()])
        if isinstance(sys_conf, dict):
            for key in ("hf_endpoint_candidates", "hf_endpoints", "huggingface_endpoints"):
                val = sys_conf.get(key)
                if isinstance(val, list):
                    endpoints.extend([str(u).strip() for u in val if str(u).strip()])
                elif isinstance(val, str) and val.strip():
                    endpoints.extend([u.strip() for u in val.split(",") if u.strip()])
        # de-dup
        seen = set()
        uniq = []
        for u in endpoints:
            if u not in seen:
                uniq.append(u)
                seen.add(u)
        return uniq

    def _build_embedding_function(self, model_name, endpoints=None):
        endpoints = endpoints or []
        auto_mirror = os.getenv("AUTO_HF_MIRROR", "0") == "1"
        if auto_mirror and "https://hf-mirror.com" not in endpoints:
            endpoints.append("https://hf-mirror.com")
        # try preferred endpoints first
        for ep in endpoints:
            try:
                os.environ.setdefault("HF_ENDPOINT", str(ep))
                os.environ.setdefault("HUGGINGFACE_HUB_BASE_URL", str(ep))
                return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=str(model_name))
            except Exception:
                continue
        # fallback: default endpoint
        try:
            return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=str(model_name))
        except Exception:
            return None

    def _probe_endpoint(self, urls, timeout=2.0):
        if not requests:
            return None
        for u in urls:
            try:
                r = requests.get(u, timeout=timeout)
                if r is not None and r.status_code < 500:
                    return u
            except Exception:
                continue
        return None

    def _init_db(self):
        if not os.path.exists("data"): os.makedirs("data")
        sys_conf = self._load_system_config()
        if os.getenv("CHROMA_DISABLED", "0") == "1" or os.getenv("CHROMA_OFFLINE", "0") == "1":
            self.client = None
            return
        if sys_conf.get("chroma_disabled") or sys_conf.get("chroma_offline"):
            self.client = None
            return
        offline = os.getenv("EMBEDDING_OFFLINE", "0") == "1" or sys_conf.get("embedding_offline")
        if not chromadb or not embedding_functions:
            self.client = None
            return
        try:
            db_path = os.getenv("CHROMA_DB_PATH") or sys_conf.get("chroma_db_path") or DB_PATH
            model_name = os.getenv("EMBEDDING_MODEL") or sys_conf.get("embedding_model") or "all-MiniLM-L6-v2"
            model_path = os.getenv("EMBEDDING_MODEL_PATH") or sys_conf.get("embedding_model_path")
            preferred = os.getenv("HF_ENDPOINT") or sys_conf.get("hf_endpoint") or sys_conf.get("huggingface_endpoint")
            endpoints = []
            if preferred:
                endpoints.append(str(preferred))
            endpoints.extend(self._parse_endpoint_candidates(sys_conf))
            if sys_conf.get("auto_hf_mirror") and "https://hf-mirror.com" not in endpoints:
                endpoints.append("https://hf-mirror.com")

            if model_path and os.path.exists(str(model_path)):
                model_name = str(model_path)
            elif offline:
                self.client = None
                return
            else:
                # If no local model and endpoint unreachable, skip to avoid hang
                skip_unreachable = os.getenv("EMBEDDING_SKIP_IF_UNREACHABLE", "1") == "1" or sys_conf.get("embedding_skip_if_unreachable")
                if skip_unreachable:
                    probe_list = endpoints if endpoints else ["https://huggingface.co"]
                    hit = self._probe_endpoint(probe_list, timeout=float(sys_conf.get("embedding_probe_timeout", 2) or 2))
                    if not hit:
                        self.client = None
                        return

            self.client = chromadb.PersistentClient(path=db_path)
            self.ef = self._build_embedding_function(model_name, endpoints=endpoints)
            if not self.ef:
                self.client = None
                return
            self.collection = self.client.get_or_create_collection(name="trading_memory", embedding_function=self.ef)
        except:
            self.client = None

    def _init_rules(self):
        if not os.path.exists("config"): os.makedirs("config")
        # 默认家规 (包含 general 总纲)
        self.default_rules = {
            "general": "1. 严禁追高，宁可错过不做错。\n2. 单只股票仓位不得超过 30%。\n3. 必须顺势而为。",
            "blue": "负责进攻，寻找高赔率机会，信奉趋势和热点。",
            "red": "负责风控，极度厌恶亏损，只关注风险、背离和压力位。",
            "green": "负责统帅，平衡红蓝观点，结合用户实盘仓位给出最终裁决。",
            "constraints": {
                "max_single_position": 0.3,
                "max_industry_concentration": 0.35,
                "max_drawdown": 0.2,
                "max_daily_trades": 6,
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.15,
                "allow_chase": False,
                "max_open_positions": 6,
                "daily_loss_pct": 0.03
            }
        }
        if not os.path.exists(RULES_PATH):
            with open(RULES_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.default_rules, f, ensure_ascii=False, indent=2)

    def get_rules(self):
        try:
            with open(RULES_PATH, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                # 兼容旧版，如果没有 general 字段则补上
                if "general" not in rules:
                    rules["general"] = self.default_rules["general"]
                if "constraints" not in rules:
                    rules["constraints"] = self.default_rules["constraints"]
                else:
                    try:
                        cons = rules.get("constraints", {})
                        if isinstance(cons, dict):
                            for k, v in self.default_rules.get("constraints", {}).items():
                                if k not in cons:
                                    cons[k] = v
                            rules["constraints"] = cons
                    except Exception:
                        pass
                # merge active profile constraints (non-destructive)
                try:
                    from core.threshold_profiles import load_profiles, get_active_profile_name, get_profile
                    profiles = load_profiles()
                    name = get_active_profile_name(profiles)
                    profile = get_profile(name, profiles)
                    prof_rules = profile.get("rules", {}) if isinstance(profile, dict) else {}
                    prof_cons = {}
                    if isinstance(prof_rules, dict):
                        prof_cons = prof_rules.get("constraints", {}) or {}
                    if not prof_cons and isinstance(profile, dict):
                        prof_cons = profile.get("constraints", {}) or {}
                    if isinstance(prof_cons, dict) and prof_cons:
                        cons = rules.get("constraints", {})
                        if not isinstance(cons, dict):
                            cons = {}
                        for k, v in prof_cons.items():
                            if k not in cons:
                                cons[k] = v
                        rules["constraints"] = cons
                    if "profile" not in rules and name:
                        rules["profile"] = name
                except Exception:
                    pass
                return rules
        except: return self.default_rules

    def update_rules(self, new_rules):
        """用户手动更新家规"""
        with open(RULES_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_rules, f, ensure_ascii=False, indent=2)
        return "✅ 家规已更新"

    def save_episode(self, code, action, price, details, manual_teach=False):
        details = details if isinstance(details, dict) else {}
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        date_str = ts.split("T")[0]
        core = details.get('core_view', '无')
        if manual_teach: core = f"【用户教学】强制买入点分析。AI原始观点: {core}"
        
        doc_text = f"日期:{date_str}|代码:{code}|操作:{action}|价格:{price}|观点:{core}"
        metadata = {
            "date": date_str, "code": code, "action": action, 
            "type": "TEACH" if manual_teach else "AUTO",
            "ts": ts
        }
        mem_id = f"{code}_{int(datetime.datetime.now().timestamp())}"
        
        if self.client:
            self.collection.add(documents=[doc_text], metadatas=[metadata], ids=[mem_id])
            print(f"💾 记忆已存储: {mem_id}")
        record = {
            "ts": ts,
            "date": date_str,
            "code": code,
            "action": action,
            "price": price,
            "core": core,
            "type": "TEACH" if manual_teach else "AUTO",
            "manual_teach": bool(manual_teach)
        }
        self._append_backup(record)
        try:
            log_event("memory_episode", {
                "ts": ts,
                "code": code,
                "action": action,
                "price": price,
                "manual_teach": bool(manual_teach),
                "core_view": core
            })
        except Exception:
            pass

    def _append_backup(self, record):
        if not isinstance(record, dict):
            return
        try:
            os.makedirs(os.path.dirname(MEMORY_BACKUP_PATH), exist_ok=True)
            with open(MEMORY_BACKUP_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _read_backup_jsonl(self, limit=None):
        if not os.path.exists(MEMORY_BACKUP_PATH):
            return []
        records = []
        try:
            with open(MEMORY_BACKUP_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if isinstance(rec, dict):
                            rec.setdefault("source", "backup")
                            records.append(rec)
                    except Exception:
                        continue
        except Exception:
            return []
        if limit and len(records) > limit:
            records = records[-limit:]
        return records

    def _read_backup_legacy(self, limit=None):
        if not os.path.exists(LEGACY_BACKUP_PATH):
            return []
        try:
            with open(LEGACY_BACKUP_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                records = []
                for item in data:
                    if isinstance(item, dict):
                        item.setdefault("source", "legacy")
                        records.append(item)
                    else:
                        records.append({"doc_text": str(item), "source": "legacy"})
                if limit and len(records) > limit:
                    records = records[-limit:]
                return records
        except Exception:
            return []
        return []

    def _read_event_bus(self, code=None, limit=200):
        if not os.path.exists(EVENT_BUS_PATH):
            return []
        records = []
        code_filter = str(code or "").strip().upper()
        try:
            with open(EVENT_BUS_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if code_filter:
                        rc = str(rec.get("code") or "").strip().upper()
                        if rc and code_filter not in rc:
                            continue
                    records.append(rec)
        except Exception:
            return []
        if limit and len(records) > limit:
            records = records[-limit:]
        return records

    def _summarize_event_bus(self, records, query_text=""):
        records = records or []
        if not records:
            return ""
        q = str(query_text or "").strip()
        hits = []
        for rec in reversed(records):
            if not isinstance(rec, dict):
                continue
            ev = str(rec.get("event") or "")
            payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
            if q:
                try:
                    blob = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    blob = str(payload)
                if q not in blob and q not in ev:
                    continue
            ts = rec.get("ts") or ""
            code = rec.get("code") or ""
            if ev == "decision":
                action = payload.get("action") or ""
                score = ""
                try:
                    score = payload.get("scores", {}).get("total")
                except Exception:
                    score = ""
                tags = payload.get("context_tags") or []
                if isinstance(tags, list) and tags:
                    tag_str = ",".join([str(t) for t in tags[:6]])
                else:
                    tag_str = ""
                line = f"{ts} {code}: decision {action} score={score} tags={tag_str}".strip()
            elif ev == "outcome":
                pnl = payload.get("pnl")
                pnl_pct = payload.get("pnl_pct")
                line = f"{ts} {code}: outcome pnl={pnl} pnl_pct={pnl_pct}"
            else:
                line = f"{ts} {code}: {ev}"
            hits.append(line.strip())
            if len(hits) >= 3:
                break
        if not hits:
            return ""
        return "\n".join([f"- {h}" for h in hits])

    def _parse_doc_text(self, doc_text):
        if not isinstance(doc_text, str):
            return {}
        data = {}
        for part in doc_text.split("|"):
            if ":" not in part:
                continue
            key, val = part.split(":", 1)
            key = key.strip()
            val = val.strip()
            if not val:
                continue
            if key in ("日期", "date"):
                data["date"] = val
            elif key in ("代码", "code"):
                data["code"] = val
            elif key in ("操作", "action"):
                data["action"] = val
            elif key in ("价格", "price"):
                data["price"] = val
            elif key in ("观点", "core", "view"):
                data["core"] = val
        return data

    def _normalize_record(self, rec):
        if not isinstance(rec, dict):
            return None
        data = {}
        doc_text = rec.get("doc_text") or rec.get("doc") or rec.get("text")
        if doc_text:
            data.update(self._parse_doc_text(doc_text))
        for key in ("ts", "date", "code", "action", "price", "core", "type", "manual_teach", "source"):
            val = rec.get(key)
            if val is not None and val != "":
                data[key] = val
        if "core_view" in rec and "core" not in data:
            data["core"] = rec.get("core_view")
        if "manual_teach" in rec and "type" not in data:
            data["type"] = "TEACH" if rec.get("manual_teach") else "AUTO"

        ts = str(data.get("ts") or "").strip()
        if ts:
            data["ts"] = ts
        date = str(data.get("date") or "").strip()
        if not date and ts:
            date = ts.split("T")[0]
        if date:
            data["date"] = date

        if "code" in data and data["code"] is not None:
            data["code"] = str(data["code"]).strip().upper()
        if "action" in data and data["action"] is not None:
            data["action"] = str(data["action"]).strip().upper()
        if "price" in data and data["price"] is not None:
            try:
                data["price"] = float(data["price"])
            except Exception:
                pass

        if "core" not in data:
            data["core"] = ""
        if "type" not in data:
            data["type"] = ""
        if "source" not in data:
            data["source"] = "unknown"
        return data

    def _parse_date(self, value):
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value[:10])
            except Exception:
                return None
        return None

    def _in_range(self, date_value, start_date=None, end_date=None):
        if not start_date and not end_date:
            return True
        d = self._parse_date(date_value)
        if not d:
            return False
        if start_date and d < start_date:
            return False
        if end_date and d > end_date:
            return False
        return True

    def _record_datetime(self, rec):
        ts = rec.get("ts") if isinstance(rec, dict) else None
        if ts:
            try:
                return datetime.datetime.fromisoformat(ts)
            except Exception:
                pass
        date = rec.get("date") if isinstance(rec, dict) else None
        if date:
            try:
                return datetime.datetime.fromisoformat(date)
            except Exception:
                pass
        return datetime.datetime.min

    def _read_from_db(self, limit=None):
        if not self.client:
            return []
        try:
            res = self.collection.get(include=["documents", "metadatas"], limit=limit)
            docs = res.get("documents") or []
            metas = res.get("metadatas") or []
            records = []
            for doc, meta in zip(docs, metas):
                rec = {}
                if isinstance(meta, dict):
                    rec.update(meta)
                rec["doc_text"] = doc
                rec["source"] = "db"
                norm = self._normalize_record(rec)
                if norm:
                    records.append(norm)
            return records
        except Exception:
            try:
                res = self.collection.peek(limit=limit or 50)
                docs = res.get("documents") or []
                records = []
                for doc in docs:
                    norm = self._normalize_record({"doc_text": doc, "source": "db"})
                    if norm:
                        records.append(norm)
                return records
            except Exception:
                return []

    def list_episodes(self, start_date=None, end_date=None, code=None, action=None, limit=200):
        records = self._read_backup_jsonl()
        if not records:
            records = self._read_backup_legacy()
        if not records:
            records = self._read_from_db(limit=limit)

        action_set = None
        if action:
            if isinstance(action, (list, tuple, set)):
                action_set = {str(a).strip().upper() for a in action if str(a).strip()}
            else:
                action_set = {str(action).strip().upper()}
        code_filter = str(code).strip().upper() if code else ""

        filtered = []
        for rec in records:
            norm = rec if isinstance(rec, dict) and rec.get("source") and rec.get("date") else None
            if not norm or not isinstance(norm, dict) or "action" not in norm or "code" not in norm:
                norm = self._normalize_record(rec)
            if not norm:
                continue
            if code_filter and code_filter not in (norm.get("code") or ""):
                continue
            if action_set and (norm.get("action") or "") not in action_set:
                continue
            if not self._in_range(norm.get("date") or norm.get("ts"), start_date, end_date):
                continue
            filtered.append(norm)

        filtered.sort(key=self._record_datetime, reverse=True)
        if limit and len(filtered) > limit:
            filtered = filtered[:limit]
        return filtered

    def summarize_episodes(self, records, start_date=None, end_date=None):
        records = records or []
        by_action = {}
        by_code = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            action = rec.get("action", "")
            if action:
                by_action[action] = by_action.get(action, 0) + 1
            code = rec.get("code", "")
            if code:
                by_code[code] = by_code.get(code, 0) + 1

        top_codes = sorted(by_code.items(), key=lambda x: x[1], reverse=True)[:5]
        last_ts = records[0].get("ts") if records else ""

        if start_date and end_date:
            range_label = f"{start_date.isoformat()} ~ {end_date.isoformat()}"
        elif start_date:
            range_label = f"{start_date.isoformat()} ~"
        elif end_date:
            range_label = f"~ {end_date.isoformat()}"
        else:
            range_label = "全部"

        lines = [
            f"时间范围: {range_label}",
            f"记录条数: {len(records)}",
            f"涉及标的: {len(by_code)}"
        ]
        if by_action:
            lines.append("动作统计: " + ", ".join([f"{k}:{v}" for k, v in by_action.items()]))
        if top_codes:
            lines.append("Top标的: " + ", ".join([f"{c}({n})" for c, n in top_codes]))
        if last_ts:
            lines.append(f"最新记录: {last_ts}")
        if not records:
            lines.append("暂无记录。")

        return {
            "total": len(records),
            "unique_codes": len(by_code),
            "by_action": by_action,
            "by_code": by_code,
            "top_codes": [{"code": c, "count": n} for c, n in top_codes],
            "last_ts": last_ts,
            "text": "\n".join(lines)
        }

    def retrieve_context(self, code, query_text=""):
        if self.client:
            try:
                q = query_text if query_text else f"{code} 交易历史"
                res = self.collection.query(query_texts=[q], n_results=3)
                docs = res['documents'][0]
                return "\n".join([f"- {d}" for d in docs]) if docs else "无相关记忆"
            except Exception:
                return "检索失败"

        # optional: event index (structured memory)
        if os.getenv("ENABLE_EVENT_INDEX", "0") == "1":
            try:
                from core.event_index import update_index, query_context
                update_index()
                lines = query_context(code=code, query_text=query_text, limit=3)
                if lines:
                    return "\n".join([f"- {l}" for l in lines])
            except Exception:
                pass

        # fallback: local backups
        records = self.list_episodes(code=code, limit=50)
        if not records:
            eb = self._read_event_bus(code=code, limit=50)
            eb_text = self._summarize_event_bus(eb, query_text=query_text)
            if eb_text:
                return eb_text
            return "无相关记忆"
        q = str(query_text or "").strip()
        hits = []
        for rec in records:
            core = str(rec.get("core", "") or "")
            action = str(rec.get("action", "") or "")
            if q and q not in core and q not in action:
                continue
            date = rec.get("date") or rec.get("ts") or ""
            price = rec.get("price", "")
            hits.append(f"{date} {rec.get('code','')}: {action} {price} {core}".strip())
            if len(hits) >= 3:
                break
        if not hits:
            eb = self._read_event_bus(code=code, limit=50)
            eb_text = self._summarize_event_bus(eb, query_text=query_text)
            if eb_text:
                return eb_text
            return "无相关记忆"
        return "\n".join([f"- {h}" for h in hits])

    def generate_weekly_summary(self, days=7):
        end_date = datetime.date.today()
        try:
            days = int(days)
        except Exception:
            days = 7
        if days < 1:
            days = 7
        start_date = end_date - datetime.timedelta(days=days - 1)
        records = self.list_episodes(start_date=start_date, end_date=end_date, limit=200)
        summary = self.summarize_episodes(records, start_date=start_date, end_date=end_date)
        return summary.get("text") or "本周无交易记录。"
