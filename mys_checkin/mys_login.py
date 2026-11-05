# -*- coding: utf-8 -*-
"""米游社登录入口（仅手机号 + 短信验证码）。

为什么只保留手机号登录：
  1. 2026-09 起米哈游限制了 App 扫码换来的 stoken 权限，米游币打卡会直接
     报无权限；只有短信验证码登录能拿到完整权限；
  2. 扫码需要在另一块屏幕上盯着二维码，无头 / 远程 / 计划任务场景下体验很差。

隐私约定：
  手机号只在本次进程内存里使用 —— 不进命令行参数（避免 shell 历史与进程列表
  泄露）、不写入 config.json、不打印明文（终端回显为 <已隐藏>）。

用法::

    python mys_checkin/mys_login.py           # 交互登录
    python mys_checkin/mys_login.py status    # 查看登录与权限状态
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"


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
    """省略号形式的显示。"""
    return mobile[:3] + "****" + mobile[-4:] if len(mobile) >= 8 else "***"


def do_login() -> int:
    ck = load_core()
    m = ck.CONFIG["mihoyo"]
    if m.get("stoken"):
        print(f"当前已登录 uid={m.get('stuid')}，继续操作会覆盖原凭据。")

    mobile = input("米哈游账号手机号（仅本次使用，不保存）：").strip()
    mobile = mobile.replace("+86", "").replace(" ", "").replace("-", "")
    if len(mobile) != 11 or not mobile.isdigit():
        print("手机号格式不对，需要 11 位数字。")
        return 2

    print(f"正在向 {mask(mobile)} 发送验证码 ...")
    ok, msg = ck.mi_sms_send(mobile)
    print(("  " if ok else "! ") + msg)
    if not ok:
        print("  仍然可以继续：去 https://user.mihoyo.com/#/login 用同一手机号获取验证码，")
        print("  注意不要点登录，把收到的 6 位码输到下面即可。")

    code = input("短信验证码（6 位）：").strip()
    if not code:
        print("未输入验证码，已取消。")
        return 3

    ok, msg = ck.mi_sms_verify(mobile, code)
    print(("登录成功：" if ok else "登录失败：") + msg)
    if not ok:
        return 4

    bbs = bool(ck.CONFIG["mihoyo"].get("bbs_checkin"))
    if not bbs:
        print("  提示：米游币打卡开关当前是关闭的；短信登录具备完整权限，")
        print("        想连米游币一起签，把 config.json 的 mihoyo.bbs_checkin 改为 true。")
    print("\n下一步：运行一条龙的「米游社签到」应用即可自动签到；")
    print(f"        核对状态：python {Path(__file__).as_posix()} status")
    return 0


def do_status() -> int:
    ck = load_core()
    m = ck.CONFIG["mihoyo"]
    cfg_file = Path(str(ck.CONFIG_FILE))
    print(f"配置文件：{cfg_file}")
    print(f"           {'存在' if cfg_file.exists() else '不存在'}")

    if not m.get("stoken"):
        print("登录状态：未登录")
        print("          先执行 python mys_checkin/mys_login.py 用手机号登录")
        return 1

    print(f"登录状态：已登录 uid={m.get('stuid')}")
    print(f"cookie_token：{'有（可做游戏签到）' if m.get('cookie_token') else '无（建议重新登录）'}")
    print(f"米游币打卡：{'开启' if m.get('bbs_checkin') else '关闭'}")
    if m.get("bbs_checkin") and not m.get("cookie_token"):
        print("  ! 开关开着但缺 cookie_token，米游币打卡会失败")
    kuro = ck.CONFIG.get("kuro") or {}
    weibo = ck.CONFIG.get("weibo") or {}
    print(f"库街区：{'开启' if kuro.get('enabled') else '关闭'}    微博超话：{'开启' if weibo.get('enabled') else '关闭'}")

    state_file = Path(str(ck.STATE_FILE))
    if state_file.exists():
        print(f"当日记录：{state_file}（已完成的模块当日会自动跳过）")
    else:
        print("当日记录：无（下次运行会正常签到）")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cmd = (sys.argv[1] if len(sys.argv) > 1 else "login").strip().lower()
    if cmd in ("login", "sms"):
        return do_login()
    if cmd == "status":
        return do_status()
    print(__doc__)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n已取消。")
        sys.exit(130)
