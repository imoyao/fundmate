# -*- coding: utf-8 -*-
"""证券历史行情同步任务（场内日线：股票 / ETF / 可转债）。

## 增量口径 = 缺口回补（#1104）

增量模式的起点是**每个 symbol 库内最新交易日的次日**，而不是固定的「昨天→今天」。
原写法（写死昨天→今天）没有任何自愈能力：任何一天没跑成功，那天就永久缺失且
再也不会被补。实测后果是各标的最后日期散落成满天星——SH601899 停在 8/14、
SZ000568 停在 7/20、SZ000001 停在 7/03、SZ000008 停在 5/29。本机调度不含本 job
（只靠 CI 每天 17:00 UTC 跑一次）时，这种断档尤其常见。

## 覆盖范围

目标池由 Orchestrator 传入（持仓 + 自选，`resolve_targets()` 的 stock 池）。
取数与复权口径见 `AkshareAdapter.fetch_stock_price`：`close` 未复权（展示 / 盈亏）、
`adj_close` 前复权（区间收益 / 回撤）。

## 前复权锚点连续性（#2464）

`adj_close` 是**前复权**价，而前复权在源侧是「以抓取那一刻的最新价为锚」算出来的：
一次分红 / 送转之后，源侧会把**全部历史**乘上一个新因子。于是「只追加新行、旧行不动」
会让库里的序列在批次边界处落在两代锚点上——边界那天凭空多出一段涨跌，收益日历
（`pnl_calendar` 用 `adj_close` 算日收益）就出现用户从没经历过的亏损日。实测
SZ000568 2026-07-20→21：`close` 口径 -2.806%、`adj_close` 口径 -8.041%，而那天
不是任何除息日。

三条口径（缺一条都修不掉）：

1. **增量窗口含库内最后一行**（`_resolve_window` 返回 `last` 而不是 `last+1`）：
   不制造重叠就没有可比对的同一个日期，锚点有没有挪就无从判断；
2. **锚点比对用 `adj_close/close` 比值**（`_anchor_moved`）：比值只在锚点变化时跳变，
   源侧修订 `close` 会同时挪动分子分母、不误报；比值变了 ⇒ 旧行整段作废，
   从最早可取处**整段重抓**（`_refetch_full_history`）；
3. **写入是 upsert**（`_save_data`）：原实现在 `_deduplicate` 里把已存在的
   `(security_id, trade_date)` 直接丢掉，于是「重算」根本落不了库——断裂永远修不掉。
   现在去重语义下移：insert 与 update 分流，重算能把整段历史覆盖成同一代锚点。

**存量修复**：本机制只保证「以后不再断」。已经断掉的历史要靠一次
`--full-sync`（现在会从 1990 年起抓全量并覆盖写入，不再只抓 365 天）覆盖一遍。

## 注意

- ETF 两个数据源（东财 / 新浪）的**当日** K 线都要到次日才齐，故当天盘后跑往往
  只拿到 T-1；缺口回补会在下一次运行时把缺的那天补上，这正是本口径的价值。
- 依赖 securities 表存在对应 symbol（`_get_security_map`），查不到即静默跳过——
  名录缺失是历史坑，见 StockListSyncJob.fetch_security_catalog。
- 增量窗口非空但取回 0 条的 symbol 记入 `stats['empty_symbols']`（#2277）：
  停牌 / 上游无数据与「今天没新行情」在日志里必须可辨，否则收益日历的
  partial 标注无法归因（真实库 SH601198 09-15 起停牌即此形态）。
"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from loguru import logger
from sqlalchemy import func, tuple_

from app.core.time_utils import today_shanghai
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.job_base import IN_CHUNK_SIZE, SyncJob

# 库内无任何历史时的首次回补窗口（天）。更长的历史走全量同步（full_sync=True）
DEFAULT_BACKFILL_DAYS = 365

# 全量 / 重算窗口的起点下限：A 股最早 1990 年开市，用它表达「要全部历史」。
# 不用 None——`fetch_stock_price(start_date=None)` 会退化成「近 365 天」，
# 重算只会覆盖最近一年，更早的旧锚点行原封不动（#2464 的反面）。
_HISTORY_START = date(1990, 1, 1)

# 锚点比对容差：同一源、同一日期、同一口径下 `adj_close/close` 应当稳定到 float 噪声；
# 一次真实分红 / 送转会把比值整体挪动 0.1% 以上（本机最小实测 0.3%），故 1e-6 的
# 相对容差既吞得下往返误差，又不可能把真实分红判成「没变」。
_ANCHOR_REL_TOL = 1e-6


class PriceHistorySyncJob(SyncJob):
    def get_name(self) -> str:
        return 'price_history'

    @property
    def _allow_empty_data(self) -> bool:
        # 增量同步在非交易日或无目标时返回空是正常的
        return True

    # ── 目标代码获取 ──

    def _get_security_map(self, targets: List[str]) -> dict:
        """
        根据代码列表查询 securities 表，返回 {symbol: Security} 映射。
        用于将 symbol 转换为 security_id。
        """
        securities = self.db.query(Security).filter(Security.symbol.in_(targets)).all()
        return {s.symbol: s for s in securities}

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """全量：拉取所有历史；增量：按各 symbol 的库内最新交易日做缺口回补。"""
        sec_map = self._get_security_map(targets)
        if not sec_map:
            return []

        today = today_shanghai()
        last_map = {} if full_sync else self._load_last_trade_dates(list(sec_map.keys()))
        # 锚点比对用的「库内最后一行」：与 `last_map` 同源，多带 close / adj_close / source
        last_bars = {} if full_sync else self._load_last_bars(list(sec_map.keys()))

        records = list()
        for symbol in targets:
            sec = sec_map.get(symbol)
            if not sec:
                continue

            start_date, end_date = self._resolve_window(symbol, last_map, today, full_sync)
            if start_date is not None and start_date > end_date:
                # 已是最新：多见于「当日 K 线尚未发布」，留给下一次运行补
                continue

            try:
                price_list = self.adapter.fetch_stock_price(symbol, start_date=start_date, end_date=end_date)
            except Exception as e:
                logger.warning(f'获取 {symbol} 行情失败: {e}')
                # #1833：异常必须进 errors —— 否则「全部标的失败」与「今天没行情」
                # 在sync_logs 里长得一模一样（records=[] + status=success + error_detail 空），
                # 而下游 position_price 会据此把持仓全记为无收盘价、快照拿旧价落账。
                self.stats.setdefault('errors', []).append({'symbol': symbol, 'stage': 'fetch_price', 'error': str(e)})
                continue

            if not isinstance(price_list, list):
                continue

            # #2464：源侧前复权锚点挪了（分红 / 送转 / 源侧重算）⇒ 库里的旧行全部作废，
            # 必须整段重抓再覆盖。只补新行的话，批次边界处会留一段凭空的涨跌。
            if not full_sync and self._anchor_moved(last_bars.get(symbol), price_list):
                rebuilt = self._refetch_full_history(symbol, today)
                if rebuilt is not None:
                    price_list = rebuilt
                    self.stats.setdefault('adj_rebuilt_symbols', []).append(symbol)
                    logger.info(f'{symbol} 前复权锚点已变，整段重抓 {len(rebuilt)} 条并覆盖写入')

            # #2277：增量窗口非空却一条都没取回 ⇒ 记入 stats，让「停牌 / 上游
            # 无数据」在 sync_logs 里可见。没有这条记录时，停牌股与「今天没有
            # 新行情」在日志里长得一模一样（`success` 只数写入行数），收益日历
            # 上标 partial 也无从判断是同步没跑、还是标的自己不开盘——真实库
            # 2026-09 的 partial 曾这样被误判成「同步漏跑」，实为 SH601198
            # 09-15 起停牌（东财 / 新浪双源均无 09-15 后行情）。
            # 只记**增量窗口非空**的：`start_date > end_date`（库内已最新，
            # 多为当日 K 线未发布）不是缺数据，别混进来。
            #
            # #2464 之后窗口含库内最后一行（为了比对锚点），于是「取到了」不再等于
            # 「有新行情」：必须出现**晚于库内最后一行**的记录才算。不这么判，
            # 停牌股每轮都能取回那一条重叠行，partial 标注会重新变成永远不亮。
            if not full_sync and start_date <= end_date and not self._has_newer_than(price_list, last_map.get(symbol)):
                self.stats.setdefault('empty_symbols', []).append(symbol)

            # 关联 security_id
            for item in price_list:
                item['security_id'] = sec.id
            records.extend(price_list)

        return records

    @staticmethod
    def _resolve_window(symbol: str, last_map: dict, today: date, full_sync: bool):
        """本次抓取窗口 (start, end)。

        - 全量：从 `_HISTORY_START` 起（**不是** `None`——`None` 在适配器里会退化成
          近 365 天，重算覆盖不到更早的旧锚点行，#2464）；
        - 增量：从「库内最新交易日」起（#2464 起**含**该日，制造一行重叠用于锚点比对）。

        `start > end` 表示无需抓取（库内已到最新），由调用方跳过。
        """
        if full_sync:
            return _HISTORY_START, today
        last = PriceHistorySyncJob._as_date(last_map.get(symbol))
        if last is None:
            # 首次同步该标的：回补近一年，更长的历史走 full_sync
            return today - timedelta(days=DEFAULT_BACKFILL_DAYS), today
        if last >= today:
            # 库内已到今日：没有更晚的交易日可补，保持「start > end ⇒ 跳过」的既有语义
            return today + timedelta(days=1), today
        return last, today

    def _load_last_trade_dates(self, symbols: List[str]) -> dict:
        """批量取 {symbol: 库内最新交易日}；分批 in_ 防 SQLite 变量上限。"""
        out: dict = {}
        for i in range(0, len(symbols), IN_CHUNK_SIZE):
            chunk = symbols[i : i + IN_CHUNK_SIZE]
            rows = (
                self.db.query(PriceHistory.symbol, func.max(PriceHistory.trade_date))
                .filter(PriceHistory.symbol.in_(chunk))
                .group_by(PriceHistory.symbol)
                .all()
            )
            for symbol, last in rows:
                if last is not None:
                    out[symbol] = last
        return out

    def _load_last_bars(self, symbols: List[str]) -> dict:
        """批量取 {symbol: (trade_date, close, adj_close, source)} —— 各标的库内最后一行。

        只为锚点比对（`_anchor_moved`）服务，故取最后一行而不是整段历史。
        """
        last_map = self._load_last_trade_dates(symbols)
        if not last_map:
            return {}
        pairs = list(last_map.items())
        out: dict = {}
        for i in range(0, len(pairs), IN_CHUNK_SIZE):
            chunk = pairs[i : i + IN_CHUNK_SIZE]
            rows = (
                self.db.query(
                    PriceHistory.symbol,
                    PriceHistory.trade_date,
                    PriceHistory.close,
                    PriceHistory.adj_close,
                    PriceHistory.source,
                )
                .filter(tuple_(PriceHistory.symbol, PriceHistory.trade_date).in_(chunk))
                .all()
            )
            for symbol, trade_date, close, adj_close, source in rows:
                out[symbol] = (trade_date, close, adj_close, source)
        return out

    @staticmethod
    def _has_newer_than(price_list: List[dict], last) -> bool:
        """抓回的行里是否有**晚于库内最后一行**的记录（#2277 的 partial 判据）。"""
        last_date = PriceHistorySyncJob._as_date(last)
        for item in price_list:
            day = PriceHistorySyncJob._as_date(item.get('trade_date'))
            if day is None:
                continue
            if last_date is None or day > last_date:
                return True
        return False

    @staticmethod
    def _anchor_moved(stored, price_list: List[dict]) -> bool:
        """源侧前复权锚点是否移动（#2464）。

        前复权在源侧是「以抓取那一刻的最新价为锚」算的：一次分红 / 送转之后，源侧会把
        **全部历史**乘上一个新因子。库里的旧行仍按旧因子，新抓的行按新因子 ⇒ 批次边界
        处凭空多出一段涨跌，日收益因此造假（SZ000568 实测 -5.235pp，而那天不是除息日）。

        判据用 `adj_close / close` 的**比值**而不是 `adj_close` 本身：

        - 比值只在锚点变化时跳变；源侧修订了某天的 `close` 会同时挪动分子分母，不误报；
        - 比对的日期是**库内最后一行**——增量窗口已含该日（`_resolve_window`），
          所以它天然是一行重叠样本。

        以下情况一律返回 False（拿不到可比样本 ⇒ 不下结论，**不把「没拿到」读成「变了」**）：
        库内无该行、窗口里没有这一天的行（停牌 / 源侧缺）、两行 `source` 不同
        （ETF 三源回退时复权实现不同，比值不可比）、任一侧 `adj_close` 或 `close` 为空。
        """
        if not stored or not price_list:
            return False
        last_date, last_close, last_adj, last_source = stored
        day = PriceHistorySyncJob._as_date(last_date)
        row = next((r for r in price_list if PriceHistorySyncJob._as_date(r.get('trade_date')) == day), None)
        if row is None:
            return False
        if row.get('source') != last_source:
            return False
        new_close, new_adj = row.get('close'), row.get('adj_close')
        if not last_close or not last_adj or not new_close or not new_adj:
            return False
        old_ratio = last_adj / last_close
        new_ratio = new_adj / new_close
        return abs(new_ratio - old_ratio) > _ANCHOR_REL_TOL * max(abs(old_ratio), 1.0)

    def _refetch_full_history(self, symbol: str, today: date) -> Optional[List[dict]]:
        """整段重抓该标的的全部历史（锚点变了时用）。

        取不到时返回 None —— 调用方保留原有增量结果，绝不拿「空」当「重算完成」：
        那样会把已有历史原地删空（本 job 现在是 upsert，空列表不会删行，但会把
        「锚点已变」这件事静默吞掉）。
        """
        try:
            rows = self.adapter.fetch_stock_price(symbol, start_date=_HISTORY_START, end_date=today)
        except Exception as e:  # noqa: BLE001
            logger.warning(f'{symbol} 锚点重算失败（保留增量结果）: {e}')
            self.stats.setdefault('errors', []).append({'symbol': symbol, 'stage': 'rebuild_adj', 'error': str(e)})
            return None
        if not isinstance(rows, list) or not rows:
            return None
        return rows

    @staticmethod
    def _as_date(value) -> Optional[date]:
        """宽松转 date：SQLite 的 max() 在个别驱动下会回传字符串而非 date。"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """清洗数据：必填字段检查、日期转换、默认值填充"""
        validated = list()
        for item in raw_data:
            if not item.get('security_id') or not item.get('trade_date') or item.get('close') is None:
                continue

            # 日期字符串转 date 对象
            if isinstance(item['trade_date'], str):
                try:
                    item['trade_date'] = date.fromisoformat(item['trade_date'])
                except ValueError:
                    continue

            # 可选字段默认值
            item.setdefault('open', None)
            item.setdefault('high', None)
            item.setdefault('low', None)
            item.setdefault('volume', None)
            item.setdefault('adj_close', item['close'])
            item.setdefault('source', self.adapter.get_name())
            validated.append(item)

        return validated

    # ── 去重 / 保存（#2464：upsert，不再「只插不更新」）──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """原样返回：去重语义已**下移**到 `_save_data` 的 insert / update 分流。

        #2464 前这里把已存在的 `(security_id, trade_date)` 直接丢掉，于是任何「重算」
        都落不了库——锚点变了也写不回去，断裂永远修不掉。这些行不是「跳过」，
        而是被**重写**，故 `stats['skipped']` 恒为 0、`stats['updated']` 单独计数。
        """
        return list(data)

    def _load_existing_ids(self, rows: List[dict]) -> dict:
        """{(security_id, trade_date): 主键 id}，分批 `in_` 防 SQLite 变量上限。

        只查本次要写的那批键，**不做全表/整段历史扫描**：增量一轮只有每标的一行。
        """
        keys = [(item['security_id'], item['trade_date']) for item in rows]
        out: dict = {}
        for i in range(0, len(keys), IN_CHUNK_SIZE):
            chunk = keys[i : i + IN_CHUNK_SIZE]
            pairs = (
                self.db.query(PriceHistory.id, PriceHistory.security_id, PriceHistory.trade_date)
                .filter(tuple_(PriceHistory.security_id, PriceHistory.trade_date).in_(chunk))
                .all()
            )
            for pk, security_id, trade_date in pairs:
                out[(security_id, trade_date)] = pk
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        """写入：已存在的行**更新**、不存在的行插入（#2464）。

        重算必须能覆盖已有行，否则「整段重抓」只是把同一批旧值再写一次。
        """
        if not new_data:
            return

        existing = self._load_existing_ids(new_data)
        to_insert = []
        to_update = []
        for item in new_data:
            pk = existing.get((item['security_id'], item['trade_date']))
            if pk is None:
                to_insert.append(item)
            else:
                # 主键回填后整行覆盖：open/high/low/close/volume/adj_close/source 都是
                # 源侧对同一天的权威值，没有「只更新 adj_close」的正当理由——
                # 换了锚点时两者本就要一起挪动。
                to_update.append({**item, 'id': pk})

        if to_insert:
            self.db.bulk_insert_mappings(PriceHistory, to_insert)
        if to_update:
            self.db.bulk_update_mappings(PriceHistory, to_update)
        self.db.commit()

        if to_update:
            self.stats['updated'] = self.stats.get('updated', 0) + len(to_update)
