# app/core/exceptions.py
# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026-05-30
# File : exceptions.py
"""自定义异常与错误码体系（轻量级，不绑定框架）。"""

from enum import Enum
from typing import Dict, Optional

from loguru import logger


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
    # 权益分隔（#2324）：与通用 FORBIDDEN 分开，前端才能把「Pro 未开通」
    # 渲染成付费墙/权益态，而不是「暂时取不到」。通用 403 仍用 1006。
    PRO_NOT_ENTITLED = (1007, 'Pro 功能未开通', 403)

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


def internal_error_message(exc: Optional[BaseException] = None, context: str = '') -> str:
    """500 响应的**固定文案**，并顺手把完整堆栈落日志（2026-10-29）。

    为什么必须有它：视图里写
    ``except Exception as e: jsonify({'message': f'服务器内部错误: {str(e)}'})``
    会把 ``str(e)`` 原样送到浏览器——实测一次 ``IntegrityError`` 就泄漏了 INSERT
    全文、绑定参数（含 ``family_id`` / ``ledger_id`` / 金额）与 ``sqlalche.me`` 链接。
    更糟的是异常被视图吞掉后，``main.py::handle_unexpected`` 那一层（固定文案 +
    ``logger.opt(exception=True)``）**永远不会执行** ⇒ 既不脱敏也不留痕，事后连
    排查线索都没有。

    本函数把「脱敏」与「留痕」绑成同一个动作：调用方只写一次，就不可能只做一半。
    堆栈走 loguru（``logger.exception`` 同效），对外只有 ``ErrorCode.INTERNAL_ERROR.msg``。
    """
    logger.opt(exception=exc).error('未捕获的系统异常（{}）', context or '未标注')
    return ErrorCode.INTERNAL_ERROR.msg


def internal_error_payload(
    exc: Optional[BaseException] = None,
    context: str = '',
    data: object = None,
    error_code: int = ErrorCode.INTERNAL_ERROR.code,
) -> Dict:
    """完整 5xx 信封 `{data, message, error_code}`：固定文案 + 堆栈留痕（2026-10-30）。

    与 :func:`internal_error_message` 的区别只是「一次给全信封」，视图侧一行即可：

        return jsonify(internal_error_payload(e, 'sankey', {'nodes': [], 'links': []})), 500

    为什么值得单独一个函数：脱敏改造让每处 5xx 从一行涨到三行，`summary` /
    `temperature` 因此顶破 `scripts/check_view_thickness.py` 的存量冻结基线
    （只减不增）。**正确做法不是放宽基线**（那等于承认「视图可以继续变厚」），
    而是把「组信封」这一步也收进 core——它本就是契约实现，不属于视图职责。

    `data` 由调用方传入而**不从 `exc` 推导**：各视图的 `data` 形状
    （`{}` / `{'items': []}` / `{'cycles': [], 'summary': {}}`）是前端契约，
    脱敏不该顺带把它改成 `None`。
    """
    return {'data': data, 'message': internal_error_message(exc, context), 'error_code': error_code}
