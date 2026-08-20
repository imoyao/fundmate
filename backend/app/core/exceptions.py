# app/core/exceptions.py
# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026-05-30
# File : exceptions.py
"""自定义异常与错误码体系（轻量级，不绑定框架）。"""

from enum import Enum
from typing import Dict, Optional


class SBException(Exception):
    """所有业务异常的基类。"""

    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 400,
        detail: Optional[Dict] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class ErrorCode(Enum):
    """业务错误码枚举。

    每个枚举项包含三个属性：
    - code: 业务错误码（整数）
    - message: 默认错误信息
    - http_status: 推荐的 HTTP 状态码
    """

    # 通用错误 1xxx
    INVALID_PARAMS = (1001, '请求参数无效', 400)
    RESOURCE_NOT_FOUND = (1002, '资源不存在', 404)
    DUPLICATE_ENTRY = (1003, '数据已存在', 409)
    OPERATION_FAILED = (1004, '操作失败', 400)
    UNAUTHORIZED = (1005, '未授权，请先登录', 401)
    FORBIDDEN = (1006, '没有权限执行此操作', 403)

    # 业务错误 2xxx（持仓/交易相关）
    INSUFFICIENT_QUANTITY = (2001, '持仓数量不足', 400)
    LOT_SIZE_VIOLATION = (2002, '数量必须为一手的整数倍', 400)
    CONFIRM_DATE_FAILED = (2003, '确认日计算失败', 400)
    POSITION_NOT_FOUND = (2004, '持仓不存在', 404)
    INVALID_OPERATION = (2005, '不支持的操作类型', 400)

    # 导入相关错误 3xxx
    FILE_PARSE_ERROR = (3001, '文件解析失败', 400)
    DUPLICATE_TRANSACTION = (3002, '重复的交易记录', 409)
    UNSUPPORTED_FILE_FORMAT = (3003, '不支持的文件格式', 400)
    USAGE_LIMIT_EXCEEDED = (3004, '当日使用次数已用完', 429)
    RATE_LIMIT_EXCEEDED = (3005, '操作太频繁，请稍后再试', 429)

    # 数据源/同步相关错误 5xxx
    DATA_SOURCE_ERROR = (5001, '外部数据源异常', 503)
    DATA_SOURCE_TIMEOUT = (5002, '数据源请求超时', 504)
    SYNC_JOB_FAILED = (5003, '数据同步任务失败', 500)
    INTERNAL_ERROR = (5004, '服务器内部错误', 500)
    OCR_SERVICE_UNAVAILABLE = (5005, 'OCR 识别服务暂不可用', 503)

    # AI 账本精灵（AgentLoop）相关错误 4xxx
    AGENT_TURN_LIMIT_EXCEEDED = (4001, '已超出分析轮次', 429)

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def msg(self) -> str:
        return self.value[1]

    @property
    def http_status(self) -> int:
        return self.value[2]

    @classmethod
    def get_by_code(cls, code: int):
        """根据错误码获取枚举项。"""
        for item in cls:
            if item.code == code:
                return item
        return None
