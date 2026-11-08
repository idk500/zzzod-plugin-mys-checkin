"""GUI 设置页的后端：加载 vendored 内核，提供登录与配置读写。

复用 mys_login.py 的加载方式（importlib 直接加载单文件内核），
登录函数与 CLI 共用同一份（checkin.py 的 mi_sms_send / mi_sms_verify），
手机号只在本次调用内存里使用，不写配置、不打日志。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"

MI_GAMES = {
    "genshin": "原神",
    "honkaisr": "崩坏：星穹铁道",
    "zzz": "绝区零",
    "honkai3rd": "崩坏3",
}


def load_core():
    """加载 vendored checkin.py（单文件内核，非包，故用 importlib 直接加载）。"""
    core_file = VENDOR / "checkin.py"
    if not core_file.exists():
        raise RuntimeError(f"找不到签到内核: {core_file}")
    spec = importlib.util.spec_from_file_location("mys_checkin_core", core_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载签到内核: {core_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CONFIG = mod.load_config()
    return mod


def mask(mobile: str) -> str:
    """只保留前 3 位，其余全部隐去。"""
    return mobile[:3] + "*" * (len(mobile) - 3) if len(mobile) >= 8 else "***"


def get_status() -> dict:
    """读取登录态与关键开关，供界面显示。字段缺失时给默认值。"""
    try:
        ck = load_core()
    except Exception as e:
        return {"ok": False, "message": str(e)}
    m = ck.CONFIG.get("mihoyo") or {}
    return {
        "ok": True,
        "config_file": str(ck.CONFIG_FILE),
        "logged_in": bool(m.get("stoken")),
        "uid": m.get("stuid") or "",
        "has_cookie_token": bool(m.get("cookie_token")),
        "bbs_checkin": bool(m.get("bbs_checkin", True)),
        "game_sign": list(m.get("game_sign") or []),
        "message": "",
    }


def send_sms(mobile: str) -> tuple[bool, str]:
    """向手机号发送登录验证码。号码只进本次函数内存。"""
    ck = load_core()
    return ck.mi_sms_send(mobile)


def verify_sms(mobile: str, code: str) -> tuple[bool, str]:
    """用手机号 + 验证码完成登录，成功后凭据由内核落盘 config.json。"""
    ck = load_core()
    return ck.mi_sms_verify(mobile, code)


def logout() -> tuple[bool, str]:
    """清除本机已保存的米游社凭据。"""
    try:
        ck = load_core()
        m = ck.CONFIG["mihoyo"]
        m["stoken"] = ""
        m["stuid"] = ""
        m["mid"] = ""
        m["cookie_token"] = ""
        m["account_id"] = ""
        ck.save_config(ck.CONFIG)
        return True, "已清除本机凭据"
    except Exception as e:
        return False, str(e)


def _update_mihoyo(patch: dict) -> tuple[bool, str]:
    """只改 mihoyo 段的指定键并保存，其余配置一律不动。"""
    try:
        ck = load_core()
        ck.CONFIG["mihoyo"].update(patch)
        ck.save_config(ck.CONFIG)
        return True, "已保存"
    except Exception as e:
        return False, str(e)


def set_bbs_checkin(enabled: bool) -> tuple[bool, str]:
    return _update_mihoyo({"bbs_checkin": bool(enabled)})


def set_game_sign(game_keys: list[str]) -> tuple[bool, str]:
    valid = [k for k in game_keys if k in MI_GAMES]
    return _update_mihoyo({"game_sign": valid})


def read_state() -> dict:
    """读当日防重签记录，供界面展示。"""
    state_file = VENDOR / "state.json"
    try:
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
