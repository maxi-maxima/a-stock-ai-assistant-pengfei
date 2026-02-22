import datetime
import json
import os
import re
try:
    import yaml
except Exception:
    yaml = None

class KnowledgeBase:
    def __init__(self, filepath="data/knowledge_base.json"):
        self.filepath = filepath
        self.knowledge_base = []
        self._load()

    def _now(self):
        return datetime.datetime.now().isoformat(timespec="seconds")

    def _normalize_tags(self, tags):
        if tags is None:
            return []
        if isinstance(tags, (list, tuple, set)):
            return [str(t).strip() for t in tags if str(t).strip()]
        if isinstance(tags, str):
            text = tags
            for sep in ["，", ";", "；", "|", "/", " "]:
                text = text.replace(sep, ",")
            return [t.strip() for t in text.split(",") if t.strip()]
        val = str(tags).strip()
        return [val] if val else []

    def _normalize_structure(self, structure):
        base = {
            "conditions": "",
            "invalidations": "",
            "timeframe": "",
            "risk": "",
            "examples": ""
        }
        if not isinstance(structure, dict):
            return base
        out = {}
        for k, v in base.items():
            val = structure.get(k, v)
            if isinstance(val, (list, tuple, set)):
                val = "\n".join([str(x) for x in val])
            elif val is None:
                val = ""
            else:
                val = str(val)
            out[k] = val
        return out

    def _normalize_item(self, item):
        if not isinstance(item, dict):
            return False
        changed = False
        if "title" in item and item["title"] is not None:
            item["title"] = str(item["title"]).strip()
        if "content" in item and item["content"] is not None:
            item["content"] = str(item["content"])

        tags_norm = self._normalize_tags(item.get("tags"))
        if item.get("tags") != tags_norm:
            item["tags"] = tags_norm
            changed = True

        structure_norm = self._normalize_structure(item.get("structure"))
        if item.get("structure") != structure_norm:
            item["structure"] = structure_norm
            changed = True

        stats = item.get("stats")
        if not isinstance(stats, dict):
            stats = {}
            item["stats"] = stats
            changed = True
        for k in ["hits", "likes", "dislikes", "wins", "losses", "pnl_count"]:
            if k not in stats or not isinstance(stats.get(k), int):
                try:
                    stats[k] = int(stats.get(k) or 0)
                except Exception:
                    stats[k] = 0
                changed = True
        for k in ["score_adjust", "pnl_sum"]:
            if k not in stats:
                stats[k] = 0.0
                changed = True
            else:
                try:
                    stats[k] = float(stats.get(k) or 0)
                except Exception:
                    stats[k] = 0.0
                    changed = True
        if "last_used_at" not in stats:
            stats["last_used_at"] = ""
            changed = True
        if "last_pnl_at" not in stats:
            stats["last_pnl_at"] = ""
            changed = True

        if "created_at" not in item or not item.get("created_at"):
            item["created_at"] = item.get("date") or self._now()
            changed = True
        if "updated_at" not in item or not item.get("updated_at"):
            item["updated_at"] = item.get("created_at") or self._now()
            changed = True
        if "date" not in item or not item.get("date"):
            item["date"] = item.get("created_at") or self._now()
            changed = True
        return changed

    def _load(self):
        if not os.path.exists(self.filepath):
            self.knowledge_base = []
            self._save()
        else:
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.knowledge_base = json.load(f)
            except:
                self.knowledge_base = []
        changed = False
        for item in self.knowledge_base:
            if self._normalize_item(item):
                changed = True
        if changed:
            self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.knowledge_base, f, ensure_ascii=False, indent=2)

    def add_knowledge(self, title, content, tags="通用"):
        return self.add_knowledge_structured(title, content, tags=tags, structure=None)

    def add_knowledge_structured(self, title, content, tags="通用", structure=None):
        title = str(title).strip()
        content = str(content)
        tags_norm = self._normalize_tags(tags)
        structure_norm = self._normalize_structure(structure)
        for item in self.knowledge_base:
            if item.get('title') == title:
                item['content'] = content
                item['tags'] = tags_norm
                item['structure'] = structure_norm
                item['updated_at'] = self._now()
                if not item.get("created_at"):
                    item["created_at"] = item.get("date") or self._now()
                self._save()
                return
        
        self.knowledge_base.append({
            "title": title,
            "content": content,
            "tags": tags_norm,
            "structure": structure_norm,
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "created_at": self._now(),
            "updated_at": self._now(),
            "stats": {
                "hits": 0,
                "likes": 0,
                "dislikes": 0,
                "wins": 0,
                "losses": 0,
                "pnl_sum": 0.0,
                "pnl_count": 0,
                "score_adjust": 0.0,
                "last_used_at": "",
                "last_pnl_at": ""
            }
        })
        self._save()

    def update_knowledge(self, old_title, new_title, content, tags="通用"):
        return self.update_knowledge_structured(old_title, new_title, content, tags=tags, structure=None)

    def update_knowledge_structured(self, old_title, new_title, content, tags="通用", structure=None):
        old_title = str(old_title).strip()
        new_title = str(new_title).strip()
        content = str(content)
        tags_norm = self._normalize_tags(tags)
        structure_norm = self._normalize_structure(structure)
        if not old_title:
            return False, "原标题为空"
        if not new_title:
            return False, "新标题为空"

        target = None
        for item in self.knowledge_base:
            if item.get("title") == old_title:
                target = item
                break
        if target is None:
            return False, "未找到原条目"

        if new_title != old_title:
            for item in self.knowledge_base:
                if item.get("title") == new_title:
                    return False, "新标题已存在"

        target["title"] = new_title
        target["content"] = content
        target["tags"] = tags_norm
        target["structure"] = structure_norm
        target["updated_at"] = self._now()
        if "stats" not in target:
            target["stats"] = {"hits": 0, "likes": 0, "dislikes": 0, "score_adjust": 0.0, "last_used_at": ""}
        if not target.get("created_at"):
            target["created_at"] = target.get("date") or self._now()
        if not target.get("date"):
            target["date"] = target.get("created_at")
        self._save()
        return True, "更新成功"

    def delete_knowledge(self, title):
        initial_len = len(self.knowledge_base)
        self.knowledge_base = [k for k in self.knowledge_base if k['title'] != title]
        if len(self.knowledge_base) < initial_len:
            self._save()
            return True
        return False

    def get_all_knowledge(self):
        return self.knowledge_base

    def search_knowledge(self, query):
        q = str(query or "").strip().lower()
        if not q:
            return self.knowledge_base
        result = []
        for k in self.knowledge_base:
            title = str(k.get("title", "")).lower()
            content = str(k.get("content", "")).lower()
            tags = " ".join(self._normalize_tags(k.get("tags"))).lower()
            structure = k.get("structure", {})
            struct_text = " ".join([str(v) for v in structure.values()]).lower() if isinstance(structure, dict) else ""
            if q in title or q in content or q in tags or q in struct_text:
                result.append(k)
        return result

    # 🔥 新增：兼容性方法，防止 tactics.py 报错
    def search_relevant_knowledge(self, query, limit=5):
        q = str(query or "").strip().lower()
        if not q:
            return []

        tokens = self._tokenize(q)
        scored = []
        for item in self.knowledge_base:
            score = self._score_item(item, q, tokens)
            if score > 0:
                row = dict(item)
                row["score"] = score
                scored.append(row)
        scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        if limit and len(scored) > limit:
            scored = scored[:limit]
        return scored

    def format_knowledge_context(self, items, max_chars=1200):
        if not items:
            return "无特定战法"
        lines = []
        total = 0
        for item in items:
            title = item.get("title", "无标题")
            tags = "/".join(self._normalize_tags(item.get("tags")))
            structure = item.get("structure", {}) if isinstance(item.get("structure", {}), dict) else {}
            content = str(item.get("content", "")).strip()
            content_short = content.replace("\n", " ")
            if len(content_short) > 200:
                content_short = content_short[:200] + "..."
            stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
            hits = stats.get("hits", 0)
            likes = stats.get("likes", 0)
            dislikes = stats.get("dislikes", 0)
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            pnl_sum = stats.get("pnl_sum", 0)
            pnl_count = stats.get("pnl_count", 0)
            avg_pnl = (float(pnl_sum) / pnl_count) if pnl_count else 0.0
            win_rate = (float(wins) / pnl_count) if pnl_count else 0.0

            parts = [f"【{title}】[{tags}]"]
            if hits or likes or dislikes:
                parts.append(f"- 参考热度: {hits} | 👍 {likes} | 👎 {dislikes}")
            if pnl_count:
                parts.append(f"- 战果: 胜率 {win_rate*100:.1f}% | 平均盈亏 {avg_pnl:.2f}")
            if structure.get("timeframe"):
                parts.append(f"- 适用周期: {structure.get('timeframe')}")
            if structure.get("conditions"):
                parts.append(f"- 触发条件: {structure.get('conditions')}")
            if structure.get("invalidations"):
                parts.append(f"- 失效条件: {structure.get('invalidations')}")
            if structure.get("risk"):
                parts.append(f"- 风险: {structure.get('risk')}")
            if structure.get("examples"):
                parts.append(f"- 例子: {structure.get('examples')}")
            if content_short:
                parts.append(f"- 摘要: {content_short}")

            block = "\n".join(parts)
            total += len(block)
            if total > max_chars:
                break
            lines.append(block)
        return "\n\n".join(lines) if lines else "无特定战法"

    def build_context(self, query, limit=5):
        items = self.search_relevant_knowledge(query, limit=limit)
        return {
            "items": items,
            "titles": [i.get("title") for i in items if i.get("title")],
            "context": self.format_knowledge_context(items)
        }

    def _tokenize(self, text):
        text = str(text or "").lower()
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text)
        return [t for t in tokens if t.strip()]

    def _normalize_text(self, text):
        text = str(text or "").lower()
        text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
        return text.strip()

    def _jaccard(self, a, b):
        if not a or not b:
            return 0.0
        sa = set(a)
        sb = set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / max(1, len(sa | sb))

    def _calc_similarity(self, title_a, content_a, title_b, content_b):
        ta = self._tokenize(title_a)
        tb = self._tokenize(title_b)
        ca = self._tokenize(content_a)
        cb = self._tokenize(content_b)
        title_sim = self._jaccard(ta, tb)
        content_sim = self._jaccard(ca, cb)
        score = 0.6 * title_sim + 0.4 * content_sim
        tna = self._normalize_text(title_a)
        tnb = self._normalize_text(title_b)
        if tna and tnb:
            if tna == tnb:
                score = max(score, 0.95)
            elif tna in tnb or tnb in tna:
                score = max(score, 0.85)
        return score

    def _auto_score_item(self, item):
        if not isinstance(item, dict):
            return 0.0
        score = 0.0
        content = str(item.get("content", "") or "")
        tags = self._normalize_tags(item.get("tags"))
        structure = item.get("structure", {}) if isinstance(item.get("structure", {}), dict) else {}

        if len(content) >= 200:
            score += 1.0
        if len(tags) >= 2:
            score += 1.0
        if structure.get("conditions"):
            score += 1.0
        if structure.get("invalidations"):
            score += 0.5
        if structure.get("risk"):
            score += 0.5
        if structure.get("examples"):
            score += 0.5
        if structure.get("timeframe"):
            score += 0.5
        return min(5.0, score)

    def _merge_item(self, existing, incoming):
        if not isinstance(existing, dict) or not isinstance(incoming, dict):
            return existing
        # merge tags
        tags = self._normalize_tags(existing.get("tags")) + self._normalize_tags(incoming.get("tags"))
        tags = self._normalize_tags(tags)
        existing["tags"] = tags

        # merge structure fields
        structure = existing.get("structure", {}) if isinstance(existing.get("structure", {}), dict) else {}
        inc_struct = incoming.get("structure", {}) if isinstance(incoming.get("structure", {}), dict) else {}
        structure = self._normalize_structure(structure)
        inc_struct = self._normalize_structure(inc_struct)
        for k, v in inc_struct.items():
            if not v:
                continue
            if not structure.get(k):
                structure[k] = v
            elif v not in structure.get(k):
                structure[k] = (structure.get(k) + "\n" + v).strip()
        existing["structure"] = structure

        # merge content
        content = str(existing.get("content", "") or "")
        inc_content = str(incoming.get("content", "") or "")
        if inc_content and inc_content not in content:
            if content:
                content = content + "\n\n---\n\n" + inc_content
            else:
                content = inc_content
        existing["content"] = content

        # update stats
        stats = existing.get("stats") if isinstance(existing.get("stats"), dict) else {}
        try:
            stats["merge_count"] = int(stats.get("merge_count", 0) or 0) + 1
        except Exception:
            stats["merge_count"] = 1
        existing["stats"] = stats
        existing["updated_at"] = self._now()
        return existing

    def _find_similar_item(self, title, content, threshold=0.78):
        best = None
        best_score = 0.0
        for item in self.knowledge_base:
            if not isinstance(item, dict):
                continue
            score = self._calc_similarity(title, content, item.get("title", ""), item.get("content", ""))
            if score > best_score:
                best = item
                best_score = score
        if best and best_score >= float(threshold):
            return best, best_score
        return None, best_score

    def _score_item(self, item, query, tokens):
        if not isinstance(item, dict):
            return 0
        title = str(item.get("title", "")).lower()
        content = str(item.get("content", "")).lower()
        tags = " ".join(self._normalize_tags(item.get("tags"))).lower()
        structure = item.get("structure", {})
        struct_text = " ".join([str(v) for v in structure.values()]).lower() if isinstance(structure, dict) else ""

        score = 0
        if query in title:
            score += 6
        if query in tags:
            score += 4
        if query in content or query in struct_text:
            score += 2
        for t in tokens:
            if t in title:
                score += 3
            elif t in tags:
                score += 2
            elif t in content or t in struct_text:
                score += 1
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        hits = int(stats.get("hits", 0) or 0)
        likes = int(stats.get("likes", 0) or 0)
        dislikes = int(stats.get("dislikes", 0) or 0)
        try:
            adj = float(stats.get("score_adjust", 0) or 0)
        except Exception:
            adj = 0.0
        wins = int(stats.get("wins", 0) or 0)
        losses = int(stats.get("losses", 0) or 0)
        try:
            pnl_sum = float(stats.get("pnl_sum", 0) or 0)
        except Exception:
            pnl_sum = 0.0
        pnl_count = int(stats.get("pnl_count", 0) or 0)
        score += min(hits, 20) * 0.2
        score += likes * 1.5
        score -= dislikes * 2.0
        if pnl_count > 0:
            avg_pnl = pnl_sum / pnl_count
            score += max(-3.0, min(3.0, avg_pnl / 1000.0))
            score += (wins - losses) * 0.3
        score += adj
        return score

    def record_usage(self, items):
        if not items:
            return
        titles = []
        for item in items:
            if isinstance(item, str):
                titles.append(item)
            elif isinstance(item, dict) and item.get("title"):
                titles.append(item.get("title"))
        title_set = {t for t in titles if t}
        if not title_set:
            return
        now = self._now()
        changed = False
        for item in self.knowledge_base:
            if item.get("title") in title_set:
                stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
                stats["hits"] = int(stats.get("hits", 0) or 0) + 1
                stats["last_used_at"] = now
                item["stats"] = stats
                changed = True
        if changed:
            self._save()

    def record_feedback(self, title, delta):
        title = str(title or "").strip()
        if not title:
            return False
        changed = False
        for item in self.knowledge_base:
            if item.get("title") == title:
                stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
                if int(delta) > 0:
                    stats["likes"] = int(stats.get("likes", 0) or 0) + 1
                else:
                    stats["dislikes"] = int(stats.get("dislikes", 0) or 0) + 1
                stats["last_used_at"] = self._now()
                item["stats"] = stats
                changed = True
                break
        if changed:
            self._save()
        return changed

    def record_trade_effect(self, title, pnl, ts=None):
        title = str(title or "").strip()
        if not title:
            return False
        try:
            pnl = float(pnl)
        except Exception:
            pnl = 0.0
        ts_str = ""
        if ts:
            if isinstance(ts, str):
                ts_str = ts
            elif isinstance(ts, datetime.datetime):
                ts_str = ts.isoformat(timespec="seconds")
            elif isinstance(ts, datetime.date):
                ts_str = datetime.datetime.combine(ts, datetime.time.min).isoformat(timespec="seconds")
        if not ts_str:
            ts_str = self._now()

        changed = False
        for item in self.knowledge_base:
            if item.get("title") == title:
                stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
                stats["pnl_sum"] = float(stats.get("pnl_sum", 0) or 0) + pnl
                stats["pnl_count"] = int(stats.get("pnl_count", 0) or 0) + 1
                if pnl > 0:
                    stats["wins"] = int(stats.get("wins", 0) or 0) + 1
                elif pnl < 0:
                    stats["losses"] = int(stats.get("losses", 0) or 0) + 1
                stats["last_pnl_at"] = ts_str
                item["stats"] = stats
                changed = True
                break
        if changed:
            self._save()
        return changed

    def update_effect_stats(self, effects):
        if not effects:
            return False
        effect_map = {}
        if isinstance(effects, dict):
            effect_map = effects
        elif isinstance(effects, (list, tuple)):
            for item in effects:
                if isinstance(item, dict) and item.get("title"):
                    effect_map[item["title"]] = item
        if not effect_map:
            return False

        changed = False
        for item in self.knowledge_base:
            title = item.get("title")
            if not title or title not in effect_map:
                continue
            eff = effect_map[title]
            stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
            try:
                stats["pnl_sum"] = float(eff.get("pnl_sum", 0) or 0)
            except Exception:
                stats["pnl_sum"] = 0.0
            try:
                stats["pnl_count"] = int(eff.get("pnl_count", 0) or 0)
            except Exception:
                stats["pnl_count"] = 0
            try:
                stats["wins"] = int(eff.get("wins", 0) or 0)
            except Exception:
                stats["wins"] = 0
            try:
                stats["losses"] = int(eff.get("losses", 0) or 0)
            except Exception:
                stats["losses"] = 0
            stats["last_pnl_at"] = eff.get("last_ts", "") or stats.get("last_pnl_at", "")
            item["stats"] = stats
            changed = True
        if changed:
            self._save()
        return changed

    def _split_copied_entries(self, text):
        text = str(text or "").strip()
        if not text:
            return []
        # Don't split JSON/YAML blobs
        if text.startswith("{") or text.startswith("["):
            return [text]
        if text.startswith("---"):
            return [text]

        lines = text.splitlines()
        entries = []
        buf = []

        section_labels = [
            "触发条件", "条件", "入场条件", "买入条件", "信号", "适用周期", "周期",
            "失效条件", "退出条件", "止损条件", "风险", "风险提示", "例子", "案例", "示例",
            "内容", "正文", "描述", "总结", "标签", "标题", "Title", "Tags", "Content"
        ]

        def _is_separator(line):
            s = line.strip()
            if not s:
                return False
            return s in ("---", "====", "=====", "*****") or (len(s) >= 3 and set(s) in ({"-"}, {"="}, {"*"}))

        def _is_new_entry_header(line):
            s = line.strip()
            if not s:
                return False
            if s.startswith("###"):
                name = s.lstrip("#").strip()
                for label in section_labels:
                    if name.lower().startswith(label.lower()):
                        return False
                return True
            if re.match(r"^(标题|Title)\s*[:：].+", s, flags=re.IGNORECASE):
                return True
            return False

        for line in lines:
            if _is_separator(line):
                if buf:
                    entries.append("\n".join(buf).strip())
                    buf = []
                continue
            if _is_new_entry_header(line) and buf:
                entries.append("\n".join(buf).strip())
                buf = [line]
                continue
            buf.append(line)
        if buf:
            entries.append("\n".join(buf).strip())
        return [e for e in entries if e]

    def _parse_kv(self, line):
        if ":" in line:
            parts = line.split(":", 1)
            return parts[0].strip(), parts[1].strip()
        if "：" in line:
            parts = line.split("：", 1)
            return parts[0].strip(), parts[1].strip()
        return None, None

    def _parse_copied_entry(self, text, default_tags=""):
        raw = str(text or "").strip()
        if not raw:
            return None

        # JSON support
        if raw.startswith("{") or raw.startswith("["):
            try:
                data = json.loads(raw)
                return self._normalize_import_payload(data, default_tags=default_tags)
            except Exception:
                pass

        # YAML support (optional)
        if yaml and raw.startswith("---"):
            try:
                data = yaml.safe_load(raw)
                return self._normalize_import_payload(data, default_tags=default_tags)
            except Exception:
                pass

        title = ""
        tags = []
        structure = {"timeframe": "", "conditions": "", "invalidations": "", "risk": "", "examples": ""}
        content_lines = []
        section = None
        sections = {
            "content": [],
            "conditions": [],
            "invalidations": [],
            "risk": [],
            "examples": [],
            "timeframe": []
        }

        def _match_section_label(s):
            s = s.strip().lower()
            mapping = {
                "适用周期": "timeframe",
                "周期": "timeframe",
                "timeframe": "timeframe",
                "触发条件": "conditions",
                "条件": "conditions",
                "入场条件": "conditions",
                "买入条件": "conditions",
                "信号": "conditions",
                "conditions": "conditions",
                "失效条件": "invalidations",
                "退出条件": "invalidations",
                "止损条件": "invalidations",
                "invalidations": "invalidations",
                "风险": "risk",
                "风险提示": "risk",
                "risk": "risk",
                "例子": "examples",
                "案例": "examples",
                "示例": "examples",
                "examples": "examples",
                "内容": "content",
                "正文": "content",
                "描述": "content",
                "总结": "content",
                "content": "content"
            }
            for k, v in mapping.items():
                if s.startswith(k.lower()):
                    return v
            return None

        lines = raw.splitlines()
        for line in lines:
            s = line.strip()
            if not s:
                continue
            # Title
            m = re.match(r"^(#+\s*)?(标题|title|名称)\s*[:：]\s*(.+)$", s, flags=re.IGNORECASE)
            if m:
                title = m.group(3).strip()
                section = None
                continue
            # Tags
            m = re.match(r"^(标签|tags)\s*[:：]\s*(.+)$", s, flags=re.IGNORECASE)
            if m:
                tags = self._normalize_tags(m.group(2))
                section = None
                continue
            # Section header
            sec = _match_section_label(s.lstrip("#").strip())
            if sec:
                section = sec
                continue

            # KV inline
            key, val = self._parse_kv(s)
            if key and val:
                sec = _match_section_label(key)
                if sec:
                    sections[sec].append(val)
                    continue

            # Hash tags
            if "#" in s:
                hash_tags = re.findall(r"#([A-Za-z0-9_\u4e00-\u9fff]+)", s)
                if hash_tags:
                    tags.extend(hash_tags)

            # Append to current section or content
            if section in sections:
                sections[section].append(s.lstrip("-*• ").strip())
            else:
                content_lines.append(s)

        if not title:
            # use the first non-empty content line as title
            for line in content_lines:
                if line:
                    title = line[:60]
                    break

        # Build content
        content = ""
        if sections["content"]:
            content = "\n".join([l for l in sections["content"] if l]).strip()
        if not content:
            content = "\n".join([l for l in content_lines if l]).strip()
        if not content:
            # fallback to structured fields
            parts = []
            for k in ["conditions", "invalidations", "risk", "examples", "timeframe"]:
                if sections.get(k):
                    parts.append(f"{k}:\n" + "\n".join(sections[k]))
            content = "\n\n".join(parts).strip()

        structure["timeframe"] = "\n".join(sections["timeframe"]).strip()
        structure["conditions"] = "\n".join(sections["conditions"]).strip()
        structure["invalidations"] = "\n".join(sections["invalidations"]).strip()
        structure["risk"] = "\n".join(sections["risk"]).strip()
        structure["examples"] = "\n".join(sections["examples"]).strip()

        if default_tags:
            tags = self._normalize_tags(tags) + self._normalize_tags(default_tags)
        tags = self._normalize_tags(tags)

        return {
            "title": title.strip(),
            "tags": tags,
            "content": content,
            "structure": structure
        }

    def _normalize_import_payload(self, data, default_tags=""):
        items = []
        if isinstance(data, dict):
            if "items" in data and isinstance(data.get("items"), list):
                items = data.get("items")
            else:
                items = [data]
        elif isinstance(data, list):
            items = data
        else:
            return []

        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("strategy") or "").strip()
            tags = item.get("tags") or item.get("tag") or item.get("labels") or ""
            content = item.get("content") or item.get("text") or item.get("body") or ""
            structure = item.get("structure") or {}
            if not isinstance(structure, dict):
                structure = {}
            if not structure:
                structure = {
                    "timeframe": item.get("timeframe") or item.get("period") or "",
                    "conditions": item.get("conditions") or item.get("setup") or "",
                    "invalidations": item.get("invalidations") or item.get("exit") or "",
                    "risk": item.get("risk") or "",
                    "examples": item.get("examples") or ""
                }
            if default_tags:
                tags = self._normalize_tags(tags) + self._normalize_tags(default_tags)
            tags = self._normalize_tags(tags)

            if not content:
                # fallback: stringify non-empty fields
                parts = []
                for k in ("summary", "notes", "idea"):
                    if item.get(k):
                        parts.append(str(item.get(k)))
                for k in ("conditions", "invalidations", "risk", "examples", "timeframe"):
                    if structure.get(k):
                        parts.append(f"{k}: {structure.get(k)}")
                content = "\n".join([p for p in parts if p]).strip()

            out.append({
                "title": title,
                "tags": tags,
                "content": content,
                "structure": self._normalize_structure(structure)
            })
        return out

    def parse_copied_knowledge(self, text, default_tags="", split_entries=True, use_llm=False):
        if not text:
            return []
        self._last_llm_used = bool(use_llm)
        self._last_llm_ok = False
        if use_llm:
            try:
                from core.knowledge_llm import KimiKnowledgeOrganizer
                organizer = KimiKnowledgeOrganizer()
                items = organizer.organize(text)
                if items:
                    # merge default tags
                    if default_tags:
                        for it in items:
                            if isinstance(it, dict):
                                tags = self._normalize_tags(it.get("tags")) + self._normalize_tags(default_tags)
                                it["tags"] = self._normalize_tags(tags)
                    self._last_llm_ok = True
                    return items
            except Exception:
                pass
        entries = [str(text)]
        if split_entries:
            entries = self._split_copied_entries(text)
        parsed = []
        for e in entries:
            item = self._parse_copied_entry(e, default_tags=default_tags)
            if not item:
                continue
            if isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict):
                        parsed.append(sub)
            elif isinstance(item, dict):
                parsed.append(item)
        return parsed

    def import_copied_knowledge(self, text, default_tags="", split_entries=True, auto_score=True, dedup=True, merge_similar=True, similarity_threshold=0.78, use_llm=False):
        items = self.parse_copied_knowledge(text, default_tags=default_tags, split_entries=split_entries, use_llm=use_llm)
        if not items:
            return {"added": 0, "items": []}
        added = 0
        merged = 0
        skipped = 0
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        for idx, item in enumerate(items, 1):
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            if not title:
                title = f"未命名战法-{ts}-{idx}"
            if not content:
                skipped += 1
                continue
            tags = item.get("tags") or default_tags
            structure = item.get("structure") if isinstance(item.get("structure"), dict) else {}
            candidate = {"title": title, "content": content, "tags": tags, "structure": structure}

            if dedup:
                existing, score = self._find_similar_item(title, content, threshold=similarity_threshold)
                if existing and merge_similar:
                    self._merge_item(existing, candidate)
                    if auto_score:
                        stats = existing.get("stats") if isinstance(existing.get("stats"), dict) else {}
                        stats["score_adjust"] = float(stats.get("score_adjust", 0) or 0) + self._auto_score_item(candidate)
                        existing["stats"] = stats
                    merged += 1
                    continue
                if existing and not merge_similar:
                    skipped += 1
                    continue

            self.add_knowledge_structured(title, content, tags, structure=structure)
            if auto_score:
                try:
                    for it in self.knowledge_base:
                        if it.get("title") == title:
                            stats = it.get("stats") if isinstance(it.get("stats"), dict) else {}
                            stats["score_adjust"] = float(stats.get("score_adjust", 0) or 0) + self._auto_score_item(candidate)
                            it["stats"] = stats
                            it["updated_at"] = self._now()
                            break
                    self._save()
                except Exception:
                    pass
            added += 1
        return {"added": added, "merged": merged, "skipped": skipped, "items": items}
