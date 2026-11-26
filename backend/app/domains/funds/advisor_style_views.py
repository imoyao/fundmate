# -*- coding: utf-8 -*-
"""投顾组合方向对照只读接口（详情页 §05 账户对照的数据面）。

**独立蓝图、单独文件**：`funds/views.py` 已顶到视图厚度基线上限，加端点即被
`scripts/check_view_thickness.py` 拦下；本文件与 `advisor_comparison_views.py`
同一形态（新增视图文件上限 lines ≤ 400）。

端点只做「取值 → 调 service → 组响应信封」，全部口径在
`app/services/advisor_style_compare.py`。
"""

from apiflask import APIBlueprint
from flask import jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.advisor_style_compare import build_advisor_style_compare

advisor_style_bp = APIBlueprint('advisor_style', __name__, url_prefix='/api/funds/advisors')


@advisor_style_bp.get('/<string:code>/style-compare/')
def get_advisor_style_compare(code: str):
    """指定投顾组合 vs 我的账户：五方向（大盘/中盘/小盘/港股/固收）占比对照。

    出参（服务层直出，视图不改字段）：
    - ``advisor``：组合侧（as_of_date / has_snapshot / directions / fund_count /
      covered_weight_pct / coverage_pct / missing / degraded）；
    - ``mine``：我侧（directions / total_market_value_cents / coverage_pct /
      fund_count / period_to / degraded）；
    - ``caveats``：口径声明（含非投资建议）。

    组合不存在 → 404/1002（与其余 advisor 端点同码）。
    """
    with get_db() as db:
        try:
            data = build_advisor_style_compare(db, code, get_family_id())
        except ValueError as e:
            return jsonify({'data': None, 'message': str(e), 'error_code': 1002}), 404
        return jsonify({'data': data, 'message': 'ok'})
