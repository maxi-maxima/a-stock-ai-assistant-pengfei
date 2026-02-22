import base64
import hashlib
import hmac
import json
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone

_ENV_APP_HOME = os.getenv("APP_HOME")
ROOT_DIR = os.path.abspath(_ENV_APP_HOME) if _ENV_APP_HOME else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_PATH = os.path.join(ROOT_DIR, "config", "license.json")
STATE_PATH = os.path.join(ROOT_DIR, "data", "license_state.json")
DEFAULT_SECRET = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"  # change this before distribution
ROLLBACK_GRACE_SECONDS = 6 * 3600


def _utc_now():
    return datetime.now(timezone.utc)


def _isoformat(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _get_secret():
    return os.getenv("SYSTEM_LICENSE_SECRET") or DEFAULT_SECRET


def _get_volume_serial():
    if os.name != "nt":
        return ""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        volume_serial = ctypes.c_ulong()
        max_component_len = ctypes.c_ulong()
        file_system_flags = ctypes.c_ulong()
        root_path = os.getenv("SystemDrive", "C:") + "\\"
        res = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root_path),
            None,
            0,
            ctypes.byref(volume_serial),
            ctypes.byref(max_component_len),
            ctypes.byref(file_system_flags),
            None,
            0,
        )
        if res:
            return f"{volume_serial.value:08x}"
    except Exception:
        return ""
    return ""


def get_machine_id():
    parts = []
    try:
        parts.append(platform.system())
        parts.append(platform.release())
        parts.append(platform.node())
    except Exception:
        pass
    try:
        mac = uuid.getnode()
        parts.append(hex(mac))
    except Exception:
        pass
    vol = _get_volume_serial()
    if vol:
        parts.append(vol)
    raw = "|".join([p for p in parts if p])
    if not raw:
        raw = str(uuid.uuid4())
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16]


def build_payload(user, days, machine_id=None, issued_at=None):
    if machine_id is None:
        machine_id = get_machine_id()
    if issued_at is None:
        issued_at = _utc_now()
    expires_at = issued_at + timedelta(days=int(days))
    return {
        "v": 1,
        "license_id": uuid.uuid4().hex,
        "user": str(user or ""),
        "machine_id": machine_id,
        "plan_days": int(days),
        "issued_at": _isoformat(issued_at),
        "expires_at": _isoformat(expires_at),
    }


def _payload_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_payload(payload, secret=None):
    secret = _get_secret() if secret is None else secret
    msg = _payload_bytes(payload)
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def encode_license(payload, signature):
    blob = {"payload": payload, "sig": signature}
    raw = json.dumps(blob, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def decode_license(code):
    if not code:
        raise ValueError("empty code")
    code = str(code).strip()
    pad = "=" * (-len(code) % 4)
    raw = base64.urlsafe_b64decode(code + pad)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or "payload" not in data or "sig" not in data:
        raise ValueError("invalid license format")
    return data["payload"], data["sig"]


def verify_payload(payload, signature, expected_machine_id=None):
    if not isinstance(payload, dict):
        return False, "invalid payload"
    calc = sign_payload(payload)
    if not hmac.compare_digest(str(signature), calc):
        return False, "invalid signature"
    if expected_machine_id:
        if payload.get("machine_id") != expected_machine_id:
            return False, "machine id mismatch"
    expires_at = _parse_iso(payload.get("expires_at"))
    if expires_at is None:
        return False, "missing expires_at"
    if _utc_now() > expires_at:
        return False, f"license expired at {payload.get('expires_at')}"
    return True, "ok"


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def activate_from_code(code, expected_machine_id=None, license_path=LICENSE_PATH):
    try:
        payload, sig = decode_license(code)
    except Exception as exc:
        return False, f"decode failed: {exc}"
    ok, reason = verify_payload(payload, sig, expected_machine_id=expected_machine_id)
    if not ok:
        return False, reason
    _save_json(license_path, {"payload": payload, "sig": sig})
    return True, "activated"


def _check_clock_rollback(now, state_path=STATE_PATH):
    state = _load_json(state_path, {})
    last_ok = _parse_iso(state.get("last_ok_utc"))
    if last_ok and now < last_ok - timedelta(seconds=ROLLBACK_GRACE_SECONDS):
        return False, "system clock rollback detected"
    return True, "ok"


def _update_last_ok(now, state_path=STATE_PATH):
    state = _load_json(state_path, {})
    state["last_ok_utc"] = _isoformat(now)
    _save_json(state_path, state)


def check_license(license_path=LICENSE_PATH, state_path=STATE_PATH, machine_id=None):
    if machine_id is None:
        machine_id = get_machine_id()
    if not os.path.exists(license_path):
        return False, "license not found"
    lic = _load_json(license_path, {})
    payload = lic.get("payload") if isinstance(lic, dict) else None
    sig = lic.get("sig") if isinstance(lic, dict) else None
    ok, reason = verify_payload(payload, sig, expected_machine_id=machine_id)
    if not ok:
        return False, reason
    now = _utc_now()
    ok, reason = _check_clock_rollback(now, state_path=state_path)
    if not ok:
        return False, reason
    _update_last_ok(now, state_path=state_path)
    return True, "ok"


def guard_streamlit():
    ok, reason = check_license()
    if ok:
        return True
    try:
        import streamlit as st
    except Exception:
        raise RuntimeError(reason)
    machine_id = get_machine_id()
    st.title("License Required")
    st.error(reason)
    st.caption(f"Machine ID: {machine_id}")
    code = st.text_area("Activation Code", height=120)
    if st.button("Activate"):
        ok, msg = activate_from_code(code, expected_machine_id=machine_id)
        if ok:
            st.success("Activated. Please refresh.")
            st.rerun()
        else:
            st.error(msg)
    st.stop()
