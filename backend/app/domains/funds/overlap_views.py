# -*- coding: utf-8 -*-
"""组合内基金持仓重叠度只读接口（#2604）。

**独立蓝图、单独文件**（`funds/views.py` 已顶到视图厚度基线上限 263 行，加行即被
`scripts/check_view_thickness.py` 拦下；新文件走「新增视图文件」上限 lines ≤ 400）。

端点只做三件事：**取值 → 调 service → 组响应信封**；全部业务口径（报告期解析、
basis 隔离、两个重叠度算法、覆盖率与缺口清单、降级契约）都在
`app/services/holding_overlap.py`，视图里一行判断都不该有。
"""

from apiflask import APIBlueprint
from flask import jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.holding_correlation import portfolio_holding_correlation
from app.services.holding_overlap import portfolio_holding_overlap

overlap_bp = APIBlueprint('fund_overlap', __name__, url_prefix='/api/funds/overlap')


@overlap_bp.get('/')
def get_holding_overlap():
    """组合内基金持仓重叠度（家庭作用域）。

    出参（服务层直出，视图不改字段）：
    - ``pairs``：有重叠的基金对，按 ``weighted_overlap`` 降序；每对带双方各自的
      ``report_period``（报告期**不强制对齐**，各取各自最新）、``holding_basis``、
      ``jaccard``（集合口径）与 ``weighted_overlap``（加权口径，百分点），以及共同
      重仓股明细 ``common_holdings``；另有 ``overlap_level``（``duplicate`` 配置重复 /
      ``watch`` 需留意 / ``low`` 一般 / ``same-series`` 同一基金不同份额）与
      ``overlap_reason``（触发原因的人话解释，``low`` 时为空串）；
    - ``duplicate_count``：判为配置重复的对数（**不含** ``same-series`` 的份额重复）；
    - ``caveats``：口径声明（持仓快照滞后、高换手基金失真、未接入基金级换手率），
      前端应与结论同屏展示——它决定这些百分比能被信到什么程度；
    - ``fund_count`` / ``skipped_basis_mismatch`` / ``skipped_null_ratio``：
      参与计算的基金数、因披露口径不同被跳过的对数、因占比缺失被排除的持仓行数；
    - ``total_market_value_cents`` / ``coverage_pct`` / ``uncovered``：
      组合内基金市值总额、有持仓明细的占比、无持仓明细的持仓清单；
    - ``degraded``：取数失败时为 ``True``（该维度置空，前端显示「暂时取不到」，
      **不得**渲染成「重叠 0%」的真结论）；``source`` 恒为 ``fund_holdings``。

    **前端消费约定（重要）**：``pairs`` 为空有三种成因，含义完全不同，不得一律
    渲染成「重叠 0%」：
    1. ``degraded=True`` —— 取数失败，显示「暂时取不到」；
    2. ``fund_count < 2`` —— 可比基金不足 2 只，**算不出**（不是「不重叠」）；
    3. ``fund_count >= 2`` 且 ``pairs`` 为空 —— 算出来了，结论就是**确实不重叠**。

    无持仓 / 无持仓明细时返回空 ``pairs`` 列表（200），不 500。
    """
    with get_db() as db:
        data = portfolio_holding_overlap(db, get_family_id())
    return jsonify({'data': data, 'message': 'ok'})


@overlap_bp.get('/correlation/')
def get_holding_correlation():
    """组合内基金两两相关性矩阵（#2686 第二交付，家庭作用域）。

    出参（服务层直出，视图不改字段）：

    - ``funds``：**已截断**的矩阵成员（市值降序）。截断规则与重叠度矩阵共用
      ``services/matrix_members.py``：累计市值覆盖 ≥90%、上限 20 只、下限 8 只；
    - ``cells``：成员内两两结果（上三角，``fund_code_a/b`` 无序）：
      ``correlation``（-1~1，``None`` = 算不出来）、``overlap_days``、
      ``status``（``ok`` / ``no_series`` / ``short_overlap`` / ``zero_variance``）、
      ``reason``（人话原因）；
    - ``fund_count``：**截断前**的成员总数——前端据此区分「组合里只有 3 只」与
      「有 96 只但只展开 20 只」，后者必须显示未覆盖只数与市值占比；
    - ``truncated``：被折叠的只数 + 市值占比（``market_value_pct``）；
    - ``matrix_rule``：当前生效的截断规则（前端文案不另写数字）；
    - ``computed_pairs`` / ``total_pairs``：可算出比例（卡面要求「先给可算出比例」）；
    - ``caveats``：口径声明，与结论同屏；
    - ``degraded``：持仓聚合失败时为 ``True``，前端显示「暂时取不到」，
      **不得**渲染成「相关性 0」的真结论。

    三种「没有值」的含义完全不同，前端不得一律画成 0：
    ``no_series``（无净值序列）/ ``short_overlap``（同期交易日不足）/
    ``zero_variance``（净值无波动，Pearson 未定义）。``0`` 的意思是「无关」，
    与「无信息」天差地别。
    """
    with get_db() as db:
        data = portfolio_holding_correlation(db, get_family_id())
    return jsonify({'data': data, 'message': 'ok'})
