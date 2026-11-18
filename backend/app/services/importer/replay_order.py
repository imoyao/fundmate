# -*- coding: utf-8 -*-
"""导入落库的**时间正序重放**顺序（#3004）。

## 为什么需要这一层

券商 / 基金平台导出的交割单普遍是**时间倒序**（最新一行在最前），例如招商证券交割单
2023-08-16 在首行、2022-07-01 在末行。落库若照文件顺序逐条处理，卖出会先于它的买入
入库：此时持仓还不存在，``process_orphan_sell_or_withdraw`` 只能把卖出降级成孤儿流水
（``position_id=NULL``），份额一点都不扣；随后买入照常累加份额，**持仓就永远停在
「只买不卖」的累加值**（实测账户 26：46 条持仓虚挂 20.9 万，75 笔卖出全是孤儿）。

## 为什么放在落库入口而不是各解析器

顺序是「持仓随流水演进」这件事的前置条件，与哪个券商、哪种文件格式无关。放在
``ImportOrchestrator.commit()`` 里，全部解析器（招商 / 同花顺 / 标准模板 / 天天 /
支付宝 / AI 识别 / OCR）一并生效，新增解析器也不用再记得排一次序。

## 同日并列的取舍

**份额减少的操作排在份额增加之后**：可转债 / ETF 支持 T+0，当天买当天卖是常态；
反过来（先卖后买）在同一天里属于「卖了老的再买回」，先买后卖只让成本均价按两者
均价重算，数量结果一致——两害相权取其轻。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List

from app.services.import_records import StandardTransactionRecord
from app.services.importer.mappings import BusinessType

# 份额「减少」的操作：同日排队时排在增仓类之后，否则 T+0 当天卖出会落到买入之前。
SHRINKING_OP_CODES = frozenset(
    {
        BusinessType.SELL.code,
        BusinessType.WITHDRAW.code,
        BusinessType.BOND_REDEEM.code,
    }
)


def replay_order_key(record: StandardTransactionRecord) -> tuple:
    """落库重放键：有效交易日升序，同日「增仓类」在「减仓类」之前。

    有效交易日取 ``trade_date or confirm_date``，与全站流水排序口径
    （``transactions.dates`` 的 ``COALESCE(trade_date, confirm_date)``）一致。
    缺日期 / 类型异常时排到最后（``date.max``）——宁可让它读到当时的仓位，
    也不插到历史最前面。
    """
    day = record.trade_date or record.confirm_date
    if isinstance(day, datetime):  # datetime 是 date 子类，混排时直接比较会 TypeError
        day = day.date()
    if not isinstance(day, date):
        day = date.max
    shrinking = (record.business_type or '').lower() in SHRINKING_OP_CODES
    return (day, 1 if shrinking else 0)


def sort_records_for_replay(records: List[StandardTransactionRecord]) -> List[StandardTransactionRecord]:
    """按 :func:`replay_order_key` 稳定排序；同键保持解析器给出的原始相对顺序。

    ``sorted`` 是稳定排序：同一交易日、同一档位的多条记录（例如拆股前后、配对组内的
    主记录与从属记录）维持解析顺序，不引入新的不确定性。
    """
    return sorted(records, key=replay_order_key)
