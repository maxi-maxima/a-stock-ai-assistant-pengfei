import os
import json
import hashlib
import streamlit as st
try:
    import yaml
except Exception:
    yaml = None
try:
    from openai import OpenAI
except Exception:
    OpenAI = None
try:
    import tushare as ts
except Exception:
    ts = None

SECURE_SETTINGS_PATH = "data/secure_settings.json"
AUTH_PATH = "data/system_auth.json"
CONFIG_PATH = "config/llm_config.yaml"


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
    if yaml is None:
        return default if default is not None else {}
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _save_yaml(path, data):
    if yaml is None:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def _test_openai_api(api_key, base_url, model):
    if OpenAI is None:
        return False, "OpenAI SDK 未安装"
    if not api_key:
        return False, "API 密钥为空"
    if not model:
        return False, "模型为空"
    try:
        client = OpenAI(api_key=api_key, base_url=base_url or None)
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a health check bot. Reply with 'pong'."},
                {"role": "user", "content": "ping"}
            ],
            temperature=0.0,
            max_tokens=8
        )
        text = res.choices[0].message.content.strip() if res and res.choices else ""
        if not text:
            return False, "无返回内容"
        return True, text
    except Exception as e:
        return False, f"调用失败: {e}"


def _test_tushare_token(token):
    if ts is None:
        return False, "Tushare 未安装"
    if not token:
        return False, "令牌为空"
    try:
        ts.set_token(token)
        pro = ts.pro_api()
        df = pro.trade_cal(exchange="", start_date="20240101", end_date="20240110", fields="cal_date,is_open")
        if df is None or df.empty:
            return False, "返回为空"
        return True, f"返回 {len(df)} 条"
    except Exception as e:
        return False, f"调用失败: {e}"


def _mask_token(token):
    if not token:
        return ""
    token = str(token)
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
    env_pw = os.getenv("SYSTEM_ADMIN_PASSWORD")
    if env_pw:
        return password == env_pw
    record = _get_auth_record()
    salt = record.get("salt")
    stored = record.get("hash")
    if not salt or not stored:
        return False
    return _hash_password(password, salt) == stored


def render():
    st.header("三脑 API 配置工具")
    st.caption("优先级：环境变量 > 安全存储(data/secure_settings.json) > config/llm_config.yaml")

    secure = _load_json(SECURE_SETTINGS_PATH, {})
    env_blue = os.getenv("BLUE_BRAIN_API_KEY", "").strip()
    env_red = os.getenv("RED_BRAIN_API_KEY", "").strip()
    env_green = os.getenv("GREEN_BRAIN_API_KEY", "").strip()

    st.subheader("当前状态")
    st.write("蓝脑:", "环境变量" if env_blue else ("安全存储" if secure.get("blue_brain_api_key") else "未配置"))
    st.write("红脑:", "环境变量" if env_red else ("安全存储" if secure.get("red_brain_api_key") else "未配置"))
    st.write("绿脑:", "环境变量" if env_green else ("安全存储" if secure.get("green_brain_api_key") else "未配置"))

    st.caption(f"安全存储 蓝脑: {_mask_token(secure.get('blue_brain_api_key')) or '-'}")
    st.caption(f"安全存储 红脑: {_mask_token(secure.get('red_brain_api_key')) or '-'}")
    st.caption(f"安全存储 绿脑: {_mask_token(secure.get('green_brain_api_key')) or '-'}")

    st.divider()

    auth_ok = st.session_state.get("llm_auth_ok", False)
    env_pw = os.getenv("SYSTEM_ADMIN_PASSWORD")
    auth_record = _get_auth_record()

    if not env_pw and not auth_record.get("hash"):
        st.info("未设置管理密码，请先设置一次密码。")
        new_pw = st.text_input("设置管理密码", type="password", key="llm_new_pw")
        new_pw2 = st.text_input("确认管理密码", type="password", key="llm_new_pw2")
        if st.button("保存管理密码", key="llm_set_pw"):
            if not new_pw or len(new_pw) < 6:
                st.error("密码至少 6 位")
            elif new_pw != new_pw2:
                st.error("两次密码不一致")
            else:
                if _set_password(new_pw):
                    st.success("管理密码已设置")
                else:
                    st.error("保存失败，请检查写入权限")
        st.stop()

    if not auth_ok:
        pw = st.text_input("输入管理密码解锁", type="password", key="llm_auth_pw")
        if st.button("解锁", key="llm_unlock"):
            if _verify_password(pw):
                st.session_state["llm_auth_ok"] = True
                st.success("已解锁")
            else:
                st.error("密码错误")
        st.stop()

    st.subheader("一键写入三脑密钥")
    same_key = st.checkbox("三脑使用同一密钥", value=True, key="llm_same_key")
    overwrite_empty = st.checkbox("允许空值覆盖(清空)", value=False, key="llm_overwrite_empty")

    if same_key:
        all_key = st.text_input("统一 API 密钥", type="password", key="llm_all_key")
        blue_key = all_key
        red_key = all_key
        green_key = all_key
    else:
        blue_key = st.text_input("蓝脑 API 密钥", type="password", key="llm_blue_key")
        red_key = st.text_input("红脑 API 密钥", type="password", key="llm_red_key")
        green_key = st.text_input("绿脑 API 密钥", type="password", key="llm_green_key")

    if st.button("写入三脑 API 密钥", key="llm_write_keys"):
        updated = dict(secure) if isinstance(secure, dict) else {}
        for k, v in (
            ("blue_brain_api_key", blue_key),
            ("red_brain_api_key", red_key),
            ("green_brain_api_key", green_key),
        ):
            if v:
                updated[k] = v
            elif overwrite_empty:
                updated[k] = ""
        if _save_json(SECURE_SETTINGS_PATH, updated):
            st.success("已写入安全存储。请重启或刷新页面以生效。")
        else:
            st.error("写入失败，请检查文件权限。")

    st.divider()
    st.subheader("API 配置中心")
    st.caption("可在此配置三脑的 API 密钥 / 接口地址 / 模型，并测试连通性。优先级：环境变量 > 安全存储(data/secure_settings.json) > config/llm_config.yaml")

    if yaml is None:
        st.error("缺少 PyYAML，无法加载/保存配置。")
        return

    conf = _load_yaml(CONFIG_PATH, {})
    if not isinstance(conf, dict):
        conf = {}

    blue_conf = conf.get("blue_brain") if isinstance(conf.get("blue_brain"), dict) else {}
    red_conf = conf.get("red_brain") if isinstance(conf.get("red_brain"), dict) else {}
    green_conf = conf.get("green_brain") if isinstance(conf.get("green_brain"), dict) else {}
    llm_conf = conf.get("llm") if isinstance(conf.get("llm"), dict) else {}
    sys_conf = conf.get("system") if isinstance(conf.get("system"), dict) else {}

    env_llm_key = os.getenv("LLM_API_KEY", "").strip()
    env_llm_base = os.getenv("LLM_BASE_URL", "").strip()
    env_llm_model = os.getenv("LLM_MODEL", "").strip()
    env_tushare = os.getenv("TUSHARE_TOKEN", "").strip()

    cfg_overwrite_empty = st.checkbox("允许空值覆盖（清空）", value=False, key="llm_cfg_overwrite_empty")

    st.markdown("**蓝脑（策略）**")
    c1, c2, c3, c4 = st.columns([2.2, 2.2, 2.2, 1])
    with c1:
        blue_key_in = st.text_input(
            "API 密钥",
            type="password",
            value="",
            placeholder=_mask_token(env_blue or secure.get("blue_brain_api_key") or env_llm_key) or "未设置",
            key="llm_cfg_blue_key"
        )
    with c2:
        blue_base_in = st.text_input(
            "接口地址",
            value=str(blue_conf.get("base_url") or ""),
            key="llm_cfg_blue_base"
        )
    with c3:
        blue_model_in = st.text_input(
            "模型",
            value=str(blue_conf.get("model") or ""),
            key="llm_cfg_blue_model"
        )
    with c4:
        if st.button("测试", key="llm_cfg_blue_test"):
            test_key = (
                blue_key_in
                or env_blue
                or env_llm_key
                or secure.get("blue_brain_api_key")
                or secure.get("llm_api_key")
                or blue_conf.get("api_key")
            )
            test_base = blue_base_in or os.getenv("BLUE_BRAIN_BASE_URL") or env_llm_base or blue_conf.get("base_url")
            test_model = blue_model_in or os.getenv("BLUE_BRAIN_MODEL") or env_llm_model or blue_conf.get("model")
            ok, msg = _test_openai_api(test_key, test_base, test_model)
            if ok:
                st.success(f"蓝脑测试成功：{msg}")
            else:
                st.error(f"蓝脑测试失败：{msg}")
    if env_blue or os.getenv("BLUE_BRAIN_BASE_URL") or os.getenv("BLUE_BRAIN_MODEL"):
        st.caption("检测到环境变量 BLUE_BRAIN_*，运行时会优先生效。")

    st.markdown("**红脑（战术）**")
    c1, c2, c3, c4 = st.columns([2.2, 2.2, 2.2, 1])
    with c1:
        red_key_in = st.text_input(
            "API 密钥",
            type="password",
            value="",
            placeholder=_mask_token(env_red or secure.get("red_brain_api_key") or env_llm_key) or "未设置",
            key="llm_cfg_red_key"
        )
    with c2:
        red_base_in = st.text_input(
            "接口地址",
            value=str(red_conf.get("base_url") or ""),
            key="llm_cfg_red_base"
        )
    with c3:
        red_model_in = st.text_input(
            "模型",
            value=str(red_conf.get("model") or ""),
            key="llm_cfg_red_model"
        )
    with c4:
        if st.button("测试", key="llm_cfg_red_test"):
            test_key = (
                red_key_in
                or env_red
                or env_llm_key
                or secure.get("red_brain_api_key")
                or secure.get("llm_api_key")
                or red_conf.get("api_key")
            )
            test_base = red_base_in or os.getenv("RED_BRAIN_BASE_URL") or env_llm_base or red_conf.get("base_url")
            test_model = red_model_in or os.getenv("RED_BRAIN_MODEL") or env_llm_model or red_conf.get("model")
            ok, msg = _test_openai_api(test_key, test_base, test_model)
            if ok:
                st.success(f"红脑测试成功：{msg}")
            else:
                st.error(f"红脑测试失败：{msg}")
    if env_red or os.getenv("RED_BRAIN_BASE_URL") or os.getenv("RED_BRAIN_MODEL"):
        st.caption("检测到环境变量 RED_BRAIN_*，运行时会优先生效。")

    st.markdown("**绿脑（裁决）**")
    c1, c2, c3, c4 = st.columns([2.2, 2.2, 2.2, 1])
    with c1:
        green_key_in = st.text_input(
            "API 密钥",
            type="password",
            value="",
            placeholder=_mask_token(env_green or secure.get("green_brain_api_key") or env_llm_key) or "未设置",
            key="llm_cfg_green_key"
        )
    with c2:
        green_base_in = st.text_input(
            "接口地址",
            value=str(green_conf.get("base_url") or ""),
            key="llm_cfg_green_base"
        )
    with c3:
        green_model_in = st.text_input(
            "模型",
            value=str(green_conf.get("model") or ""),
            key="llm_cfg_green_model"
        )
    with c4:
        if st.button("测试", key="llm_cfg_green_test"):
            test_key = (
                green_key_in
                or env_green
                or env_llm_key
                or secure.get("green_brain_api_key")
                or secure.get("llm_api_key")
                or green_conf.get("api_key")
            )
            test_base = green_base_in or os.getenv("GREEN_BRAIN_BASE_URL") or env_llm_base or green_conf.get("base_url")
            test_model = green_model_in or os.getenv("GREEN_BRAIN_MODEL") or env_llm_model or green_conf.get("model")
            ok, msg = _test_openai_api(test_key, test_base, test_model)
            if ok:
                st.success(f"绿脑测试成功：{msg}")
            else:
                st.error(f"绿脑测试失败：{msg}")
    if env_green or os.getenv("GREEN_BRAIN_BASE_URL") or os.getenv("GREEN_BRAIN_MODEL"):
        st.caption("检测到环境变量 GREEN_BRAIN_*，运行时会优先生效。")

    st.markdown("**通用 LLM（默认）**")
    c1, c2, c3, c4 = st.columns([2.2, 2.2, 2.2, 1])
    with c1:
        llm_key_in = st.text_input(
            "API 密钥",
            type="password",
            value="",
            placeholder=_mask_token(env_llm_key or secure.get("llm_api_key")) or "未设置",
            key="llm_cfg_llm_key"
        )
    with c2:
        llm_base_in = st.text_input(
            "接口地址",
            value=str(llm_conf.get("base_url") or ""),
            key="llm_cfg_llm_base"
        )
    with c3:
        llm_model_in = st.text_input(
            "模型",
            value=str(llm_conf.get("model") or ""),
            key="llm_cfg_llm_model"
        )
    with c4:
        if st.button("测试", key="llm_cfg_llm_test"):
            test_key = llm_key_in or env_llm_key or secure.get("llm_api_key") or llm_conf.get("api_key")
            test_base = llm_base_in or env_llm_base or llm_conf.get("base_url")
            test_model = llm_model_in or env_llm_model or llm_conf.get("model")
            ok, msg = _test_openai_api(test_key, test_base, test_model)
            if ok:
                st.success(f"LLM 测试成功：{msg}")
            else:
                st.error(f"LLM 测试失败：{msg}")

    if env_llm_key or env_llm_base or env_llm_model:
        st.caption("检测到环境变量 LLM_*，在未配置专用脑时会作为默认值。")

    st.markdown("**Tushare（行情数据）**")
    c1, c2 = st.columns([2.2, 1])
    with c1:
        tushare_token_in = st.text_input(
            "令牌",
            type="password",
            value="",
            placeholder=_mask_token(env_tushare or secure.get("tushare_token") or sys_conf.get("tushare_token")) or "未设置",
            key="llm_cfg_tushare_token"
        )
    with c2:
        if st.button("测试", key="llm_cfg_tushare_test"):
            test_token = tushare_token_in or env_tushare or secure.get("tushare_token") or sys_conf.get("tushare_token")
            ok, msg = _test_tushare_token(test_token)
            if ok:
                st.success(f"Tushare 测试成功：{msg}")
            else:
                st.error(f"Tushare 测试失败：{msg}")

    if env_tushare:
        st.caption("检测到环境变量 TUSHARE_TOKEN，运行时会优先生效。")

    if st.button("保存 API 配置", key="llm_cfg_save"):
        updated_secure = dict(secure) if isinstance(secure, dict) else {}
        for k, v in (
            ("blue_brain_api_key", blue_key_in),
            ("red_brain_api_key", red_key_in),
            ("green_brain_api_key", green_key_in),
            ("llm_api_key", llm_key_in),
            ("tushare_token", tushare_token_in),
        ):
            if v:
                updated_secure[k] = v
            elif cfg_overwrite_empty:
                updated_secure[k] = ""

        updated_conf = dict(conf) if isinstance(conf, dict) else {}
        for brain_key, base_val, model_val in (
            ("blue_brain", blue_base_in, blue_model_in),
            ("red_brain", red_base_in, red_model_in),
            ("green_brain", green_base_in, green_model_in),
        ):
            section = updated_conf.get(brain_key)
            if not isinstance(section, dict):
                section = {}
            if base_val or cfg_overwrite_empty:
                section["base_url"] = base_val
            if model_val or cfg_overwrite_empty:
                section["model"] = model_val
            updated_conf[brain_key] = section

        llm_section = updated_conf.get("llm")
        if not isinstance(llm_section, dict):
            llm_section = {}
        if llm_base_in or cfg_overwrite_empty:
            llm_section["base_url"] = llm_base_in
        if llm_model_in or cfg_overwrite_empty:
            llm_section["model"] = llm_model_in
        updated_conf["llm"] = llm_section

        sys_section = updated_conf.get("system")
        if not isinstance(sys_section, dict):
            sys_section = {}
        if tushare_token_in or cfg_overwrite_empty:
            sys_section["tushare_token"] = tushare_token_in
        updated_conf["system"] = sys_section

        ok1 = _save_json(SECURE_SETTINGS_PATH, updated_secure)
        ok2 = _save_yaml(CONFIG_PATH, updated_conf)
        if ok1 and ok2:
            st.success("配置已保存，请刷新或重启后生效。")
        else:
            st.error("保存失败，请检查文件权限或路径。")
