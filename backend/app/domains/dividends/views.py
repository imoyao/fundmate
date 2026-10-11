# -*- coding: utf-8 -*-
"""分红与股息 API（#872）。

端点（一律尾斜杠，见 `docs/spec/conventions.md` §2.2）：

- ``GET    /api/dividends/summary/`` 分红与股息总览（累计分红 / 股息率 / 再投收益 / 目标达成度）
- ``PUT    /api/dividends/target/``  设置或更新家庭股息目标
- ``DELETE /api/dividends/target/``  清除股息目标

视图只做参数校验与编排，所有统计口径在 `services/dividend_service.py`（不在此重算）。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.dividends.schemas import DividendTargetUpdate
from app.services.dividend_service import (
    MONTHS_MAX,
    MONTHS_MIN,
    YEARS_MAX,
    YEARS_MIN,
    build_dividend_summary,
    clear_target,
    read_target,
    upsert_target,
)

dividends_bp = APIBlueprint('dividends', __name__, url_prefix='/api/dividends')


def _bounded_int_arg(name: str, default: int, low: int, high: int) -> int:
    """查询参数取整数并做闭区间校验，越界/非法一律 422（统一错误信封）。

    **刻意不用 `request.args.get(name, default, type=int)`**：Werkzeug 在类型转换
    抛 ValueError 时会**静默回落默认值**（`?months=abc` 变成 12），把非法入参伪装成
    合法请求——统计窗口被悄悄改写，用户看到的口径与请求的不一致。
    这里显式解析，任何非法值都抛 422。

    也不走 `parse_query`：只有两个可选整数，Pydantic 模型的样板成本高于收益，
    而 `abort(422)` 经 `main._HTTP_STATUS_TO_ERROR_CODE` 同样收敛为 error_code=1001。
    """
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        abort(422, f'{name} 必须是 {low}~{high} 之间的整数')
    if not (low <= value <= high):
        abort(422, f'{name} 必须是 {low}~{high} 之间的整数')
    return value


@dividends_bp.get('/summary/')
def get_dividend_summary():
    """分红与股息总览。

    query:
        months: 股息率与「近期分红」的统计窗口（自然月，1~60，默认 12 = TTM）。
        years:  `by_year` 逐年汇总回溯的年数（1~20，默认 5）。
    """
    months = _bounded_int_arg('months', 12, MONTHS_MIN, MONTHS_MAX)
    years = _bounded_int_arg('years', 5, YEARS_MIN, YEARS_MAX)
    with get_db() as db:
        data = build_dividend_summary(db, get_family_id(), months=months, years=years)
        return jsonify({'data': data, 'message': 'ok'})


@dividends_bp.put('/target/')
def put_dividend_target():
    """设置 / 更新家庭股息目标。

    目标本身不含达成度——达成度依赖实际股息率，由 `GET /summary/` 的 `target` 字段给出；
    本端点只回写配置，避免为了一次写操作把整套统计再算一遍。
    """
    payload: DividendTargetUpdate = parse_body(DividendTargetUpdate)
    with get_db() as db:
        upsert_target(
            db,
            get_family_id(),
            target_yield_pct=payload.target_yield_pct,
            notes=payload.notes,
        )
        return jsonify({'data': read_target(db, get_family_id()), 'message': 'ok'})


@dividends_bp.delete('/target/')
def delete_dividend_target():
    """清除股息目标。

    「未设置目标」是一种合法状态而非资源缺失，故幂等返回 200 + ``configured=False``，
    不抛 404——否则前端在「本来就没设目标」时点清除会拿到一个业务错误。
    """
    with get_db() as db:
        clear_target(db, get_family_id())
        return jsonify({'data': read_target(db, get_family_id()), 'message': 'ok'})
