# -*- coding: utf-8 -*-
"""基金经理档案写入侧（#1970 扩展：sum_scale / best_return / appointment_date）。

覆盖三组行为，都是「最容易写错且错了不会报错」的那类：

1. **``appointment_date`` 由天数反推**，而非直接存天数 —— 天数是**相对抓取日的
   滚动值**（今天 5125、明年 5190），存天数会让起始日每次同步都漂移且无法复核。
   实测张坤5125 → 2026-10-10 减 5125 = 2012-09-28，与天天基金 F10 实测的
   110011「任职起始日 2012-09-28」逐日相同。
2. **脏输入返回 None 而不是假日期** —— 0 / 负数 / 空串 / 非数字 / 缺键，
   任一情况下写出一个日期都是**假事实**，比留空危害大得多。
3. **存量行必须被回填，且只补 NULL** —— ``bulk_insert_if_not_exists`` 只插不更新，
   没有回填路径的话生产库 4267 行永远拿不到这三列，填充率仍是0%，
   等于把 #1970 的原始 bug 原样保留。

⚠️ 测试数据一律造在 **market 域**会话（``managers`` 属 market 域）。
"""

from contextlib import closing
from datetime import date

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Manager
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob

# 固定基准日：让反推结果可断言（真实实现用 date.today()）
TODAY = date(2026, 10, 10)


def _derive(item, today=TODAY):
    """调静态方法反推日期。"""
    return FundManagerSyncJob._derive_appointment_date(item, today=today)


def _job(db):
    """构造一个只借用 db 的 job 实例（反推/回填不触网，构造不跑同步）。"""
    job = FundManagerSyncJob.__new__(FundManagerSyncJob)
    job.db = db
    return job


def _seed_manager(mgr_code, name, **fields):
    with closing(market_session_factory()()) as db:
        exists = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        if exists is None:
            db.add(Manager(mgr_code=mgr_code, name=name, **fields))
        else:
            for k, v in fields.items():
                setattr(exists, k, v)
        db.commit()


def _read(mgr_code):
    with closing(market_session_factory()()) as db:
        m = db.query(Manager).filter(Manager.mgr_code == mgr_code).first()
        if m is None:
            return None
        return {
            'name': m.name,
            'sum_scale': m.sum_scale,
            'best_return': m.best_return,
            'appointment_date': m.appointment_date,
        }


# ── 反推：核心口径 ────────────────────────────────────────────


def test_derive_matches_empirical_calibration():
    """张坤实测校准：5125 天 → 2012-09-28（与天天基金 F10 逐日相同）。"""
    assert _derive({'tenure_days': 5125}) == date(2012, 9, 28)


def test_derive_uses_calendar_span_not_active_days():
    """口径为**日历跨度**：基准日不同，起始日随之平移（天数是相对量）。

    这是「存天数会漂移」的证据 —— 同一条数据在两个基准日得出两个起始日，
    所以必须反推成日期落库。
    """
    a = _derive({'tenure_days': 5125}, today=date(2026, 10, 10))
    b = _derive({'tenure_days': 5125}, today=date(2026, 10, 11))
    assert a == date(2012, 9, 28)
    assert b == date(2012, 9, 29)  # 基准日 +1 天，起始日也 +1 天


def test_derive_accepts_float_and_str():
    """适配器给的是 float /可能给脏字符串，都应能解析。"""
    assert _derive({'tenure_days': 5125.0}) == date(2012, 9, 28)
    assert _derive({'tenure_days': '5125'}) == date(2012, 9, 28)


def test_derive_handles_one_day_tenure():
    """最小合法值（1 天）应能反推，不被边界条件误伤。"""
    assert _derive({'tenure_days': 1}) == date(2026, 10, 9)


# ── 反推：脏输入一律None（假日期比留空危害大） ──────────────────


def test_derive_returns_none_for_dirty_input():
    """0 / 负数 / 空串 / 非数字 / None / 缺键 → 全部 None。

    这些若被反推成日期就是**假事实**：0 会算出「今天上任」，负数算出未来日，
    且都会污染展示层的从业年限。
    """
    for dirty in (0, -5, -1, '', 'abc', None, 'nan'):
        assert _derive({'tenure_days': dirty}) is None, f'{dirty!r} 应返回 None'
    # 整个键缺失（适配器未透传该列）
    assert _derive({}) is None


def test_derive_rejects_absurdly_large_tenure():
    """超大天数反推出远古日期时仍返回 date，但不越界成未来日。

    东财实测 max=8145（约22 年），这里用更大值只为确认不会崩。
    """
    got = _derive({'tenure_days': 20000})
    assert got is not None and got < date(1975, 1, 1)


# ── 存量回填：只补 NULL，不覆盖已有值 ───────────────────────────


def test_backfill_fills_null_columns_on_existing_row():
    """已存在的经理行要被回填 —— 这正是生产库 4267 行的处境。"""
    _seed_manager('bf001', '回填经理', sum_scale=None, best_return=None, appointment_date=None)

    with closing(market_session_factory()()) as db:
        stats = _job(db)._backfill_manager_profile(
            [
                {
                    'mgr_code': 'bf001',
                    'sum_scale': 307.94,
                    'best_return': 297.54,
                    'appointment_date': date(2012, 9, 28),
                }
            ]
        )
        db.commit()

    assert stats['updated'] == 1
    got = _read('bf001')
    assert got['sum_scale'] == 307.94
    assert got['best_return'] == 297.54
    assert got['appointment_date'] == date(2012, 9, 28)


def test_backfill_never_overwrites_existing_values():
    """已有值不被覆盖：数据源口径可能修正，无条件覆盖会让历史值被静默改写。"""
    _seed_manager('bf002', '不覆盖经理', sum_scale=1.23, best_return=4.56, appointment_date=date(2015, 1, 1))

    with closing(market_session_factory()()) as db:
        stats = _job(db)._backfill_manager_profile(
            [
                {
                    'mgr_code': 'bf002',
                    'sum_scale': 999.99,
                    'best_return': 888.88,
                    'appointment_date': date(2020, 5, 5),
                }
            ]
        )
        db.commit()

    assert stats['updated'] == 0  # 无脏字段 → 无需写
    got = _read('bf002')
    assert got['sum_scale'] == 1.23
    assert got['best_return'] == 4.56
    assert got['appointment_date'] == date(2015, 1, 1)


def test_backfill_fills_only_missing_columns_partially():
    """部分缺失时只补缺失的那几列，已有列保持原值。"""
    _seed_manager('bf003', '部分缺失', sum_scale=10.0, best_return=None, appointment_date=None)

    with closing(market_session_factory()()) as db:
        stats = _job(db)._backfill_manager_profile(
            [{'mgr_code': 'bf003', 'sum_scale': 999.0, 'best_return': 77.0, 'appointment_date': date(2011, 1, 1)}]
        )
        db.commit()

    assert stats['updated'] == 1
    got = _read('bf003')
    assert got['sum_scale'] == 10.0  # 原值保住
    assert got['best_return'] == 77.0  # 补上
    assert got['appointment_date'] == date(2011, 1, 1)  # 补上


def test_backfill_skips_unknown_mgr_code():
    """库中不存在的 mgr_code 跳过（不凭回填数据造经理行）。

    关系与档案行都由 ``_save_data`` 决定，回填只补列、不新建。
    """
    with closing(market_session_factory()()) as db:
        stats = _job(db)._backfill_manager_profile(
            [{'mgr_code': 'nonexistent999', 'sum_scale': 1.0, 'best_return': 1.0, 'appointment_date': date(2020, 1, 1)}]
        )
        db.commit()

    assert stats['updated'] == 0
    assert _read('nonexistent999') is None


def test_backfill_ignores_none_values():
    """回填数据本身为 None 时不动手（不能把 NULL 写回 NULL 还算「更新」）。"""
    _seed_manager('bf004', '全空经理', sum_scale=None, best_return=None, appointment_date=None)

    with closing(market_session_factory()()) as db:
        stats = _job(db)._backfill_manager_profile(
            [{'mgr_code': 'bf004', 'sum_scale': None, 'best_return': None, 'appointment_date': None}]
        )
        db.commit()

    assert stats['updated'] == 0
    got = _read('bf004')
    assert got['sum_scale'] is None
    assert got['appointment_date'] is None
