# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/7 21:52
# File : views.py
# backend/app/api/views.py

"""首页仪表盘聚合数据 API."""

from datetime import date

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.exceptions import internal_error_payload
from app.core.time_utils import today_shanghai
from app.core.validation import parse_query
from app.domains.summary.schemas import MemberSliceQuery
from app.services.analytics.benchmark_excess import build_scope_excess
from app.services.analytics.cleared_cycles import build_cleared_cycles
from app.services.bias.constants import BENCHMARK_INDICES
from app.services.cash_flow_service import build_cash_flow
from app.services.penetration import SCHEME_LABELS, build_penetration
from app.services.pnl_calendar import GRANULARITY_DAY, build_pnl_series, compute_range_attribution
from app.services.position_structure import build_position_structure
from app.services.summary_service import (
    get_account_groups,
    get_distributions,
    get_position_groups,
    get_sankey_data,
    get_snapshots,
    get_summary_data,
    list_fund_valuation_rows,
    orphan_cash_like_payload,
    scan_cross_ledger_duplicates,
    write_asset_snapshot,
)

bp = APIBlueprint('summary', __name__, url_prefix='/api')


@bp.get('/summary/')
def summary():
    """返回首页仪表盘聚合数据"""
    # 参数解析放在 try 之外：try 里的 `except Exception` 会把 abort(422) 吞成 500
    member_id = parse_query(MemberSliceQuery).member_id
    try:
        with get_db() as db:
            family_id = get_family_id()
            data = get_summary_data(db, family_id, member_id)
            account_groups = get_account_groups(db, family_id, member_id)
            data['account_groups'] = account_groups
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(internal_error_payload(e, 'summary', {})), 500


@bp.get('/summary/cash-like/')
def cash_like():
    """#2315 家庭级「类现金」逐产品明细（持仓页分组展示）。

    孤儿货基/逆回购（`position_id IS NULL`）不建持仓、不在持仓明细里，但已计入总资产。
    ⚠️ 返回值不得再被任何汇总加总一次（`summary_service` 已并入 total_assets）。
    """
    try:
        with get_db() as db:
            data = orphan_cash_like_payload(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(internal_error_payload(e, 'cash_like', {'items': []})), 500


@bp.get('/summary/sankey/')
def sankey():
    """返回桑基图数据"""
    member_id = parse_query(MemberSliceQuery).member_id
    try:
        with get_db() as db:
            data = get_sankey_data(db, get_family_id(), member_id)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(internal_error_payload(e, 'sankey', {'nodes': [], 'links': []})), 500


@bp.get('/summary/distributions/')
def distributions():
    """返回家庭级多维市值分布（Overview/AssetPanorama 分布图表消费）"""
    member_id = parse_query(MemberSliceQuery).member_id
    try:
        with get_db() as db:
            data = get_distributions(db, get_family_id(), member_id)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(internal_error_payload(e, 'distributions', {})), 500


@bp.get('/summary/position-structure/')
def position_structure():
    """#2617 持仓结构（资产类别占比 / 股基分列 Top N / 集中度）。

    查询参数：`ledger_id` / `portfolio_id`（互斥，同时传 400；均不传=家庭级）、
    `top_n`（每组榜单条数，默认 5，夹取 1–50）。股票与基金**分开排名**
    （份额与价格不可比）；同一标的跨账户先合并再排序。口径见
    `services/position_structure.py`。
    """
    raw_top_n = request.args.get('top_n')
    try:
        top_n = int(raw_top_n) if raw_top_n not in (None, '') else 5
    except (TypeError, ValueError):
        return jsonify({'data': {}, 'message': f'top_n 必须为整数: {raw_top_n!r}', 'error_code': 1001}), 400

    try:
        with get_db() as db:
            data = build_position_structure(
                db,
                get_family_id(),
                ledger_id=request.args.get('ledger_id', type=int),
                portfolio_id=request.args.get('portfolio_id', type=int),
                top_n=top_n,
            )
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        # scope 参数冲突 / 组合不存在（services 约定），与穿透 / 归因端点同款 400
        return jsonify({'data': {}, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'position_structure', {})), 500


@bp.get('/summary/penetration/')
def penetration():
    """返回基金持仓穿透（行业 / 个股真实暴露，#870 Step 2；#2595 三级口径）。

    查询参数：
    - `scheme`：主聚合口径，`csrc`（默认，证监会门类）/ `gics`（GICS 板块）。
      两套体系**不可相加**，非主口径的结果在 `other_schemes` 单列返回。
    - `top_n`：个股分布截断条数，默认 20；`<=0` 表示不截断（超出部分合并为「其他」）。
    - `ledger_id` / `portfolio_id`：可选，账户级 / 组合级口径（#2595，互斥，
      同时传 400；均不传=家庭级）。组合级语义同归因（#2135）：显式归属 +
      成员账本继承，解析唯一出口 `services/scope.py`。

    覆盖率有硬上限（本机实测约 53%）：直持股票无「个股→行业」映射、场内 ETF 无
    底层持仓数据、货基债基本身无股票敞口。`unpenetrated` 逐条带 `reason`，区分
    「真缺口」与「本质无敞口」，前端不得把两者混为一谈。注意：按账户 / 组合
    拆分后，小作用域的覆盖率波动会更明显（持仓基数变小）。
    """
    scheme = (request.args.get('scheme') or 'csrc').strip().lower()
    if scheme not in SCHEME_LABELS:
        return jsonify(
            {'data': {}, 'message': f'scheme 仅支持 {"/".join(sorted(SCHEME_LABELS))}', 'error_code': 1001}
        ), 400

    raw_top_n = request.args.get('top_n')
    try:
        top_n = int(raw_top_n) if raw_top_n not in (None, '') else 20
    except (TypeError, ValueError):
        return jsonify({'data': {}, 'message': f'top_n 必须为整数: {raw_top_n!r}', 'error_code': 1001}), 400

    ledger_id = request.args.get('ledger_id', type=int)
    portfolio_id = request.args.get('portfolio_id', type=int)

    try:
        with get_db() as db:
            data = build_penetration(
                db, get_family_id(), scheme=scheme, top_n=top_n, ledger_id=ledger_id, portfolio_id=portfolio_id
            )
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        # scope 参数冲突 / 组合不存在（services/scope.py 约定），与归因端点同款 400
        return jsonify({'data': {}, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        # 标准错误信封 {data, message, error_code}（AGENTS.md 接口契约）
        return jsonify(internal_error_payload(e, 'penetration', {})), 500


@bp.get('/summary/groups/')
def position_groups():
    """返回持仓/资产按维度分组汇总（type/account/allocation，含 items 明细）"""
    dimension = request.args.get('dimension', 'type')
    if dimension not in ('type', 'account', 'allocation'):
        return jsonify({'data': [], 'message': f'不支持的维度: {dimension}', 'error_code': 1001}), 400
    member_id = parse_query(MemberSliceQuery).member_id
    try:
        with get_db() as db:
            data = get_position_groups(db, get_family_id(), dimension, member_id)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(internal_error_payload(e, 'position_groups', [])), 500


@bp.post('/summary/snapshots/')
def create_snapshot():
    """记录当日资产快照（幂等 upsert，同 natural 日覆盖）。

    请求体可选 `snapshot_date`（YYYY-MM-DD）用于历史回填；默认上海时区当日。
    金额自动聚合当前家庭总资产/负债/净资产，无请求体依赖。
    """
    try:
        body = request.get_json(silent=True) or {}
        snapshot_date = body.get('snapshot_date')
        with get_db() as db:
            data = write_asset_snapshot(db, get_family_id(), snapshot_date)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'create_snapshot', None)), 500


@bp.get('/summary/snapshots/')
def list_snapshots():
    """返回资产快照列表（升序），附 monthly_change_pct / yearly_change_pct 同比。

    支持 `start_date` / `end_date`（含）筛选。同比基准取基准日当天或之前最近
    一条快照；积累期无历史返回 null（前端降级展示）。分页为纯数据列表，量极小。

    #1181：支持 `ledger_id` 筛选——传入返回该账户的**账户级**快照序列，
    不传返回**家庭级**序列（既有行为不变）。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        ledger_id = request.args.get('ledger_id', type=int)
        with get_db() as db:
            data = get_snapshots(db, get_family_id(), start_date, end_date, ledger_id)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': [], 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'list_snapshots', [])), 500


@bp.get('/summary/pnl-calendar/')
def pnl_calendar():
    """#1812 每日收益日历（as-of 派生逐日盈亏；口径与六态定义见 services/pnl_calendar.py）。
    与 snapshots 的区别：快照记的是落库当时的状态，改持仓后历史不更新、回填还会把今天
    的值贴到历史日期上；本接口现算。`ledger_id` 同 snapshots（不传=家庭级）；#1925 加
    `granularity`（day 缺省回 `days`，month/year 回 `periods`，聚合下推），非法值回 400。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        ledger_id = request.args.get('ledger_id', type=int)
        granularity = request.args.get('granularity', GRANULARITY_DAY)
        with get_db() as db:
            data = build_pnl_series(db, get_family_id(), start_date, end_date, ledger_id, granularity)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'pnl_calendar', None)), 500


@bp.get('/summary/cash-flow/')
def cash_flow():
    """#2616 / #2681 资金流动（入金/出金/净投入/期末资产 + 净值与累计净投入双线）。

    `ledger_id` 与 `portfolio_id` 二选一（同传 400、都不传也 400，不设隐式默认）。
    组合级 = 成员账本集合一次聚合（`services/scope.member_ledger_ids`），组合内互转由
    `cashflow_layers.pair_internal_transfers` 配对抵消为 0，与「Σ 账户 ≡ 家庭」同一条可加性。
    累计指标恒为「自开户以来」，`start_date`/`end_date` 只影响逐笔流水、月度柱状与曲线。
    口径与现金残差推导见 `docs/spec/cashflow-layers.md`。
    """
    try:
        with get_db() as db:
            data = build_cash_flow(
                db,
                get_family_id(),
                ledger_id=request.args.get('ledger_id', type=int),
                portfolio_id=request.args.get('portfolio_id', type=int),
                start_date=request.args.get('start_date'),
                end_date=request.args.get('end_date'),
            )
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'cash_flow', None)), 500


@bp.get('/summary/pnl-attribution/')
def pnl_attribution():
    """#2135 区间收益归因（逐品种 / 大类贡献；复用 pnl 引擎唯一盈亏口径）。

    `start_date` / `end_date` 缺省同 pnl-calendar（end=今日，start=end−29）；
    `ledger_id` 与 `portfolio_id` 互斥（同时传 400）。Σ positions[].pnl ≡
    同窗 pnl-calendar 的 month_total（构造保证，见 services/pnl_calendar.py）。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        ledger_id = request.args.get('ledger_id', type=int)
        portfolio_id = request.args.get('portfolio_id', type=int)
        with get_db() as db:
            data = compute_range_attribution(db, get_family_id(), start_date, end_date, ledger_id, portfolio_id)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'pnl_attribution', None)), 500


@bp.get('/summary/cleared-cycles/')
def cleared_cycles():
    """#2131 清仓周期统计（只读现算）：从流水聚合「首买→末卖」周期 + 跨周期汇总。

    参数 ledger_id / symbol / include_cash_equivalents / start_date / end_date，
    返回结构与口径详见 services/analytics/cleared_cycles.py（视图层不重复口径说明）。

    `start_date` / `end_date`（#2774）按**末卖日**裁剪，缺省 = 投资以来；格式错 400
    而不是静默当成「不过滤」——静默降级会让用户以为筛选生效了。

    `include_post_clear`（#2773）口径与四个状态码见 services/analytics/cleared_cycles.py。
    """
    try:
        ledger_id = request.args.get('ledger_id', type=int)
        symbol = (request.args.get('symbol') or '').strip() or None
        include_cash = str(request.args.get('include_cash_equivalents') or '').lower() in ('1', 'true', 'yes')
        include_post_clear = str(request.args.get('include_post_clear') or '').lower() in ('1', 'true', 'yes')
        with get_db() as db:
            data = build_cleared_cycles(
                db,
                get_family_id(),
                ledger_id=ledger_id,
                symbol=symbol,
                include_cash_equivalents=include_cash,
                start_date=request.args.get('start_date'),
                end_date=request.args.get('end_date'),
                include_post_clear=include_post_clear,
            )
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'cleared_cycles', {'cycles': [], 'summary': {}})), 500


@bp.get('/summary/benchmarks/')
def benchmarks():
    """可选基准清单（#2685）：唯一出口 `BENCHMARK_INDICES`，前端下拉不再各自硬编码。

    历史上前端把选项写死成 `CSI300/CSI500/SPX`，而 `SPX` 不在清单里 ⇒ 选中必走
    `unrecognized_benchmark` 降级、永远显示「--」。返回顺序 = 常量声明顺序（稳定，
    前端不做二次排序）。值一律为指数代码（`000300.SH`），旧的 `CSI300` 文本仍由
    `_BENCHMARK_TEXT_ALIASES` 解析，存量不迁移。
    """
    data = [{'code': code, 'name': name} for code, name in BENCHMARK_INDICES.items()]
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/summary/benchmark-excess/')
def benchmark_excess():
    """#2134 账户/组合/家庭区间收益 vs 基准指数超额收益（账本对齐-D）。

    查询参数：`start_date` / `end_date`（YYYY-MM-DD，**必填**）、`ledger_id` /
    `portfolio_id`（互斥，均不传=家庭级）。三条口径（scope 区间收益 / 指数区间
    涨跌幅 / 超额）与全部降级原因见 services/analytics/benchmark_excess.py——
    基准缺失一律诚实降级 None，不拿别的指数顶替。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if not start_date or not end_date:
            raise ValueError('start_date 与 end_date 必填（YYYY-MM-DD）')
        ledger_id = request.args.get('ledger_id', type=int)
        portfolio_id = request.args.get('portfolio_id', type=int)
        with get_db() as db:
            data = build_scope_excess(
                db,
                get_family_id(),
                start_date,
                end_date,
                ledger_id=ledger_id,
                portfolio_id=portfolio_id,
            )
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify(internal_error_payload(e, 'benchmark_excess', None)), 500


@bp.get('/summary/fund-valuation/')
def fund_valuation():
    """#2141/#2142 收盘估值定格清单（某日，需登录）。

    查询参数：
    - `date`：YYYY-MM-DD，默认上海时区今日；
    - `fund_code`：可选，单基金过滤。

    返回该日定格行（fund_code / estimated_nav / change_pct / source / source_time /
    status / official_nav / deviation / deviation_pct）按 fund_code 升序；日期非法回 400。
    """
    raw_date = (request.args.get('date') or '').strip()
    try:
        query_date = date.fromisoformat(raw_date) if raw_date else today_shanghai()
    except ValueError:
        return jsonify(
            {'data': [], 'message': f'date 格式非法（应为 YYYY-MM-DD）: {raw_date!r}', 'error_code': 1001}
        ), 400
    fund_code = request.args.get('fund_code')
    try:
        with get_db() as db:
            data = list_fund_valuation_rows(db, query_date, fund_code=fund_code)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(internal_error_payload(e, 'fund_valuation', [])), 500


@bp.get('/summary/ghost-duplicates/')
def ghost_duplicates():
    """#1066 / #1020：family 级「幽灵重复」扫描（跨账本疑似重复交易预警）。

    识别同一笔交易疑似出现在多个账本（跨账本重复导入），供前端非阻断软提示
    横幅指名来源账本。不阻断任何操作，仅预警。
    """
    try:
        with get_db() as db:
            data = scan_cross_ledger_duplicates(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        # 标准错误信封 {data, message, error_code}（AGENTS.md 接口契约）
        return jsonify(internal_error_payload(e, 'ghost_duplicates', [])), 500
