# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : manager_profile.py
# app/services/manager_profile.py
"""基金经理资料聚合（#1970 · 产品详情页基金经理详情区块）。

反向于 :mod:`app.services.fund_profile`（那只回答「某只基金有哪些经理」）：
此处回答「**某位经理管过哪些基金**」。funds 域同样没有对应端点
（``/api/funds/managers/search/`` 是按姓名模糊搜，与本问题无关），故在此补出口。

## 为什么一期只给「任职基金列表」，且任期字段一律降级

设计文档 §6 标注经理「字段多为空 → 诚实降级」。本次对生产库（``managers`` 4267 行 /
``fund_managers`` 34812 行）实测填充率，结论与文档一致且更极端：

===========================  ==========  ======  ==========
字段                填充              说明
===========================  ==========  ======  ==========
``managers.name``            4267/4267  100%     可展示
``managers.company_id``      4264/4267  99.9%    可展示
``managers.appointment_date``      0/4267    0%  **全空**
``managers.sum_scale``             0/4267    0%  **全空**
``managers.best_return``           0/4267    0%  **全空**
``managers.avatar_url``            0/4267    0%  **全空**
``fund_managers.start_date``       0/34812   0%  **全空**
``fund_managers.end_date``         0/34812   0%  **全空**
===========================  ==========  ======  ==========

## 字段填充率：#1970 的判断已被本轮实测推翻（下方「扩展」节）

设计文档 §6 标注经理「字段多为空→ 诚实降级」。对生产库（``managers`` 4267 行/
``fund_managers`` 34812 行）实测填充率，``appointment_date`` / ``sum_scale`` /
``best_return`` / ``start_date`` / ``end_date`` **全为 0%**，故 #1970 一律返回
``None``、前端显示「—」，**不用 mock 顶替**（G1 教训）。

⚠️ **但「0%」不等于「拿不到」**（#1970 扩展实测结论）：

- ``sum_scale`` / ``best_return`` / tenure天数三列东财接口**本来就返回**，
  是 ``fund_manager_job._save_data`` 只写 ``mgr_code`` / ``name`` / ``company_id``
  **把已拿到的数据丢弃了** —— 根因是**写入侧裁剪**，不是数据源缺失；
- ``start_date`` / ``end_date`` 来自天天基金 F10 ``jjjl_<code>.html``，
  此前**根本没接**。

故本轮起这些字段不再一律 ``None``，改为「有则给、无则降级」。

关联完整性实测：孤儿关联（``fund_id`` / ``mgr_id`` 失效）**0 条**，
无基金关联的经理**0 位**——故列表不需要额外的「数据异常」兜底分支。

## 转换层：为什么「存储」与「展示」要分开（#1970 扩展）

原始值是**为计算而存**的，界面要的是**给人看的**：

=========================  ====================  =================================
字段库内原值                界面显示             换算位置
=========================  ====================  =================================
``sum_scale= 307.94``     ``307.94 亿元``      :func:`build_scale_display`
``best_return= 297.54``    ``+297.54%``         :func:`build_return_display`
``appointment_date``       ``14 年又 15 天``    :func:`build_tenure_display`
=========================  ====================  =================================

换算全部在 :mod:`app.services.tenure_display`，**不在本模块、不在视图层、更不在前端**。
这样做的直接收益：口径只有一处实现，改口径不会漏改某个页面。

**原始值也照给**（``sum_scale`` 等原字段保留在出参里）：转换层是**增加**表达力，
不是替换。后端其他调用方仍可拿到裸数值做自己的判断。

## 为什么用 ``mgr_code`` 而非姓名做检索键

``managers`` 有 **119 组重名**（最多「吴昊」6 位、「张磊」「刘洋」各 5 位），
姓名不是唯一键；而 ``mgr_code`` 是 12 位哈希、100% 唯一，是 ``managers`` 表的
业务唯一键。故入参与路由均按 ``mgr_code``。

由于重名，列表里**必须带公司名**消歧，否则「吴昊」会显示成六个同名的人。

## 同一 (经理, 基金) 存在多行时必须按 fund_code 去重（#2215）

``fund_managers`` 只有自增 ``id`` 主键，**没有 (fund_id, mgr_id) 业务唯一约束**
（``app/domains/funds/models.py`` 的 ``FundManager``），库内可存在同一任职的多行
——实测经理详情页「任职基金」列表**每只基金渲染两次**。读侧 join 是按关联行扇出的
（一行关联 = 一行输出），故去重落在 :func:`_managed_funds` 查询层；``fund_count``
同口径改按 ``distinct fund_id`` 计数，否则「共 N 只」会比去重后的列表虚高、
与截断提示「仅显示前 M 只」自相矛盾。

A/C 份额是**不同的 fund_code**（不同的基金行），按代码各自分列展示，不在去重
范围内——去重只消「同一代码出现多次」。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.manager_code import bare_manager_code
from app.services.tenure_display import (
    build_return_display,
    build_scale_display,
    build_tenure_display,
)

# 列表默认返回条数。经理最多管 42 只基金，但那是极端值；20 条足够覆盖绝大多数，
# 且前端不做分页（详情页是「看一眼」的定位，不是列表页）。
DEFAULT_FUND_LIMIT = 20


def _iso(value) -> Optional[str]:
    """date/datetime → ISO 字符串；空值返回 None（前端降级为「—」）。"""
    if value is None:
        return None
    return value.isoformat()


def _fund_company(db: Session, company_id: Optional[int]) -> Optional[str]:
    """公司 id → 公司名。未绑定公司时返回 None。"""
    if not company_id:
        return None
    from app.domains.funds.models import FundCompany

    row = db.query(FundCompany.name).filter(FundCompany.id == company_id).first()
    return row[0] if row else None


def build_manager_profile(
    db: Session,
    mgr_code: str,
    fund_limit: int = DEFAULT_FUND_LIMIT,
    as_of: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """一次拼出单位基金经理的资料 + 其任职基金列表。

    Args:
        mgr_code: 12 位 ``managers.mgr_code``（**非姓名**，库内存在重名）。
        fund_limit: 任职基金返回条数上限。
        as_of: 年限计算基准日，默认今天。测试可注入以得到确定结果。

    Returns:
        资料 dict；**经理不存在时返回 None**（由调用方转 404）。

    出参分两档（**新增，不删除旧字段**）：

    - 原始档：``sum_scale`` / ``best_return`` / ``appointment_date`` 等裸值仍在，
      供其他调用方与交叉校验使用；
    - 展示档：``scale_display`` / ``best_return_display`` / ``tenure_display``，
      由 :mod:`app.services.tenure_display` 换算并附口径元数据。

    字段缺失一律 ``None``，由前端降级为「—」，不编造占位值。
    """
    from app.domains.funds.models import Manager

    code = bare_manager_code(mgr_code)
    if not code:
        raise ValueError('缺少 mgr_code')

    # 归一后**大小写不敏感**匹配：入参可能来自 watchlist symbol（`MGR_<code>`），
    # 且详情页路由的 symbol 会被 `resolve_product_identity` 大写化；库内是小写派生码。
    # 少这一步，**每一张经理详情页**都会落到「经理不存在」（2026-10-11 实测）。
    manager = db.query(Manager).filter(func.lower(Manager.mgr_code) == code).first()
    if manager is None:
        return None

    funds = _managed_funds(db, manager.id, fund_limit, as_of=as_of)
    sum_scale = float(manager.sum_scale) if manager.sum_scale is not None else None
    best_return = float(manager.best_return) if manager.best_return is not None else None

    return {
        'mgr_code': manager.mgr_code,
        'name': manager.name,
        # 重名靠公司消歧（库内 119 组重名，最多 6 位同名）
        'company': _fund_company(db, manager.company_id),
        'company_full_name': _fund_company_full_name(db, manager.company_id),
        'company_scale': _fund_company_scale(db, manager.company_id),
        'mgr_type': manager.mgr_type,
        'appointment_date': _iso(manager.appointment_date),
        'sum_scale': sum_scale,
        'best_return': best_return,
        'avatar_url': manager.avatar_url or None,
        # ── 展示档（转换层，详见模块 docstring「转换层」节）──
        'scale_display': build_scale_display(sum_scale),
        'best_return_display': build_return_display(best_return),
        # 从业年限以**首次任职日**为基准（非各基金任期起算），口径记在 basis 上。
        #
        # `raw` 由起始日**反算**回天数，而非回传库里的原值：`managers` 表没有
        # `tenure_days` 列（天数只是入站数据，不入库），故溯源值只能这样重建。
        # 它与东财原始天数的差异**恰在 ±1 天内**（基准日口径问题，见
        # :meth:`app.services.sync.jobs.fund_manager_job.FundManagerSyncJob._derive_appointment_date`），
        # 用于「这个起始日大概对应多少天从业」的审计，不作精确溯源。
        'tenure_display': build_tenure_display(
            manager.appointment_date,
            'em_days_derived',
            as_of=as_of,
            raw=(
                None if manager.appointment_date is None or as_of is None else (as_of - manager.appointment_date).days
            ),
        ),
        'fund_count': funds['total'],
        'active_fund_count': funds['active_in_list'],
        'funds': funds['items'],
    }


def _fund_company_full_name(db: Session, company_id: Optional[int]) -> Optional[str]:
    """公司全称（AMAC 公示口径，如「易方达基金管理有限公司」）。

    与简称分列返回：详情页副标题位置适合放全称，简称留给列表页消歧用。
    实测全称仅 AMAC 名录任务写，覆盖低于简称，故允许为 None。
    """
    if not company_id:
        return None
    from app.domains.funds.models import FundCompany

    row = db.query(FundCompany.full_name).filter(FundCompany.id == company_id).first()
    return row[0] if row else None


def _fund_company_scale(db: Session, company_id: Optional[int]) -> Optional[float]:
    """公司整体管理规模（亿元），仅作展示参照。

    与经理个人 ``sum_scale`` 不同口径（后者只是其**现任**基金合计），
    两者并列易被误读为「占比」，故返回值同时交给前端决定是否加口径注释。
    """
    if not company_id:
        return None
    from app.domains.funds.models import FundCompany

    row = db.query(FundCompany.scale).filter(FundCompany.id == company_id).first()
    if not row or row[0] is None:
        return None
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return None


def _managed_funds(db: Session, mgr_id: int, limit: int, as_of: Optional[date] = None) -> Dict[str, Any]:
    """任职基金列表 + 总数 + 在任数。

    关联完整性已实测（孤儿 0 条），故不再逐条判断「基金是否已删除」。

    排序取**基金简称**而非任职起始日：``start_date`` 是本轮才接上的（此前全空），
    而本轮只对**目标池**回填任期（jjjl 每只基金一次 HTTP，全量回填不现实），
    大部分行仍为空 → 拿它排序会退化成无序（全表同值）。按名称排至少稳定可读。

    **去重（#2215）**：``fund_managers`` 无 (fund_id, mgr_id) 唯一约束，同一任职
    可能存多行，join 会按关联行扇出（实测「每只基金出现两次」）。这里按
    ``fund_code`` 只保留一条，并且**先去重再截断**——重复行挤占 ``limit`` 名额会
    让「仅显示前 M 只」少算。单个经理的关联行数量有限（实测在管最多 42 只），
    全取再截断的开销可忽略。

    Args:
        as_of: 年限计算基准日，默认今天（测试注入）。
    """
    from app.domains.funds.models import Fund, FundManager

    # 总数与列表必须同口径（去重后），否则「共 N 只」虚高、与截断提示自相矛盾
    total = db.query(func.count(func.distinct(FundManager.fund_id))).filter(FundManager.mgr_id == mgr_id).scalar() or 0

    rows = (
        db.query(
            Fund.fund_code,
            Fund.name,
            FundManager.is_classic,
            FundManager.start_date,
            FundManager.end_date,
            FundManager.id,
        )
        .join(FundManager, FundManager.fund_id == Fund.id)
        .filter(FundManager.mgr_id == mgr_id)
        # 同名（重复关联行）之间再按关联行 id 定序，保证取舍结果稳定
        .order_by(Fund.name, FundManager.id)
        .all()
    )

    items: List[Dict[str, Any]] = []
    # 去重：fund_code → (取舍权重, items 下标)。命中更高权重时**原地替换**，
    # 位置保持首次出现处，整体顺序仍由 order_by(Fund.name) 决定。
    picked: Dict[str, Tuple[int, int, int, int]] = {}

    for fund_code, name, is_classic, start_date, end_date, rel_id in rows:
        item = {
            'fund_code': fund_code,
            'name': name,
            'is_classic': bool(is_classic),
            'start_date': _iso(start_date),
            'end_date': _iso(end_date),
            # 在任标记 = 未记录卸任日。**不能用东财全量表的「现任基金」**：
            # 实测张坤已于2026-05-22 卸任蓝筹精选，但 `fund_manager_em` 仍把他列为
            # 该基金现任（粗粒度、不含卸任时间）。以 F10 任期分段为准才准确。
            'is_active': end_date is None,
            'tenure_display': build_tenure_display(
                start_date,
                'em_days_derived' if start_date else 'derived_from_start',
                as_of=as_of,
            ),
        }
        # 重复关联行的取舍（元组越大越优）。为什么「任期完整性」必须排在
        # is_active 前面：is_active = (end_date is None) 会把「任期从未回填」
        # 也读成在任，只按 is_active 优先会选中空行，把已卸任的基金显示成「至今」。
        rank = (
            1 if start_date is not None else 0,  # ① 任期已回填的行更完整
            1 if end_date is None else 0,  # ② 同等完整时保留在任行（is_active 优先）
            1 if is_classic else 0,  # ③ 代表作标记是信息，True 优先
            -rel_id,  # ④ 兜底稳定序：先落库的原始行
        )
        prev = picked.get(fund_code)
        if prev is None:
            picked[fund_code] = (rank, len(items))
            items.append(item)
        elif rank > prev[0]:
            # 替换后同步更新权重，否则后续重复行会与**旧**权重比较
            picked[fund_code] = (rank, prev[1])
            items[prev[1]] = item

    # 先去重、后截断：limit 必须作用在去重后的列表上
    items = items[:limit]

    # 在任数单独统计：只统计返回的 limit 条会让「在任 2 只」在有 42 只经理时显得
    # 与真实不符，故标明是「已列出的在任数」而非全量在任数。
    active_in_list = sum(1 for i in items if i['is_active'])

    return {'total': total, 'active_in_list': active_in_list, 'items': items}
