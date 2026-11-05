from one_dragon.base.operation.application.application_config import ApplicationConfig
from . import mys_checkin_const


class MysCheckinConfig(ApplicationConfig):

    def __init__(self, instance_idx: int, group_id: str):
        ApplicationConfig.__init__(
            self,
            app_id=mys_checkin_const.APP_ID,
            instance_idx=instance_idx,
            group_id=group_id,
        )

    @property
    def probe_mode(self) -> bool:
        """探测模式: 只运行 checkin.py test 查询登录/签到状态, 不执行真实签到"""
        return self.get('probe_mode', True)

    @probe_mode.setter
    def probe_mode(self, new_value: bool) -> None:
        self.update('probe_mode', new_value)

    @property
    def timeout_seconds(self) -> int:
        """子进程超时秒数(米游币打卡多分区时较慢, 默认 300)"""
        return self.get('timeout_seconds', 300)

    @timeout_seconds.setter
    def timeout_seconds(self, new_value: int) -> None:
        self.update('timeout_seconds', new_value)
