import os
import json
import yaml
import re
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from core.llm_guard import parse_json_safe, log_llm
from core.llm_resolver import resolve_brain_settings


class KimiKnowledgeOrganizer:
    def __init__(self):
        self.client = None
        self.model = None
        self._init_client()

    def _load_secure_settings(self):
        path = "data/secure_settings.json"
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_config(self):
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                conf = yaml.safe_load(f) or {}
            return conf if isinstance(conf, dict) else {}
        except Exception:
            return {}

    def _init_client(self):
        if OpenAI is None:
            return
        if os.getenv("LLM_OFFLINE", "0") == "1" or os.getenv("DISABLE_LLM", "0") == "1":
            return
        conf = self._load_config()
        secure = self._load_secure_settings()
        setting = resolve_brain_settings("green", secure=secure, conf=conf, load_environment=True)
        api_key = setting.get("api_key")
        base_url = setting.get("base_url")
        model = setting.get("model") or "moonshot-v1-8k"
        if not api_key or not model:
            return
        try:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.model = model
        except Exception:
            self.client = None

    def test_connection(self):
        if os.getenv("LLM_OFFLINE", "0") == "1" or os.getenv("DISABLE_LLM", "0") == "1":
            return False, "LLM 已禁用或离线模式", ""
        if not self.client or not self.model:
            return False, "Kimi 未初始化，请检查密钥/配置", ""
        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a health check bot. Reply with 'pong'."},
                    {"role": "user", "content": "ping"}
                ],
                temperature=1,
                max_tokens=8
            )
            raw = res.choices[0].message.content if res and res.choices else ""
            ok = bool(raw and "pong" in raw.lower())
            log_llm("kb_kimi_ping", self.model, raw, raw, ok=ok)
            return ok, (raw.strip() or "pong"), self.model
        except Exception as e:
            return False, f"调用失败: {e}", self.model or ""

    def _normalize_items(self, data):
        items = []
        if isinstance(data, dict):
            if isinstance(data.get("items"), list):
                items = data.get("items")
            else:
                items = [data]
        elif isinstance(data, list):
            items = data
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            content = str(item.get("content") or item.get("text") or item.get("body") or "").strip()
            tags = item.get("tags") or item.get("tag") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.replace("，", ",").replace("/", ",").split(",") if t.strip()]
            if not isinstance(tags, list):
                tags = []
            structure = item.get("structure") if isinstance(item.get("structure"), dict) else {}
            if not structure:
                structure = {
                    "timeframe": item.get("timeframe") or "",
                    "conditions": item.get("conditions") or "",
                    "invalidations": item.get("invalidations") or "",
                    "risk": item.get("risk") or "",
                    "examples": item.get("examples") or ""
                }
            # enforce required structure fields (empty -> "无")
            for k in ["conditions", "invalidations", "risk", "examples"]:
                if not str(structure.get(k, "") or "").strip():
                    structure[k] = "无"
            out.append({
                "title": title,
                "tags": tags,
                "content": content,
                "structure": structure
            })
        return out

    def _split_text(self, text, max_chars=1800):
        raw = str(text or "").strip()
        if not raw:
            return []
        if len(raw) <= max_chars:
            return [raw]

        # insert breaks before hierarchical headings like "1.2", "2.1", "4.3"
        def _insert_breaks(s):
            op_chars = set("×*xX><=+-")
            out = []
            i = 0
            for m in re.finditer(r"\d+\.\d+\s+", s):
                start = m.start()
                # check if already at line start
                last_nl = s.rfind("\n", 0, start)
                seg = s[last_nl + 1:start] if last_nl >= 0 else s[:start]
                if seg.strip() == "":
                    continue
                # find previous non-space char
                j = start - 1
                while j >= 0 and s[j].isspace():
                    j -= 1
                prev = s[j] if j >= 0 else ""
                if prev and (prev.isdigit() or prev in op_chars or prev == "."):
                    continue
                out.append(s[i:start])
                out.append("\n")
                i = start
            if i == 0:
                return s
            out.append(s[i:])
            return "".join(out)

        raw = _insert_breaks(raw)
        lines = raw.splitlines()
        chunks = []
        buf = []

        def _is_header(line):
            s = line.strip()
            if not s:
                return False
            if len(s) <= 2:
                return False
            if re.match(r"^\d+(\.\d+)+\b", s):
                return True
            if s.startswith(("规则", "风险控制", "数据验证", "操作周期", "买入类型", "大盘环境", "主力行为")):
                return True
            if s[0].isdigit():
                return True
            if s[0] in ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十"):
                return True
            return False

        current_len = 0
        for line in lines:
            if _is_header(line) and buf and current_len >= 200:
                chunks.append("\n".join(buf).strip())
                buf = [line]
                current_len = len(line)
                continue
            if current_len + len(line) + 1 > max_chars and buf:
                chunks.append("\n".join(buf).strip())
                buf = [line]
                current_len = len(line)
                continue
            buf.append(line)
            current_len += len(line) + 1

        if buf:
            chunks.append("\n".join(buf).strip())

        # If still too large, do hard split
        final = []
        for c in chunks:
            if len(c) <= max_chars:
                final.append(c)
                continue
            step = max_chars
            for i in range(0, len(c), step):
                final.append(c[i:i+step])
        return [c for c in final if c]

    def _call_once(self, text):
        if not self.client or not self.model:
            return []
        if not text or not str(text).strip():
            return []

        sys_prompt = (
            "You are a knowledge curator. Convert copied trading knowledge into a clean JSON format.\n"
            "Output JSON ONLY, no markdown.\n"
            "Schema:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\n"
            "      \"title\": \"\",\n"
            "      \"tags\": [\"\"],\n"
            "      \"content\": \"\",\n"
            "      \"structure\": {\n"
            "        \"timeframe\": \"\",\n"
            "        \"conditions\": \"\",\n"
            "        \"invalidations\": \"\",\n"
            "        \"risk\": \"\",\n"
            "        \"examples\": \"\"\n"
            "      }\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- If multiple entries exist, split into multiple items.\n"
            "- Treat each numbered subsection like '1.2', '2.1', '4.3', '9.1' as a separate item.\n"
            "- Keep numeric thresholds and logical relations (AND/OR) intact.\n"
            "- Do not omit details; summarize only duplicated phrases.\n"
            "- tags should be short keywords (<=5 items).\n"
            "- Each item MUST include structure fields: conditions, invalidations, risk, examples.\n"
            "- If any structure field is missing, set it to '无'."
        )
        user_prompt = f"[RAW]\n{text}"

        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2
            )
            raw = res.choices[0].message.content if res and res.choices else ""
        except Exception:
            return []

        data, cleaned = parse_json_safe(raw)
        log_llm("kb_import_kimi", self.model, raw, cleaned, ok=bool(data))
        if not data:
            return []
        return self._normalize_items(data)

    def organize(self, text):
        if not self.client or not self.model:
            return []
        if not text or not str(text).strip():
            return []
        chunks = self._split_text(text)
        all_items = []
        for chunk in chunks:
            items = self._call_once(chunk)
            if items:
                all_items.extend(items)
        return all_items
