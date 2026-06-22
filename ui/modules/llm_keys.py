# -*- coding: utf-8 -*-
import hashlib
import json
import os

import streamlit as st
import yaml

from core.llm_resolver import (
    apply_input_overrides,
    resolve_brain_settings,
    resolve_general_settings,
    source_label_zh,
)


SECURE_SETTINGS_PATH = "data/secure_settings.json"
AUTH_PATH = "data/system_auth.json"
LLM_CONFIG_PATH = "config/llm_config.yaml"
LETTA_CONFIG_PATH = "config/letta.json"


MODEL_PRESETS = [
    "deepseek-chat",
    "deepseek-reasoner",
    "qwen3-max",
    "qwen2.5-72b-instruct",
    "moonshot-v1-8k",
    "moonshot-v1-32k",
    "moonshot-v1-128k",
    "kimi-k2.5",
    "kimi-k1.5",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo",
]


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _load_yaml(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _save_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def _clean_str(val):
    if val is None:
        return ""
    try:
        return str(val).strip()
    except Exception:
        return ""


def _mask_token(token):
    token = _clean_str(token)
    if not token:
        return ""
    if len(token) <= 6:
        return "*" * len(token)
    return token[:2] + "*" * (len(token) - 4) + token[-2:]


def _hash_password(password, salt):
    raw = (salt + password).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _get_auth_record():
    return _load_json(AUTH_PATH, {})


def _set_password(new_password):
    salt = os.urandom(8).hex()
    record = {"salt": salt, "hash": _hash_password(new_password, salt)}
    return _save_json(AUTH_PATH, record)


def _verify_password(password):
    env_pw = _clean_str(os.getenv("SYSTEM_ADMIN_PASSWORD"))
    if env_pw:
        return _clean_str(password) == env_pw
    record = _get_auth_record()
    salt = _clean_str(record.get("salt"))
    stored = _clean_str(record.get("hash"))
    if not salt or not stored:
        return False
    return _hash_password(_clean_str(password), salt) == stored


def _select_model(label, current, key_prefix):
    current = _clean_str(current)
    options = list(MODEL_PRESETS) + ["自定义"]
    index = options.index(current) if current in MODEL_PRESETS else len(options) - 1
    choice = st.selectbox(label, options, index=index, key=f"{key_prefix}_select")
    if choice == "自定义":
        custom = st.text_input(
            f"{label}（自定义）",
            value=current if current not in MODEL_PRESETS else "",
            key=f"{key_prefix}_custom",
        )
        return _clean_str(custom)
    return choice


def _test_llm(api_key, base_url, model):
    api_key = _clean_str(api_key)
    base_url = _clean_str(base_url)
    model = _clean_str(model)
    if not api_key:
        return False, "缺少 API Key"
    if not model:
        return False, "缺少模型"
    try:
        from openai import OpenAI
    except Exception as exc:
        return False, f"OpenAI SDK 导入失败: {exc}"
    try:
        client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=10.0)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            temperature=1,
            max_tokens=1,
        )
        content = ""
        if resp and getattr(resp, "choices", None):
            content = resp.choices[0].message.content or ""
        return True, content.strip() or "ok"
    except Exception as exc:
        return False, str(exc)


def _run_brain_test(brain_name, secure, llm_conf, api_key_input="", base_url_input="", model_input=""):
    setting = resolve_brain_settings(brain_name, secure=secure, conf=llm_conf, load_environment=False)
    setting = apply_input_overrides(
        setting,
        api_key=api_key_input,
        base_url=base_url_input,
        model=model_input,
    )
    ok, msg = _test_llm(setting.get("api_key"), setting.get("base_url"), setting.get("model"))
    return ok, msg, setting


def _auth_gate():
    auth_ok = st.session_state.get("llm_auth_ok", False)
    env_pw = _clean_str(os.getenv("SYSTEM_ADMIN_PASSWORD"))
    auth_record = _get_auth_record()

    if not env_pw and not _clean_str(auth_record.get("hash")):
        st.info("未设置管理员密码，请先设置。")
        new_pw = st.text_input("设置管理员密码", type="password", key="llm_new_pw")
        new_pw2 = st.text_input("确认管理员密码", type="password", key="llm_new_pw2")
        if st.button("保存管理员密码", key="llm_set_pw"):
            if len(_clean_str(new_pw)) < 6:
                st.error("密码至少 6 位。")
            elif _clean_str(new_pw) != _clean_str(new_pw2):
                st.error("两次输入不一致。")
            elif _set_password(new_pw):
                st.success("管理员密码已设置。")
            else:
                st.error("保存失败，请检查权限。")
        st.stop()

    if not auth_ok:
        pw = st.text_input("输入管理员密码解锁", type="password", key="llm_auth_pw")
        if st.button("解锁", key="llm_unlock"):
            if _verify_password(pw):
                st.session_state["llm_auth_ok"] = True
                st.success("已解锁。")
            else:
                st.error("密码错误。")
        st.stop()


def render():
    st.header("三脑 API 配置工具")
    st.caption("统一优先级：环境变量(本脑>通用) > 安全存储(本脑>通用) > 配置文件(本脑>通用)")

    secure = _load_json(SECURE_SETTINGS_PATH, {})
    llm_conf = _load_yaml(LLM_CONFIG_PATH, {})

    _auth_gate()

    st.subheader("当前密钥状态")
    st.caption(f"蓝脑密钥: {_mask_token(secure.get('blue_brain_api_key')) or '-'}")
    st.caption(f"红脑密钥: {_mask_token(secure.get('red_brain_api_key')) or '-'}")
    st.caption(f"绿脑密钥: {_mask_token(secure.get('green_brain_api_key')) or '-'}")
    st.caption(f"通用密钥: {_mask_token(secure.get('llm_api_key')) or '-'}")

    st.divider()
    st.subheader("三脑 API 密钥")
    same_key = st.checkbox("三脑使用同一 API 密钥", value=True, key="llm_same_key")
    overwrite_empty = st.checkbox("允许空值覆盖（清空）", value=False, key="llm_overwrite_empty")

    if same_key:
        all_key = st.text_input("统一 API 密钥", type="password", key="llm_all_key")
        blue_key = all_key
        red_key = all_key
        green_key = all_key
    else:
        blue_key = st.text_input("蓝脑 API 密钥", type="password", key="llm_blue_key")
        red_key = st.text_input("红脑 API 密钥", type="password", key="llm_red_key")
        green_key = st.text_input("绿脑 API 密钥", type="password", key="llm_green_key")

    st.caption("测试优先级：当前输入 > 环境变量 > 安全存储 > 配置文件")
    c1, c2, c3 = st.columns(3)
    if c1.button("测试 蓝脑", key="llm_test_blue"):
        ok, msg, setting = _run_brain_test("blue", secure, llm_conf, api_key_input=blue_key)
        if ok:
            st.success(f"蓝脑测试成功 ({setting.get('model')})")
        else:
            st.error(f"蓝脑测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )
    if c2.button("测试 红脑", key="llm_test_red"):
        ok, msg, setting = _run_brain_test("red", secure, llm_conf, api_key_input=red_key)
        if ok:
            st.success(f"红脑测试成功 ({setting.get('model')})")
        else:
            st.error(f"红脑测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )
    if c3.button("测试 绿脑", key="llm_test_green"):
        ok, msg, setting = _run_brain_test("green", secure, llm_conf, api_key_input=green_key)
        if ok:
            st.success(f"绿脑测试成功 ({setting.get('model')})")
        else:
            st.error(f"绿脑测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )

    if st.button("写入三脑 API 密钥", key="llm_write_keys"):
        updated = dict(secure) if isinstance(secure, dict) else {}
        for k, v in (
            ("blue_brain_api_key", _clean_str(blue_key)),
            ("red_brain_api_key", _clean_str(red_key)),
            ("green_brain_api_key", _clean_str(green_key)),
        ):
            if v:
                updated[k] = v
            elif overwrite_empty:
                updated[k] = ""
        if _save_json(SECURE_SETTINGS_PATH, updated):
            st.success("已写入安全存储，请刷新页面。")
        else:
            st.error("写入失败，请检查权限。")

    st.divider()
    st.subheader("大模型接口地址 / 模型设置")
    same_endpoint = st.checkbox("统一三脑 base_url + 模型", value=False, key="llm_same_endpoint")
    overwrite_empty_cfg = st.checkbox("允许空值覆盖配置（清空）", value=False, key="llm_overwrite_empty_cfg")

    def _conf_get(section, key, default=""):
        sec = llm_conf.get(section, {}) if isinstance(llm_conf.get(section), dict) else {}
        return _clean_str(sec.get(key, default))

    if same_endpoint:
        base_url_all = st.text_input("统一接口地址", value=_conf_get("blue_brain", "base_url"), key="llm_base_url_all")
        model_all = _select_model("统一模型", _conf_get("blue_brain", "model"), "llm_model_all")
        blue_base = red_base = green_base = base_url_all
        blue_model = red_model = green_model = model_all
    else:
        b1, b2, b3 = st.columns(3)
        with b1:
            st.caption("蓝脑")
            blue_base = st.text_input("蓝脑接口地址", value=_conf_get("blue_brain", "base_url"), key="llm_blue_base")
            blue_model = _select_model("蓝脑模型", _conf_get("blue_brain", "model"), "llm_blue_model")
        with b2:
            st.caption("红脑")
            red_base = st.text_input("红脑接口地址", value=_conf_get("red_brain", "base_url"), key="llm_red_base")
            red_model = _select_model("红脑模型", _conf_get("red_brain", "model"), "llm_red_model")
        with b3:
            st.caption("绿脑")
            green_base = st.text_input("绿脑接口地址", value=_conf_get("green_brain", "base_url"), key="llm_green_base")
            green_model = _select_model("绿脑模型", _conf_get("green_brain", "model"), "llm_green_model")

    st.caption("测试优先级：当前输入 > 环境变量 > 安全存储 > 配置文件")
    t1, t2, t3 = st.columns(3)
    if t1.button("测试 蓝脑(base/model)", key="llm_test_blue_cfg"):
        ok, msg, setting = _run_brain_test(
            "blue",
            secure,
            llm_conf,
            api_key_input=blue_key,
            base_url_input=blue_base,
            model_input=blue_model,
        )
        if ok:
            st.success(f"蓝脑测试成功 ({setting.get('model')})")
        else:
            st.error(f"蓝脑测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )
    if t2.button("测试 红脑(base/model)", key="llm_test_red_cfg"):
        ok, msg, setting = _run_brain_test(
            "red",
            secure,
            llm_conf,
            api_key_input=red_key,
            base_url_input=red_base,
            model_input=red_model,
        )
        if ok:
            st.success(f"红脑测试成功 ({setting.get('model')})")
        else:
            st.error(f"红脑测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )
    if t3.button("测试 绿脑(base/model)", key="llm_test_green_cfg"):
        ok, msg, setting = _run_brain_test(
            "green",
            secure,
            llm_conf,
            api_key_input=green_key,
            base_url_input=green_base,
            model_input=green_model,
        )
        if ok:
            st.success(f"绿脑测试成功 ({setting.get('model')})")
        else:
            st.error(f"绿脑测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )

    if st.button("保存大模型接口地址/模型", key="llm_save_endpoints"):
        updated = dict(llm_conf) if isinstance(llm_conf, dict) else {}
        for sec, base, model in (
            ("blue_brain", _clean_str(blue_base), _clean_str(blue_model)),
            ("red_brain", _clean_str(red_base), _clean_str(red_model)),
            ("green_brain", _clean_str(green_base), _clean_str(green_model)),
        ):
            s = updated.get(sec, {}) if isinstance(updated.get(sec), dict) else {}
            if base or overwrite_empty_cfg:
                s["base_url"] = base
            if model or overwrite_empty_cfg:
                s["model"] = model
            updated[sec] = s
        if _save_yaml(LLM_CONFIG_PATH, updated):
            st.success("已写入 config/llm_config.yaml，请重启或刷新页面。")
        else:
            st.error("写入 config/llm_config.yaml 失败。")

    st.divider()
    st.subheader("通用 LLM 覆盖配置")
    st.caption("写入 data/secure_settings.json（llm_base_url / llm_model / llm_api_key）")

    llm_base_url_override = st.text_input(
        "llm_base_url",
        value=_clean_str(secure.get("llm_base_url")),
        key="llm_secure_base",
    )
    llm_model_override = _select_model("llm_model", _clean_str(secure.get("llm_model")), "llm_secure_model")
    llm_api_key_override = st.text_input("llm_api_key", type="password", key="llm_secure_key")

    if st.button("测试通用 LLM", key="llm_test_general"):
        setting = resolve_general_settings(secure=secure, conf=llm_conf, load_environment=False)
        setting = apply_input_overrides(
            setting,
            api_key=llm_api_key_override,
            base_url=llm_base_url_override,
            model=llm_model_override,
        )
        ok, msg = _test_llm(setting.get("api_key"), setting.get("base_url"), setting.get("model"))
        if ok:
            st.success(f"通用 LLM 测试成功 ({setting.get('model')})")
        else:
            st.error(f"通用 LLM 测试失败: {msg}")
        st.caption(
            f"来源: key={source_label_zh(setting.get('api_key_source'))}, "
            f"base_url={source_label_zh(setting.get('base_url_source'))}, "
            f"model={source_label_zh(setting.get('model_source'))}"
        )

    if st.button("保存通用 LLM 覆盖", key="llm_save_general"):
        updated = dict(secure) if isinstance(secure, dict) else {}
        if _clean_str(llm_base_url_override) or overwrite_empty:
            updated["llm_base_url"] = _clean_str(llm_base_url_override)
        if _clean_str(llm_model_override) or overwrite_empty:
            updated["llm_model"] = _clean_str(llm_model_override)
        if _clean_str(llm_api_key_override) or overwrite_empty:
            updated["llm_api_key"] = _clean_str(llm_api_key_override)
        if _save_json(SECURE_SETTINGS_PATH, updated):
            st.success("通用 LLM 覆盖已保存。")
        else:
            st.error("通用 LLM 覆盖保存失败。")

    st.divider()
    st.subheader("其他 API 密钥管理")
    st.caption("写入 data/secure_settings.json")
    st.caption(f"Composio: {_mask_token(secure.get('composio_api_key')) or '-'}")
    st.caption(f"Browser Use: {_mask_token(secure.get('browser_use_api_key')) or '-'}")
    st.caption(f"记忆服务（Letta）：{_mask_token(secure.get('letta_api_key')) or '-'}")
    st.caption(f"Tushare: {_mask_token(secure.get('tushare_token')) or '-'}")

    composio_key = st.text_input("Composio API 密钥", type="password", key="key_composio")
    browser_key = st.text_input("Browser Use API 密钥", type="password", key="key_browser_use")
    letta_key = st.text_input("Letta 服务密钥", type="password", key="key_letta")
    letta_project = st.text_input(
        "Letta 项目编号",
        value=_clean_str(secure.get("letta_project_id")),
        key="key_letta_project",
    )
    tushare_token = st.text_input("Tushare Token", type="password", key="key_tushare")

    if st.button("保存其他 Key", key="save_other_keys"):
        updated = dict(secure) if isinstance(secure, dict) else {}
        for k, v in (
            ("composio_api_key", _clean_str(composio_key)),
            ("browser_use_api_key", _clean_str(browser_key)),
            ("letta_api_key", _clean_str(letta_key)),
            ("tushare_token", _clean_str(tushare_token)),
        ):
            if v:
                updated[k] = v
            elif overwrite_empty:
                updated[k] = ""
        if _clean_str(letta_project) or overwrite_empty:
            updated["letta_project_id"] = _clean_str(letta_project)
        if _save_json(SECURE_SETTINGS_PATH, updated):
            st.success("其他 Key 已保存。")
        else:
            st.error("其他 Key 保存失败。")

    st.subheader("记忆服务接口地址 / 模型设置")
    st.caption("写入 config/letta.json")
    letta_conf = _load_json(LETTA_CONFIG_PATH, {})
    letta_base = st.text_input("记忆服务接口地址", value=_clean_str(letta_conf.get("base_url")), key="letta_base_url")
    letta_model = st.text_input("记忆服务模型", value=_clean_str(letta_conf.get("model")), key="letta_model")
    if st.button("保存记忆服务配置", key="save_letta_config"):
        updated = dict(letta_conf) if isinstance(letta_conf, dict) else {}
        if _clean_str(letta_base) or overwrite_empty_cfg:
            updated["base_url"] = _clean_str(letta_base)
        if _clean_str(letta_model) or overwrite_empty_cfg:
            updated["model"] = _clean_str(letta_model)
        if _save_json(LETTA_CONFIG_PATH, updated):
            st.success("记忆服务配置已保存。")
        else:
            st.error("记忆服务配置保存失败。")
