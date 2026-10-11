# -*- coding: utf-8 -*-
# app/services/fund_company_backfill.py
"""基金公司的**按需回填**（#2037 方案 A · L3 懒加载）。

## 为什么需要它

`funds.company_id` 覆盖率长期只有约 11.5%（本库 3,104/26,938），于是场外基金详情页
的「基金公司」栏约 88.5% 显示「—」（`services/fund_profile.py` 取 `fund.company.name`，
前端 `ProductFundSection.vue` 渲染）。

**为什么不跑全库回填**：`fund_company_backfill` 在 `SYMBOL_BACKFILL_JOBS` 名单内，裸
`--full-sync` 被 CLI 拒绝；且 `data-strategy.md` §190 已把「全库 `company_id ≥90%`」列为
**无产品场景支撑的反面先例**——26,938 次外部请求换用户触达不到的字段。

**为什么不摘掉字段**：11.5% 已填的正是高价值用户看的字段，且详情页有现成的降级渲染。

故取 L3 层的标准做法（`data-strategy.md` §2「按需取 + 缓存 + 可降级 `—`」）：
**用户打开详情页时，若该只基金 `company_id` 为空，就按 symbol 单只回填并落库**——
触达不到的基金永远不请求、永远不存，全库覆盖率不再是目标。

## 关键约束（每条都有代价，不是口号）

1. **唯一写入口**：公司行一律经 `company_resolver.get_or_create_fund_company` 创建，
   identity 解析经 `resolve_company_identity`。本模块**不自己比对、不自己建行**——
   「招商基金」与「招商证券资管」归一化后同键，绕过 resolver 就会把 A 公司的官网写到
   B 公司上（最难发现的一类数据腐蚀）。取数口（`fetch_fund_company_of`）只负责把东财
   **简称**带回来，不做第二次身份解析。

2. **不能拖垮首屏**：取数口实测**连接复用后 43~87ms**（模块级长连接 Session，
   首次约 1.8s 握手），超时上限 6s，且失败进**负缓存**（`_MISS_CACHE`，默认 30 分钟）。
   没有负缓存的话，一只本就查不到公司的基金会让用户每次冷开详情页都白等一个超时——
   L3 的「可降级」就变成了「每次都卡」；没有长连接的话，每个冷开用户都要付一次
   TLS 握手，那才是真正拖垮首屏的那一份。

3. **串行化**：回填段（含外部请求与写库）整体走一把进程内锁。SQLite 只有一个写者，
   并发回填同一/不同 code 会同时抢写事务；且同一 code 并发打开会重复抓同一份外部数据。
   回填是低频路径（每只基金生命周期内通常只发生一次），串行的代价可接受，换来的是
   不重复请求 + 不撞写锁。

## 为什么不放在 `fund_profile.py` 里

「读资料」与「发现缺数据就写库」是两种职责，混在一个函数里会让调用方无法判断
它到底会不会改库——而这正是需要显式声明、显式命名的边界。放在独立模块后，
`build_fund_profile` 里那一行 import 就是「本聚合会按需写库」的完整声明。
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.services.adapters.eastmoney_adapter import fetch_fund_company_of
from app.services.sync.company_resolver import get_or_create_fund_company

# 负缓存：code -> 上次「查不到 / 抓取失败」的时刻（monotonic 秒）。
# 只记**失败**——成功的已落库，下一次直接走 DB 快路径，无需再进内存缓存。
_MISS_CACHE: Dict[str, float] = {}
# 负缓存存活时长（秒）。取 30 分钟的取舍：fundsuggest 失败多为网络抖动 / 限流，
# 半小时足以让用户刷新、切换详情页时不再重复吃超时；而半年才重试会让「刚被源补上
# 公司名」的基金长期留白。半小时是可调的保守值，不是精确结论。
_MISS_TTL_SECONDS = 30 * 60
# 负缓存条目上限：全库 26,938 只，若用户遍历全市场会把 dict 撑到 2.7 万条。
# 到上限即整体清空——负缓存本就是「尽力避免重复请求」，清空只损失一点命中率，
# 换来内存有界。清空后按时间自然重建，无需 LRU 那套复杂度。
_MISS_CACHE_MAX = 512
# 回填段（含外部请求 + 写库）串行锁，见模块 docstring 第 3 条。
_BACKFILL_LOCK = threading.Lock()


def _in_miss_cache(code: str) -> bool:
    return (time.monotonic() - _MISS_CACHE.get(code, 0.0)) < _MISS_TTL_SECONDS


def _remember_miss(code: str) -> None:
    if len(_MISS_CACHE) >= _MISS_CACHE_MAX:
        _MISS_CACHE.clear()
    _MISS_CACHE[code] = time.monotonic()


def reset_miss_cache() -> None:
    """清空负缓存（测试与需强制重试的场景用）。"""
    _MISS_CACHE.clear()


def ensure_fund_company(db: Session, fund_code: str) -> Optional[str]:
    """确保该只基金有基金公司，返回公司简称；确实没有时返回 ``None``（前端降级 `—`）。

    三条路径，从便宜到贵：

    1. **已有 `company_id`** → 直接读库返回，**零外部请求**（这是 11.5% 已填数据的路径）；
    2. **命中负缓存** → 立即返回 ``None``，不再打外部接口（防「每次冷开都白等超时」）；
    3. **按 symbol 单只回填** → 取东财简称 → 经唯一写入口建/匹配公司行 → 写
       `funds.company_id` 并提交 → 返回简称。

    基金不存在返回 ``None``（调用方本就应先确认基金存在；此处不抛异常以免把
    「查不到公司」与「基金不存在」混成同一种失败）。

    **本函数会 commit**：回填要跨请求存活就必须落库，而调用方持有的正是同一个
    market 域会话。调用方若在调用前已改了库内对象，须自行处理过期（`conventions.md`
    §2.13：请求路径默认 flush，跨请求存活才 commit——此处正是后者）。
    """
    from app.domains.funds.models import Fund, FundCompany

    code = (fund_code or '').strip()
    if not code:
        return None

    fund = db.query(Fund).filter(Fund.fund_code == code).first()
    if fund is None:
        return None
    if fund.company_id:
        # 路径 1：已有归属。显式查 FundCompany 而非走 `fund.company` relationship——
        # 后者会再打一次 SELECT，而这里要的只是那一行的 name。
        company = db.query(FundCompany).filter(FundCompany.id == fund.company_id).first()
        return company.name if company else None

    if _in_miss_cache(code):  # 路径 2
        return None

    with _BACKFILL_LOCK:  # 路径 3
        # 抢锁期间可能已被另一个请求填好（双击 / 多端同时打开同一只），故重新读一次。
        #
        # **刻意用 `refresh(fund)` 而不是 `expire_all()`**：后者会把调用方会话里**所有**
        # 实例一并过期——若调用方在同一会话改了别的对象，那些改动会被静默丢弃
        # （未提交时）或提前落盘（已改但未提交时）。只刷新本基金，不碰别人的对象。
        # `refresh` 要求实例仍在本会话的 identity map 里，故每次进入都重新 `query`
        # （拿到的是本会话缓存的同一实例）。
        fund = db.query(Fund).filter(Fund.fund_code == code).first()
        if fund is None:
            return None
        db.refresh(fund)
        if fund.company_id:
            company = db.query(FundCompany).filter(FundCompany.id == fund.company_id).first()
            return company.name if company else None

        try:
            fetched = fetch_fund_company_of(code)
        except Exception as e:  # 取数口已自带异常兜底，这里是最后一道保险
            logger.warning(f'按需回填基金 {code} 的基金公司失败: {e}')
            fetched = None

        if not fetched or not fetched.get('name'):
            # 查不到不等于「公司不存在」，也可能是源临时不可用：两者都不写库，
            # 只进负缓存，避免把一次网络抖动固化成永久留白。
            _remember_miss(code)
            return None

        try:
            company_id = get_or_create_fund_company(db, fetched['name'])
            if not company_id:
                db.rollback()
                _remember_miss(code)
                return None
            fund.company_id = company_id
            db.commit()
        except Exception:
            # `get_or_create_fund_company` 在同事务里 `flush` 了新建的公司行；若此处不
            # rollback，那行会**留在调用方的会话事务里**——调用方若随后 commit，就会把
            # 一行半成品（公司建好了、基金没挂上）落库。故失败一律回滚整段，不留残迹。
            db.rollback()
            logger.warning(f'按需回填基金 {code} 的基金公司时出错，已回滚', exc_info=True)
            _remember_miss(code)
            return None

        logger.info(f'按需回填基金 {code} 的基金公司：{fetched["name"]}')
        return fetched['name']
