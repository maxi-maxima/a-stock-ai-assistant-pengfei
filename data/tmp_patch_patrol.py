from pathlib import Path

p = Path('ui/modules/patrol.py')
text = p.read_text(encoding='utf-8', errors='replace')
old = """                                    \"min_score\": min_score,\n                                    \"fin_enabled\": enable_fin_score,\n"""
new = """                                    \"min_score\": min_score,\n                                    \"sort_by\": sort_by,\n                                    \"fin_enabled\": enable_fin_score,\n"""
if old in text and new not in text:
    text = text.replace(old, new)
    p.write_text(text, encoding='utf-8')
