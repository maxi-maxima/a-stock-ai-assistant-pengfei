import os
import json
import hashlib
import streamlit as st

SECURE_SETTINGS_PATH = "data/secure_settings.json"
AUTH_PATH = "data/system_auth.json"


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
    st.header("三脑 API Key 工具")
    st.caption("优先级：环境变量 > 安全存储(data/secure_settings.json) > config/llm_config.yaml")

    secure = _load_json(SECURE_SETTINGS_PATH, {})
    env_blue = os.getenv("BLUE_BRAIN_API_KEY", "").strip()
    env_red = os.getenv("RED_BRAIN_API_KEY", "").strip()
    env_green = os.getenv("GREEN_BRAIN_API_KEY", "").strip()

    st.subheader("当前状态")
    st.write("Blue:", "环境变量" if env_blue else ("安全存储" if secure.get("blue_brain_api_key") else "未配置"))
    st.write("Red:", "环境变量" if env_red else ("安全存储" if secure.get("red_brain_api_key") else "未配置"))
    st.write("Green:", "环境变量" if env_green else ("安全存储" if secure.get("green_brain_api_key") else "未配置"))

    st.caption(f"安全存储 Blue: {_mask_token(secure.get('blue_brain_api_key')) or '-'}")
    st.caption(f"安全存储 Red: {_mask_token(secure.get('red_brain_api_key')) or '-'}")
    st.caption(f"安全存储 Green: {_mask_token(secure.get('green_brain_api_key')) or '-'}")

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

    st.subheader("一键写三脑 Key")
    same_key = st.checkbox("三脑使用同一 Key", value=True, key="llm_same_key")
    overwrite_empty = st.checkbox("允许空值覆盖(清空)", value=False, key="llm_overwrite_empty")

    if same_key:
        all_key = st.text_input("统一 API Key", type="password", key="llm_all_key")
        blue_key = all_key
        red_key = all_key
        green_key = all_key
    else:
        blue_key = st.text_input("Blue API Key", type="password", key="llm_blue_key")
        red_key = st.text_input("Red API Key", type="password", key="llm_red_key")
        green_key = st.text_input("Green API Key", type="password", key="llm_green_key")

    if st.button("写入三脑 API Key", key="llm_write_keys"):
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
