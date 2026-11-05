from __future__ import annotations

from typing import TYPE_CHECKING

from one_dragon.base.operation.application.application_config import ApplicationConfig
from one_dragon.base.operation.application.application_factory import ApplicationFactory
from one_dragon.base.operation.application_base import Application
from . import mys_checkin_const
from .mys_checkin_app import MysCheckinApp
from .mys_checkin_config import MysCheckinConfig

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class MysCheckinAppFactory(ApplicationFactory):

    def __init__(self, ctx: ZContext):
        ApplicationFactory.__init__(self, mys_checkin_const)
        self.ctx: ZContext = ctx

    def create_application(self, instance_idx: int, group_id: str) -> Application:
        return MysCheckinApp(self.ctx)

    def create_config(
        self, instance_idx: int, group_id: str
    ) -> ApplicationConfig:
        return MysCheckinConfig(
            instance_idx=instance_idx,
            group_id=group_id,
        )
