from one_dragon_qt.services.app_setting.app_setting_provider import (
    AppSettingProvider,
    SettingType,
)

from . import mys_checkin_const


class MysCheckinAppSetting(AppSettingProvider):
    app_id = mys_checkin_const.APP_ID
    setting_type = SettingType.INTERFACE

    @staticmethod
    def get_setting_cls() -> type:
        from .mys_checkin_setting_interface import MysCheckinSettingInterface

        return MysCheckinSettingInterface
