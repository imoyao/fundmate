# -*- coding: utf-8 -*-
"""跨组合对比只读接口（#调仓解读付费功能 · L3）。

**独立蓝图、单独文件**：`funds/views.py` 已顶到视图厚度基线上限（263 行），加行即被
`scripts/check_view_thickness.py` 拦下；本文件走「新增视图文件」上限 lines ≤ 400。

端点只做「取值 → 调 service → 组响应信封」，全部业务口径（货基/债基剔除、基金代码级
三集合、降级契约）都在 `app/services/advisor_comparison.py`。
"""

from apiflask import APIBlueprint
from flask import jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.advisor_comparison import build_advisor_comparison

advisor_comparison_bp = APIBlueprint('advisor_comparison', __name__, url_prefix='/api/funds/advisors')


@advisor_comparison_bp.get('/<string:code>/compare/')
def get_advisor_comparison(code: str):
    """我的账户集 vs 指定投顾组合的基金代码级重合对比（家庭作用域）。

    出参（服务层直出，视图不改字段）：
    - ``advisor``：投顾组合侧（code/name/platform/product_type/as_of_date/holdings
      + max_drawdown/sharpe_ratio/volatility/收益指标 + degraded）；
    - ``mine``：我的账户集侧（holdings + total_market_value_cents + degraded）；
    - ``overlap``：基金代码级三集合 common/advisor_only/mine_only；
    - ``caveats``：口径声明（货基/债基已剔除、混合型未细分、快照滞后、非投资建议）。

    组合不存在 → 404/1002（与 funds/views.py 的 advisor 端点同码）。
    """
    with get_db() as db:
        try:
            data = build_advisor_comparison(db, code, get_family_id())
        except ValueError as e:
            return jsonify({'data': None, 'message': str(e), 'error_code': 1002}), 404
        return jsonify({'data': data, 'message': 'ok'})
