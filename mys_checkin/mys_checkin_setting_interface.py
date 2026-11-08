from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, InfoBar, LineEdit, PushButton

from one_dragon.utils.i18_utils import gt
from one_dragon_qt.widgets.column import Column
from one_dragon_qt.widgets.setting_card.check_box_setting_card import (
    CheckBoxSettingCard,
)
from one_dragon_qt.widgets.setting_card.multi_push_setting_card import (
    MultiPushSettingCard,
)
from one_dragon_qt.widgets.setting_card.switch_setting_card import (
    SwitchSettingCard,
)
from one_dragon_qt.widgets.vertical_scroll_interface import (
    VerticalScrollInterface,
)

from . import mys_login_backend

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class SmsSendRunner(QThread):
    """后台发送验证码，网络请求不阻塞界面"""

    result_signal = Signal(bool, str)

    def __init__(self, mobile: str, parent: QWidget | None = None) -> None:
        QThread.__init__(self, parent)
        self._mobile: str = mobile

    def run(self) -> None:
        try:
            ok, msg = mys_login_backend.send_sms(self._mobile)
        except Exception as e:
            ok, msg = False, f'发送失败：{e}'
        self.result_signal.emit(ok, msg)


class SmsVerifyRunner(QThread):
    """后台完成登录（网络请求 + 凭据落盘）"""

    result_signal = Signal(bool, str)

    def __init__(self, mobile: str, code: str, parent: QWidget | None = None) -> None:
        QThread.__init__(self, parent)
        self._mobile: str = mobile
        self._code: str = code

    def run(self) -> None:
        try:
            ok, msg = mys_login_backend.verify_sms(self._mobile, self._code)
        except Exception as e:
            ok, msg = False, f'登录失败：{e}'
        self.result_signal.emit(ok, msg)


class MysCheckinSettingInterface(VerticalScrollInterface):
    """米游社签到配置页：登录入口 + 签到选项。

    登录用手机号 + 短信验证码，与 CLI 入口 mys_login.py 同一内核；
    手机号不进配置、不落日志，登录成功后凭据由内核存入 vendor/config.json。
    """

    def __init__(self, ctx: ZContext, parent=None):
        self.ctx: ZContext = ctx

        VerticalScrollInterface.__init__(
            self,
            object_name='mys_checkin_setting_interface',
            content_widget=None, parent=parent,
            nav_text_cn='米游社签到'
        )

        self._status: dict = {}
        self._pending_mobile: str = ''
        self._sms_runner: SmsSendRunner | None = None
        self._verify_runner: SmsVerifyRunner | None = None
        self._updating_checkboxes: bool = False

    def get_content_widget(self) -> QWidget:
        content = Column()

        # ── 账号登录 ──
        self.login_card = MultiPushSettingCard(
            icon=FluentIcon.PEOPLE,
            title='米游社账号',
            content='未登录',
            btn_list=[],
        )
        content.add_widget(self.login_card)

        self.mobile_input = LineEdit()
        self.mobile_input.setPlaceholderText(gt('手机号（仅本次登录使用，不保存）'))
        self.mobile_input.setMaxLength(13)
        self.mobile_input.setFixedWidth(220)

        self.code_input = LineEdit()
        self.code_input.setPlaceholderText(gt('短信验证码'))
        self.code_input.setMaxLength(6)
        self.code_input.setFixedWidth(120)

        self.send_code_btn = PushButton(text=gt('发送验证码'))
        self.send_code_btn.clicked.connect(self._on_send_code)
        self.login_btn = PushButton(text=gt('登录'))
        self.login_btn.clicked.connect(self._on_verify)
        self.logout_btn = PushButton(text=gt('退出登录'))
        self.logout_btn.clicked.connect(self._on_logout)

        self.login_input_card = MultiPushSettingCard(
            icon=FluentIcon.SEND,
            title='手机号验证码登录',
            content='发送验证码后输入 6 位短信码完成登录',
            btn_list=[self.mobile_input, self.code_input, self.send_code_btn,
                      self.login_btn, self.logout_btn],
        )
        content.add_widget(self.login_input_card)

        # ── 签到选项 ──
        self.bbs_switch = SwitchSettingCard(
            icon=FluentIcon.SHARE,
            title='米游币打卡',
            content='登录具备完整权限时可一并完成米游币打卡',
        )
        self.bbs_switch.value_changed.connect(self._on_bbs_changed)
        content.add_widget(self.bbs_switch)

        self.game_cards: dict[str, CheckBoxSettingCard] = {}
        for game_key, game_name in mys_login_backend.MI_GAMES.items():
            card = CheckBoxSettingCard(
                icon=FluentIcon.GAME,
                title=game_name,
                content='',
            )
            card.check_box.stateChanged.connect(self._on_game_sign_changed)
            self.game_cards[game_key] = card
            content.add_widget(card)

        return content

    def on_interface_shown(self) -> None:
        VerticalScrollInterface.on_interface_shown(self)
        self._refresh_status()

    def on_interface_hidden(self) -> None:
        VerticalScrollInterface.on_interface_hidden(self)
        self._pending_mobile = ''

    # ---------- 状态刷新 ----------

    def _refresh_status(self) -> None:
        self._status = mys_login_backend.get_status()
        if not self._status.get('ok'):
            self.login_card.setContent(f'内核加载失败：{self._status.get("message")}')
            self.logout_btn.setVisible(False)
            return

        if self._status.get('logged_in'):
            uid = self._status.get('uid') or ''
            has_ct = self._status.get('has_cookie_token')
            ct_text = 'cookie_token 正常' if has_ct else 'cookie_token 待续期（会自动重试）'
            self.login_card.setContent(f'已登录 uid={uid}，{ct_text}')
        else:
            self.login_card.setContent('未登录，请在下方用手机号验证码登录')

        self.logout_btn.setVisible(bool(self._status.get('logged_in')))

        self._updating_checkboxes = True
        self.bbs_switch.setValue(bool(self._status.get('bbs_checkin')),
                                 emit_signal=False)
        signed_games = set(self._status.get('game_sign') or [])
        for game_key, card in self.game_cards.items():
            card.check_box.blockSignals(True)
            card.check_box.setChecked(game_key in signed_games)
            card.check_box.blockSignals(False)
        self._updating_checkboxes = False

    # ---------- 登录 ----------

    def _on_send_code(self) -> None:
        mobile = self.mobile_input.text().strip().replace('+86', '')
        mobile = mobile.replace(' ', '').replace('-', '')
        if len(mobile) != 11 or not mobile.isdigit():
            self._show_toast('手机号格式不对，需要 11 位数字', error=True)
            return
        self._pending_mobile = mobile

        self._set_login_running(True, '正在发送验证码…')
        self._sms_runner = SmsSendRunner(mobile, self)
        self._sms_runner.result_signal.connect(self._on_sms_sent)
        self._sms_runner.start()

    def _on_sms_sent(self, ok: bool, msg: str) -> None:
        self._set_login_running(False, msg)
        self._show_toast(msg, error=not ok)
        if ok:
            self.code_input.setFocus()

    def _on_verify(self) -> None:
        code = self.code_input.text().strip()
        if len(self._pending_mobile) != 11:
            self._show_toast('请先发送验证码', error=True)
            return
        if len(code) != 6 or not code.isdigit():
            self._show_toast('请输入 6 位短信验证码', error=True)
            return

        self._set_login_running(True, '正在登录…')
        self._verify_runner = SmsVerifyRunner(self._pending_mobile, code, self)
        self._verify_runner.result_signal.connect(self._on_verify_done)
        self._verify_runner.start()

    def _on_verify_done(self, ok: bool, msg: str) -> None:
        self._set_login_running(False, msg)
        self._show_toast(msg, error=not ok)
        if ok:
            self._pending_mobile = ''
            self.mobile_input.clear()
            self.code_input.clear()
            self._refresh_status()

    def _on_logout(self) -> None:
        ok, msg = mys_login_backend.logout()
        self._show_toast(msg, error=not ok)
        if ok:
            self._refresh_status()

    def _set_login_running(self, running: bool, text: str = '') -> None:
        self.send_code_btn.setEnabled(not running)
        self.login_btn.setEnabled(not running)
        if text:
            self.login_input_card.setContent(text)

    # ---------- 配置 ----------

    def _on_bbs_changed(self, value: bool) -> None:
        ok, msg = mys_login_backend.set_bbs_checkin(value)
        if not ok:
            self._show_toast(f'保存失败：{msg}', error=True)
            self._refresh_status()

    def _on_game_sign_changed(self) -> None:
        if self._updating_checkboxes:
            return
        selected = [key for key, card in self.game_cards.items()
                    if card.check_box.isChecked()]
        if len(selected) == 0:
            self._show_toast('至少保留一个签到游戏', error=True)
            self._refresh_status()
            return
        ok, msg = mys_login_backend.set_game_sign(selected)
        if not ok:
            self._show_toast(f'保存失败：{msg}', error=True)
        self._refresh_status()

    def _show_toast(self, message: str, error: bool = False) -> None:
        if error:
            InfoBar.error(
                title='', content=message,
                orient=Qt.Orientation.Horizontal, isClosable=True,
                duration=5000, parent=self,
            )
        else:
            InfoBar.success(
                title='', content=message,
                orient=Qt.Orientation.Horizontal, isClosable=True,
                duration=3000, parent=self,
            )
