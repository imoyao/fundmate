# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 17:21
# File : async_backfill.py
# -*- coding: utf-8 -*-
"""
异步数据回填工具。

在用户新增持仓或自选标的时，后台静默拉取历史净值/行情数据。
使用轻量级线程，不阻塞主请求，失败静默处理。

并发口径（2026-10-28 修复 `database is locked`）：
本机 dev 是**单个 SQLite 文件**（WAL 只允许一个写事务），而导入一次持仓会逐只基金触发
回填（`orchestrator_commit.trigger_metadata_update`）——实测一次导入 90+ 只，等于瞬间
起 90+ 个线程同时写 `daily_worth`。`busy_timeout=30s` 被这批并发写耗光后抛
`database is locked`，又被本模块的 `except` 吞成一条 warning ⇒ **这批净值静默丢失**，
用户看到的是走势图缺数据、且日志里只有一行「失败」。

因此三件事必须同时成立，缺一条都还会复发：
1. **写入串行化**（`_WRITE_LOCK`）：同一时刻只允许一个回填线程写库；
2. **locked 退避重试**（`_write_with_retry`）：与 web 请求 / scheduler 抢锁时重试，
   而不是把异常当成终态；
3. **限流 + 去重**（`_WORKER_SLOTS` / `_INFLIGHT`）：避免线程风暴与同标的重复抓取。
网络抓取**不在锁内**——90 只基金的 HTTP 抓取仍然并行，被串行化的只有写库那一段。
"""

import random
import threading
import time
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy import exc as sa_exc

from app.core import database  # 晚绑定：属性在调用时解析，勿改成 from-import（#1608）
from app.core.constants import SOURCE_VERSION_V2_RECALC
from app.core.db_utils import bulk_insert_if_not_exists
from app.core.time_utils import today_shanghai
from app.domains.funds.models import DailyWorth, MoneyFundDailyWorth
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.adapters.akshare_adapter import AkshareAdapter
from app.services.adapters.xalpha_adapter import XalphaAdapter
from app.services.money_fund_yield import compute_series_from_records


def _as_date(value) -> Optional[date]:
    """将 'YYYY-MM-DD' 字符串解析为 date；解析失败返回 None。"""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _drop_today(records: list, date_field: str) -> list:
    """T 日不回填：丢弃日期 >= 今日（上海时区）的记录，回填止于 T-1。

    当日净值/行情未收盘、未定稿，回填进去会让用户看到不完整/变动中的数据，
    故仅回填到 T-1。适配器若本身只返回已定稿数据，本过滤为防御性冗余。
    """
    cutoff = today_shanghai()
    kept = []
    for r in records:
        d = _as_date(r.get(date_field))
        if d is not None and d >= cutoff:
            continue
        kept.append(r)
    return kept


# --------------------------------------------------------------------------- #
# 后台回填的并发闸门（见模块 docstring；三条缺一不可）
# --------------------------------------------------------------------------- #

# 写锁：SQLite 单写者模型的进程内对应物。用 RLock 而非 Lock，便于将来在同一线程内嵌套写入。
_WRITE_LOCK = threading.RLock()

# 同时在跑的 worker 上限：一次导入 90 只基金只应占 4 个跑批槽位，其余线程在信号量上排队。
_MAX_WORKERS = 4
_WORKER_SLOTS = threading.BoundedSemaphore(_MAX_WORKERS)

# in-flight 去重：同一 (asset_type, code) 只允许一个回填任务在跑/在队，避免「导入一次 + 首屏
# 按需回填」两条链路对同一只基金重复抓取全历史。
_INFLIGHT: set = set()
_INFLIGHT_LOCK = threading.Lock()

# locked 重试：首轮立即重试，间隔 0.3/0.6/1.2/2.4s（+抖动），最多 5 次 ≈ 峰值 4.5s。
_LOCKED_MARK = 'database is locked'
_WRITE_ATTEMPTS = 5


def _write_with_retry(db, write):
    """串行化 + locked 退避重试地执行一段写库逻辑，返回其返回值。

    两个约束：
    - ``write`` 必须**幂等**（本模块的写入都是 `INSERT OR IGNORE`），重跑安全；
    - 重试前必须 ``db.rollback()``：失败的事务在 Session 上留下失效状态 / 过期快照，
      不回滚则重跑仍在同一快照上撞同一个 locked。

    **只有**消息含 ``database is locked`` 的 ``OperationalError`` 才重试；其余异常原样上抛，
    交给调用方既有的 except 分支（避免把「表不存在」「列不匹配」这类真 bug 重试 5 次后掩盖）。
    """
    with _WRITE_LOCK:
        for attempt in range(_WRITE_ATTEMPTS):
            try:
                return write()
            except sa_exc.OperationalError as err:
                if _LOCKED_MARK not in str(err):
                    raise
                if attempt >= _WRITE_ATTEMPTS - 1:
                    raise
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001 - 尽力清理，重跑时的错误才会暴露真因
                    pass
                time.sleep(0.3 * (2**attempt) + random.uniform(0, 0.15))
    raise RuntimeError('unreachable: 循环必然 return 或 raise')  # pragma: no cover


def _insert_rows(db, model, rows: list, unique_columns: list) -> int:
    """批量 `INSERT OR IGNORE` + 写锁 + locked 重试的薄封装（全模块唯一写入口）。"""
    return _write_with_retry(
        db,
        lambda: bulk_insert_if_not_exists(
            db,
            model,
            rows,
            unique_key=unique_columns[0],  # 兼容旧参数
            unique_columns=unique_columns,  # 实际使用的联合键
        ),
    )


def _backfill_fund_nav(fund_code: str):
    db = database.get_session()
    try:
        adapter = XalphaAdapter()
        records = adapter.fetch_fund_nav(fund_code)
        if not records:
            return
        # T 日不回填：丢弃 date >= 今日（上海时区）的记录，回填止于 T-1
        records = _drop_today(records, 'date')
        if not records:
            return

        money_records = []
        normal_records = []
        for r in records:
            if r.get('is_money_fund'):
                money_records.append(
                    {
                        'fund_code': fund_code,
                        'date': r['date'],
                        'nav_per_10k': r['unit_nav'],
                        # #2120 P0-1：七日年化随行落库（下方按窗口统一回填）
                        'annual_return_7d': None,
                        # #863 P0-4：与 fund_nav_job 一致，新写入标记 v2_recalc
                        'source_version': SOURCE_VERSION_V2_RECALC,
                    }
                )
            else:
                normal_records.append(
                    {
                        'fund_code': fund_code,
                        'date': r['date'],
                        'unit_nav': r['unit_nav'],
                        'acc_nav': r.get('acc_nav', 0),
                    }
                )

        # #2120 P0-1：七日年化是**滑动窗口**指标（每行的窗口是它自己往前 7 个自然日），
        # 所以不能逐行独立算。本路径一次拿到全历史（pingzhongdata），
        # 直接在内存里按窗口算好随行落库，无需再回查 DB。
        # 口径与 `fund_nav_job` 共用 `money_fund_yield`，避免两处各算一套。
        if money_records:
            for row, (_day, _nav, value) in zip(money_records, compute_series_from_records(money_records)):
                row['annual_return_7d'] = value

        if normal_records:
            total = _insert_rows(db, DailyWorth, normal_records, ['fund_code', 'date'])
            logger.info(f'异步回填基金 {fund_code} 净值 {total} 条')
        if money_records:
            # 货币基金元数据随行落库（七日年化在内存算好，见上）
            total = _insert_rows(db, MoneyFundDailyWorth, money_records, ['fund_code', 'date'])
            logger.info(f'异步回填货币基金 {fund_code} 收益 {total} 条')
    except sa_exc.OperationalError as e:
        db.rollback()
        if _LOCKED_MARK in str(e):
            # 重试已耗尽：说明写锁被长期占用（另一个实例 / 长事务）。留明确痕迹，
            # 不能像历史上那样与普通解析失败混在同一条 warning 里（那是「静默丢数据」的入口）。
            logger.warning(f'异步回填基金 {fund_code} 净值失败：写库锁冲突，重试 {_WRITE_ATTEMPTS} 次仍 locked')
        else:
            logger.warning(f'异步回填基金 {fund_code} 净值失败: {e}')
    except Exception as e:
        db.rollback()
        logger.warning(f'异步回填基金 {fund_code} 净值失败: {e}')
    finally:
        db.close()


def _backfill_stock_price(symbol: str):
    db = database.get_session()
    try:
        sec = db.query(Security).filter(Security.symbol == symbol).first()
        if not sec:
            return
        security_id = sec.id
        stock_symbol = sec.symbol

        adapter = AkshareAdapter()
        records = adapter.fetch_stock_price(symbol)
        if not isinstance(records, list) or not records:
            return
        # T 日不回填：丢弃 trade_date >= 今日（上海时区）的记录，回填止于 T-1
        records = _drop_today(records, 'trade_date')
        if not records:
            return

        allowed_columns = {c.name for c in PriceHistory.__table__.columns}
        clean_records = []
        for r in records:
            r['security_id'] = security_id
            r['symbol'] = stock_symbol
            filtered = {k: v for k, v in r.items() if k in allowed_columns}
            clean_records.append(filtered)

        if clean_records:
            total = _insert_rows(db, PriceHistory, clean_records, ['symbol', 'trade_date'])
            logger.info(f'异步回填股票 {symbol} 行情 {total} 条')
    except sa_exc.OperationalError as e:
        db.rollback()
        if _LOCKED_MARK in str(e):
            logger.warning(f'异步回填股票 {symbol} 行情失败：写库锁冲突，重试 {_WRITE_ATTEMPTS} 次仍 locked')
        else:
            logger.warning(f'异步回填股票 {symbol} 行情失败: {e}')
    except Exception as e:
        db.rollback()
        logger.warning(f'异步回填股票 {symbol} 行情失败: {e}')
    finally:
        db.close()


def _run_backfill(key: tuple, target_func, code: str):
    """worker 线程体：占一个跑批槽位执行回填，结束后一定释放 in-flight 标记。

    `finally` 里移除 in-flight 是必须的：漏掉会让这只基金**永久**被判定为「已在跑」，
    之后按需首屏回填（`fund_nav_on_demand`）与再次导入都静默跳过——比报错更难发现。
    """
    try:
        with _WORKER_SLOTS:
            target_func(code)
    except Exception as e:  # pragma: no cover - target_func 内部已各自兜底，这里只防线程静默死亡
        logger.warning(f'异步回填任务异常退出: {key} {e}')
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT.discard(key)


def _dispatch_backfill(key: tuple, target_func, code: str) -> bool:
    """去重 + 起线程（`trigger_backfill` 的实际动作，独立成缝以便测试直接驱动）。

    为什么拆出来：`tests/conftest.py` 的 autouse 夹具把 `trigger_backfill` 整个替换成
    空实现（防止测试期真的起线程打网络），于是「去重与释放」这套判据在测试里无处可跑——
    隔着被替换掉的入口去测，测到的是夹具而不是本模块。判据钉在这里，`trigger_backfill`
    只负责「按资产类型挑目标函数」。

    Returns:
        True = 已起线程；False = 同标的已在跑/在队，本次跳过。
    """
    asset_type, _code = key
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT:
            # 同一标的已在跑/在队：重复触发没有任何收益，只会在 SQLite 上多排一次全历史写入。
            logger.debug(f'跳过重复的异步回填: {asset_type} {code}')
            return False
        _INFLIGHT.add(key)

    thread = threading.Thread(
        target=_run_backfill,
        args=(key, target_func, code),
        daemon=True,
        name=f'backfill-{asset_type}-{code}',
    )
    thread.start()
    logger.debug(f'已触发异步回填: {asset_type} {code}')
    return True


def trigger_backfill(asset_type: str, code: str):
    """
    触发异步回填。根据资产类型自动选择回填方式。

    Args:
        asset_type: 'fund' 或 'stock'
        code: 基金代码（6位数字）或股票代码（如 SH600519）
    """
    if asset_type == 'fund':
        target_func = _backfill_fund_nav
    elif asset_type in ('stock', 'etf', 'bond'):
        target_func = _backfill_stock_price
    else:
        return

    _dispatch_backfill((asset_type, code), target_func, code)
