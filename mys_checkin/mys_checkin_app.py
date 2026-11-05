from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import ClassVar

from one_dragon.base.operation.application import application_const
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log
from zzz_od.application.zzz_application import ZApplication
from zzz_od.context.zzz_context import ZContext

from . import mys_checkin_const
from .mys_checkin_config import MysCheckinConfig
from .zzz_compat import factory_record_kwargs


class MysCheckinApp(ZApplication):
    """米游社签到：一条龙运行时顺便签到，不操作游戏。

    内核为 vendored DailyCheckIn/checkin.py（MIT, 单文件, 仅依赖 requests）：
    - run  = 执行今日签到（游戏签到 + 米游币打卡，state.json 当日防重签）
    - test = 只查询登录/签到状态（对应本应用 probe 模式）
    - 凭据在 vendor/config.json（用户首次登录生成，永不入库）

    本应用全程不发游戏请求、不截图不识别，只托管子进程并汇总结果。
    """

    STATUS_DONE: ClassVar[str] = '签到完成'
    STATUS_SKIP: ClassVar[str] = '今日已完成'

    def __init__(self, ctx: ZContext):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=mys_checkin_const.APP_ID,
            op_name=mys_checkin_const.APP_NAME,
            node_max_retry_times=3,
            **factory_record_kwargs(),
        )
        self.config: MysCheckinConfig = self.ctx.run_context.get_config(
            app_id=mys_checkin_const.APP_ID,
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )

        self.vendor_dir: str = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'vendor')
        self.checkin_py: str = os.path.join(self.vendor_dir, 'checkin.py')
        self.config_json: str = os.path.join(self.vendor_dir, 'config.json')
        self.state_json: str = os.path.join(self.vendor_dir, 'state.json')

        self.skip_today: bool = False
        self.proc_output: list[str] = []
        self.proc_returncode: int | None = None

    # ---------- 辅助 ----------

    def _load_json(self, path: str) -> dict:
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _today_all_done(self) -> bool:
        """state.json 显示今日全部启用模块已完成（checkin.py 自己也会跳，这里省一次进程）"""
        state = self._load_json(self.state_json)
        if state.get('date') != f'{datetime.now():%Y-%m-%d}':
            return False
        cfg = self._load_json(self.config_json)
        mi = cfg.get('mihoyo', {})
        if mi.get('enabled', True):
            if state.get('mihoyo_game') is not True:
                return False
            if mi.get('bbs_checkin', True) and state.get('mihoyo_bbs') is not True:
                return False
        return True

    def _run_checkin(self, command: str) -> OperationRoundResult:
        """托管子进程执行 checkin.py，输出实时落日志"""
        cmd = [sys.executable, self.checkin_py, command]
        log.info('[米游社签到] 执行: %s (超时 %ds)', ' '.join(cmd[1:]),
                 self.config.timeout_seconds)
        self.proc_output = []
        # 子进程默认按系统代码页(GBK)输出中文，主进程按 UTF-8 解码会变成乱码。
        # 强制子进程用 UTF-8，签到明细才能在一条龙日志里正常阅读。
        child_env = dict(os.environ)
        child_env['PYTHONIOENCODING'] = 'utf-8'
        child_env['PYTHONUTF8'] = '1'
        try:
            proc = subprocess.run(
                cmd, cwd=self.vendor_dir,
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=self.config.timeout_seconds,
                env=child_env,
            )
            self.proc_returncode = proc.returncode
            for line in (proc.stdout or '').splitlines():
                self.proc_output.append(line)
                log.info('[checkin] %s', line)
            for line in (proc.stderr or '').splitlines():
                self.proc_output.append(line)
                log.warning('[checkin] %s', line)
        except subprocess.TimeoutExpired:
            return self.round_fail(f'子进程超时({self.config.timeout_seconds}s)，'
                                   f'可在配置调大 timeout_seconds')
        except Exception as e:
            return self.round_fail(f'子进程启动失败: {e}')

        if self.proc_returncode != 0:
            tail = ' | '.join(self.proc_output[-3:])
            return self.round_fail(f'checkin.py 退出码 {self.proc_returncode}: {tail}')
        return self.round_success()

    def _write_result(self, status: str) -> None:
        out_dir = os.path.join(
            os_utils.get_path_under_work_dir('.debug'), 'mys_checkin')
        os.makedirs(out_dir, exist_ok=True)
        report = {
            'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': status,
            'probe_mode': self.config.probe_mode,
            'returncode': self.proc_returncode,
            'state': self._load_json(self.state_json),
        }
        try:
            with open(os.path.join(out_dir, 'last_run.json'), 'w',
                      encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
        except Exception as e:
            log.warning(f'写结果失败: {e}')

    # ---------- 节点 ----------

    @operation_node(name='凭据预检', is_start_node=True)
    def precheck(self) -> OperationRoundResult:
        if not os.path.exists(self.checkin_py):
            return self.round_fail('vendor/checkin.py 缺失，插件安装不完整')
        cfg = self._load_json(self.config_json)
        mi = cfg.get('mihoyo', {})
        if not (mi.get('stoken') or mi.get('cookie_token')):
            return self.round_fail(
                '尚未登录米游社：在本机运行 vendor/checkin.py 的 login 子命令'
                '(或上游 GUI)登录一次，生成的 config.json 会落在 vendor 目录')
        if self._today_all_done():
            self.skip_today = True
            log.info('[米游社签到] state.json 显示今日已完成，跳过')
            return self.round_success(self.STATUS_SKIP)
        return self.round_success()

    @node_from(from_name='凭据预检')
    @operation_node(name='执行签到')
    def do_checkin(self) -> OperationRoundResult:
        if self.skip_today:
            return self.round_success(self.STATUS_SKIP)
        return self._run_checkin('test' if self.config.probe_mode else 'run')

    @node_from(from_name='执行签到')
    @operation_node(name='汇总结果')
    def summarize(self) -> OperationRoundResult:
        if self.skip_today:
            self._write_result(self.STATUS_SKIP)
            return self.round_success(self.STATUS_SKIP)
        if self.proc_returncode != 0:
            self._write_result('FAIL')
            return self.round_fail('签到失败，见上方 [checkin] 日志')
        self._write_result(self.STATUS_DONE)
        log.info('[米游社签到] 完成 (probe=%s)', self.config.probe_mode)
        return self.round_success(self.STATUS_DONE)
