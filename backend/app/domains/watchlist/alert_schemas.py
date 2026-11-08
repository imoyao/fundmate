# -*- coding: utf-8 -*-
"""自选提醒的入参 Schema。

边界值只在**服务层**校验一次（`watchlist_alert_rules.validate_threshold`），这里只做
「类型 + 明显非法的数」这一层，避免两处各写一套上下限后漂移。`Literal` 让非法类型
在 422 阶段就被拦住，不进业务逻辑。
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AlertType = Literal['PRICE_UP', 'PRICE_DOWN', 'CHANGE_PCT', 'DRAWDOWN']
MagnitudeType = Literal['CHANGE_PCT', 'DRAWDOWN']


class AlertSettingsItem(BaseModel):
    """家庭默认口径的一项（按类型）。

    到价提醒不在此列：到价线逐标的设，「家庭默认到价」没有语义。
    """

    alert_type: MagnitudeType
    is_enabled: bool = Field(False, description='是否默认对全部自选生效')
    threshold_value: float = Field(..., gt=0, description='默认阈值（百分比正数，5 表示 5%）')
    window_days: Optional[int] = Field(None, ge=5, le=250, description='回看窗口天数（仅回撤类）')


class AlertSettingsUpdate(BaseModel):
    items: List[AlertSettingsItem] = Field(..., min_length=1, description='要更新的类型（按 alert_type 覆盖）')


class WatchlistAlertCreate(BaseModel):
    alert_type: AlertType
    threshold_value: float = Field(..., gt=0, description='到价：价格（元）；跌幅/回撤：百分比正数')
    is_active: bool = Field(True, description='是否立即启用')


class WatchlistAlertUpdate(BaseModel):
    threshold_value: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = None
